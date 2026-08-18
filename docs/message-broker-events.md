# Arquitetura de Eventos e Message Broker

Documento de referência da arquitetura orientada a eventos (Event-Driven Architecture) da Auth API.
Descreve o barramento interno de eventos, a integração plugável com brokers externos (**RabbitMQ** e **Apache Kafka**), o esquema padronizado de eventos e as diretrizes de integração com microsserviços.

---

## 1. Visão Geral da Arquitetura

A Auth API adota o padrão de eventos de domínio assíncronos para desacoplar a lógica central de autenticação de serviços secundários (como envio de e-mails, notificações em tempo real, auditoria e sincronização com microsserviços externos).

```mermaid
graph TD
    A[Ação de Negócio: Login / Registro / Perfil] --> B[Event Bus Interno]
    B --> C[NotificationService / WebSockets]
    B --> D[Security & Audit Logs]
    B --> E[Message Broker Publisher]
    E --> F[(RabbitMQ)]
    E --> G[(Apache Kafka)]
    F --> H[Microsserviços Externos]
    G --> H
```

---

## 2. Estrutura Canônica do Evento (`Event`)

Todos os eventos emitidos pela aplicação seguem o contrato canônico definido em [`app/core/events.py`](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/events.py):

| Campo | Tipo | Descrição |
| :--- | :--- | :--- |
| `event_id` | `string (UUID v4)` | Identificador único e imutável do evento |
| `type` | `string` | Nome do evento no formato `dominio.acao` (ex: `user.created`, `auth.login`) |
| `timestamp` | `datetime (ISO 8601 UTC)` | Momento exato em que o evento ocorreu |
| `data` | `dict` | Carga útil contendo os dados do evento (sem dados sensíveis como senhas) |
| `correlation_id` | `string (opcional)` | Identificador de rastreamento da transação distribuída ponta a ponta |
| `causation_id` | `string (opcional)` | ID da mensagem ou evento que causou este evento |

### Exemplo de Payload JSON:

```json
{
  "event_id": "a9b3d123-4567-890a-bcde-f1234567890a",
  "type": "user.created",
  "timestamp": "2026-08-18T16:20:00.123456Z",
  "correlation_id": "req-987654321",
  "causation_id": "cmd-123456",
  "data": {
    "user_id": "b8de84c8-7899-4d84-b15a-a281c96c0e5f",
    "email": "usuario@exemplo.com",
    "full_name": "Nome do Usuário",
    "is_active": true,
    "roles": ["user"]
  }
}
```

---

## 3. Catálogo de Eventos de Domínio

### Eventos de Usuário (`user.*`)

| Evento | Momento do Disparo | Dados no Payload |
| :--- | :--- | :--- |
| `user.created` | Criação de novo usuário (auto-registro ou admin) | `user_id`, `email`, `full_name`, `roles` |
| `user.updated` | Atualização de perfil cadastral | `user_id`, `full_name`, `email` |
| `user.deactivated` | Conta desativada por um administrador | `user_id`, `reason` |
| `user.roles_changed` | Atribuição/remoção de papéis administrativos | `user_id`, `roles` |
| `user.password_changed` | Redefinição ou alteração de senha | `user_id`, `changed_at` |
| `user.email_verified` | Confirmação de e-mail bem-sucedida | `user_id`, `email`, `verified_at` |

### Eventos de Autenticação (`auth.*`)

| Evento | Momento do Disparo | Dados no Payload |
| :--- | :--- | :--- |
| `auth.login` | Autenticação bem-sucedida (senha ou Google) | `user_id`, `ip_address`, `user_agent` |
| `auth.password_reset_requested` | Solicitação de recuperação de senha | `email`, `token_id` |
| `auth.password_reset_completed` | Conclusão da redefinição de senha | `user_id`, `completed_at` |

---

## 4. Integração com Message Brokers

O módulo [`app/core/broker.py`](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/broker.py) fornece integração nativa assíncrona.

### 4.1 RabbitMQ (`aio-pika`)
* **Padrão de Exchange:** `topic` com persistência (`durable=True`).
* **Routing Keys:** O nome do evento é usado diretamente como Routing Key (ex: `user.created`, `auth.*`).
* **Configuração:**
  ```env
  MESSAGE_BROKER_TYPE=rabbitmq
  MESSAGE_BROKER_URL=amqps://usuario:senha@host.cloudamqp.com/vhost
  MESSAGE_BROKER_EXCHANGE=auth_events
  MESSAGE_BROKER_EXCHANGE_TYPE=topic
  ```

### 4.2 Apache Kafka (`aiokafka`)
* **Tópicos:** `<prefixo>.<evento>` (ex: `auth_events.user.created`).
* **Garantias:** Idempotência ativada (`enable_idempotence=True`), confirmações completas (`acks=all`), chaves de partição pelo `event_id`.
* **Configuração:**
  ```env
  MESSAGE_BROKER_TYPE=kafka
  MESSAGE_BROKER_BOOTSTRAP_SERVERS=kafka-host:9092
  MESSAGE_BROKER_CONSUMER_GROUP=auth-service
  ```

---

## 5. Provedores Gerenciados Gratuitos Recomendados

1. **CloudAMQP (RabbitMQ):**
   * Plano gratuito *Little Lemur* (1M mensagens/mês).
   * URL com TLS: `amqps://...` (definir `MESSAGE_BROKER_SSL=true`).
2. **Upstash Kafka:**
   * Plano gratuito Serverless (10k mensagens/dia).
