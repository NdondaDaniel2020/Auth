# Imutabilidade de Auditoria (Append-Only) e Armazenamento WORM

Este documento descreve a arquitetura de segurança em profundidade (**Defense in Depth**) aplicada aos registros de auditoria administrativa (`audit_logs`), garantindo que nenhuma ação sensível possa ser alterada ou apagada, mesmo em cenários de comprometimento de credenciais da aplicação ou privilégios intermediários no banco de dados.

---

## 1. As Quatro Camadas de Imutabilidade (Defense in Depth)

A integridade dos registros é protegida em 4 camadas complementares:

```
┌─────────────────────────────────────────────────────────────┐
│ 1. Aplicação / Repositório (AuditRepository)                │
│    Bloqueio de chamadas a update() e delete()               │
├─────────────────────────────────────────────────────────────┤
│ 2. ORM / SQLAlchemy Events                                  │
│    before_update e before_delete interceptam mutações de    │
│    sessão antes do envio de comandos                        │
├─────────────────────────────────────────────────────────────┤
│ 3. SGBD / Triggers de Banco de Dados (PostgreSQL / SQLite)  │
│    Trigger Function que aborta transações de UPDATE/DELETE  │
│    direto via SQL / clientes externos                       │
├─────────────────────────────────────────────────────────────┤
│ 4. RBAC SQL / Permissões de Usuário                         │
│    app_user possui apenas permissões de INSERT e SELECT na  │
│    tabela audit_logs                                        │
└─────────────────────────────────────────────────────────────┘
```

### 1.1. Camada de Repositório (`app/repositories/audit_repository.py`)
Qualquer chamada explícita aos métodos `update()` ou `delete()` da classe `AuditRepository` lança `AuditImmutabilityError` (`code="AUDIT_LOG_IMMUTABLE"`):

```python
await audit_repo.update(record, {...})  # Lança AuditImmutabilityError
await audit_repo.delete(record)         # Lança AuditImmutabilityError
```

### 1.2. Camada de Eventos ORM (`app/models/audit_log.py`)
Decoradores `@event.listens_for(AuditLog, 'before_update')` e `@event.listens_for(AuditLog, 'before_delete')` barram operações de mutação realizadas através de qualquer `AsyncSession` do SQLAlchemy.

### 1.3. Triggers em Nível de SGBD (`migrations/versions/`)
Mesmo que um operador execute comandos SQL diretos via `psql` ou ferramentas externas:
- **PostgreSQL:**
  ```sql
  CREATE OR REPLACE FUNCTION block_audit_log_mutation()
  RETURNS TRIGGER AS $$
  BEGIN
      RAISE EXCEPTION 'A tabela audit_logs é append-only. Operações de UPDATE ou DELETE são proibidas.';
  END;
  $$ LANGUAGE plpgsql;

  CREATE TRIGGER prevent_audit_log_mutation
  BEFORE UPDATE OR DELETE ON audit_logs
  FOR EACH ROW
  EXECUTE FUNCTION block_audit_log_mutation();
  ```
- **SQLite (Ambiente de Testes):**
  Triggers locais registrados via `DDL` com `RAISE(ABORT, ...)` para manter a mesma semântica de bloqueio durante a execução da suíte de testes.

### 1.4. Permissões de Banco de Dados (RBAC SQL)
Em ambiente de produção, o usuário conectado à aplicação (`app_user`) deve possuir permissões restritas na tabela:
```sql
REVOKE ALL ON TABLE audit_logs FROM app_user;
GRANT INSERT, SELECT ON TABLE audit_logs TO app_user;
```

---

## 2. Encadeamento Criptográfico (Hash Chain)

Cada linha inserida na tabela `audit_logs` calcula um digest criptográfico SHA-256 encadeado ao registro anterior:

### Colunas
- `previous_hash` (`VARCHAR(64)`, nullable): Hash do registro imediatamente anterior na sequência cronológica (nulo para o registro inicial / gênese).
- `hash` (`VARCHAR(64)`, non-nullable, indexed): Hash SHA-256 gerado a partir dos dados sensíveis do registro atual concatenados ao `previous_hash`.

### Payload Canônico Hashed
O cálculo (`app/core/security/audit.py`) gera um hash determinístico a partir dos campos canônicos:
```text
{id}|{actor_user_id}|{action}|{resource_type}|{resource_id}|{result}|{details_json}|{created_at_utc_iso}|{previous_hash}
```

### Rotina de Verificação de Integridade
A função `verify_audit_trail_integrity` (`app/services/audit_service.py`) permite validar a qualquer momento a integridade da cadeia de ponta a ponta:

```python
from app.services.audit_service import verify_audit_trail_integrity

is_valid, errors = await verify_audit_trail_integrity(db)
if not is_valid:
    logger.critical("Violação de integridade nos logs de auditoria: %s", errors)
```

A rotina verifica:
1. Se o `previous_hash` de cada linha corresponde ao `hash` da linha precedente.
2. Se o recálculo do SHA-256 dos campos bate exatamente com o valor armazenado na coluna `hash`.

Qualquer tentativa de edição fora da aplicação ou deleção no meio da sequência provocará falha imediata na verificação.

---

## 3. Off-loading para Armazenamento Imutável (WORM)

Para conformidade com regulações internacionais de segurança e auditoria (ex.: SOC 2 Tipo II, ISO 27001, HIPAA, PCI-DSS, LGPD/GDPR), recomenda-se a exportação assíncrona dos registros para um armazenamento **WORM (Write Once, Read Many)**.

### 3.1. Arquitetura Recomendada com AWS S3 Object Lock

```
┌──────────────┐     Eventos      ┌───────────────┐   Consumo / Batch   ┌───────────────────────────┐
│   Auth API   ├─────────────────►│ Message Broker│────────────────────►│ Sink Worker (Assíncrono)   │
│ (Audit Repo) │                  │ (Rabbit/Kafka)│                     │                           │
└──────────────┘                  └───────────────┘                     └─────────────┬─────────────┘
                                                                                      │
                                                                       Streaming JSON │ (SHA-256 + HMAC)
                                                                                      ▼
                                                                        ┌───────────────────────────┐
                                                                        │ AWS S3 Bucket             │
                                                                        │ - Object Lock Ativado     │
                                                                        │ - Mode: COMPLIANCE        │
                                                                        │ - Retenção: 5 a 7 Anos    │
                                                                        └───────────────────────────┘
```

### 3.2. Configuração do S3 com Object Lock em Compliance Mode
No modo **Compliance**:
- Nenhum usuário (nem mesmo o usuário `root` da conta AWS) pode sobrescrever ou apagar os objetos durante o período de retenção configurado.
- Garante proteção estrita mesmo contra ataques com comprometimento total de chaves de infraestrutura.

Exemplo de configuração via Terraform / OpenTofu:
```hcl
resource "aws_s3_bucket" "audit_logs" {
  bucket = "company-auth-audit-logs-worm"
}

resource "aws_s3_bucket_object_lock_configuration" "audit_lock" {
  bucket = aws_s3_bucket.audit_logs.id

  rule {
    default_retention {
      mode  = "COMPLIANCE"
      years = 7
    }
  }
}
```

### 3.3. Integração via Message Broker
Os eventos gerados em `record_admin_action` podem ser simultaneamente publicados na fila `audit.events` utilizando a infraestrutura de mensageria já existente (`app/core/broker.py`), assegurando que sistemas de SIEM (Splunk, Datadog, Elastic) consumam os logs em tempo quase real.
