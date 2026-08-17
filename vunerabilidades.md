# Relatório de Análise de Vulnerabilidades e Cenários de Risco Arquitetural

Data da Análise: 17 de Agosto de 2026

## Resumo Executivo

Este documento apresenta a análise técnica detalhada do projeto `Auth` em relação às 20 apontamentos do relatório de vulnerabilidades (`relatorio_vunerabilidade.txt`), incluindo os **cenários de risco arquitetural** (falhas que persistem mesmo com o arquivo `.env` corretamente configurado em produção) e seus respectivos **planos de correção defensiva**.

### Síntese da Avaliação
- **Vulnerabilidades de Código/Arquitetura (14 itens):** Confirmadas no código-fonte. Mesmo com variáveis de ambiente fortes, a lógica de código apresenta riscos operacionais.
- **Práticas Defensivas Existentes (5 itens):** Os itens 15 a 19 estão corretamente implementados e funcionando.
- **Configuração de Cookies (1 item):** O item 7 é um alerta informativo para caso o transporte por cookies venha a ser adotado futuramente (atualmente a API usa Bearer Token no cabeçalho HTTP / JSON body).

---

## 🟢 Boas Práticas Já Implementadas (Confirmadas)

| Item | Descrição | Status no Código | Evidência / Arquivo |
| :--- | :--- | :--- | :--- |
| **15** | Algoritmo JWT Restrito no Decode | ✅ **Implementado** | [security.py:141](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/security.py#L141) — Restringe a `algorithms=[settings.ALGORITHM]`. |
| **16** | Rotação de Refresh Token com Detecção de Reuso | ✅ **Implementado** | [auth_service.py:107-110](file:///spot/NdDaniel/Code/Estudo/Auth/app/services/auth_service.py#L107-L110) — Revoga todas as sessões ativas caso um refresh token reutilizado seja detectado. |
| **17** | Hash Argon2 para Senhas | ✅ **Implementado** | [config.py:86](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/config.py#L86), [security.py:16](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/security.py#L16) — Utiliza o algoritmo recomendado Argon2id. |
| **18** | Tokens Opacos para Reset / Verificação | ✅ **Implementado** | [auth_service.py](file:///spot/NdDaniel/Code/Estudo/Auth/app/services/auth_service.py) — Gera tokens aleatórios de alta entropia com hash SHA-256 no banco. |
| **19** | Blacklist de Token no Logout | ✅ **Implementado** | [auth_service.py:154-159](file:///spot/NdDaniel/Code/Estudo/Auth/app/services/auth_service.py#L154-L159) — Adiciona o `jti` do access token à blacklist ao realizar logout. |

---

## 🔴 Vulnerabilidades, Cenários de Risco Arquitetural e Planos de Correção

---

### 1. Críticas

#### **1. Secrets Padrão Hardcoded em Desenvolvimento e Defaults Fracos**
- **Localização:** [config.py:68-71](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/config.py#L68-L71), [config.py:278](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/config.py#L278)
- **Status:** **Verdadeiro**
- **Cenário de Risco (Mesmo com .env configurado):** 
  Se uma variável de ambiente como `ADMIN_PASSWORD` não for informada no `.env` do ambiente de produção, a aplicação inicia utilizando o default `'admin123'` sem emitir erros de inicialização, criando uma conta administrativa vulnerável.
- **Plano de Correção:**
  - Em `ProductionSettings`, adicionar validações explícitas (`min_length` ou validadores `@model_validator`) que impeçam a inicialização da aplicação se `ADMIN_PASSWORD`, `SECRET_KEY` ou `REFRESH_SECRET_KEY` utilizarem valores padrões ou fracos.

#### **2. Fallback do Refresh Token para Secret de Acesso**
- **Localização:** [config.py:263-264](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/config.py#L263-L264)
- **Status:** **Verdadeiro**
- **Cenário de Risco (Mesmo com .env configurado):** 
  Se o operador configurar a `SECRET_KEY` mas esquecer de definir a `REFRESH_SECRET_KEY` no `.env`, o sistema executa `return self.REFRESH_SECRET_KEY or self.SECRET_KEY`. Com isso, tokens de acesso e refresh tokens passam a ser assinados com o mesmo segredo, violando o isolamento de chaves.
- **Plano de Correção:**
  - Tornar `REFRESH_SECRET_KEY` uma variável de ambiente obrigatória sem fallback automático em ambiente de produção.

#### **3. Rate Limiting Fail-Open**
- **Localização:** [redis.py:140-141](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/redis.py#L140-L141), [redis.py:153](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/redis.py#L153)
- **Status:** **Verdadeiro**
- **Cenário de Risco (Mesmo com .env configurado):** 
  Mesmo com o Redis perfeitamente configurado e ativo em produção, caso a instância do Redis caia (por OOM, falha de rede ou manutenção), as chamadas `rate_limit_check` capturam o erro e retornam `None`. No FastAPI, a dependência entende `None` como liberação da requisição, desabilitando completamente a proteção de rate limit em rotas sensíveis (login, registro, reset de senha).
- **Plano de Correção:**
  - Alterar a lógica do rate limiter para a política *fail-closed* em produção (bloquear requisições excessivas ou fallback imediato para limitação local rigorosa se o Redis estiver indisponível).

---

### 2. Alta Severidade

#### **4. Rate Limiter In-Memory Não Pronto para Produção (Multi-instâncias)**
- **Localização:** [rate_limiter.py:19-22](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/rate_limiter.py#L19-L22)
- **Status:** **Verdadeiro**
- **Cenário de Risco (Mesmo com .env configurado):** 
  Em uma arquitetura com múltiplas réplicas (Kubernetes, Docker Swarm ou instâncias com múltiplos workers Uvicorn), se o Redis não for utilizado, a memória in-memory é isolada por processo. Um atacante pode distribuir as requisições entre as réplicas via Load Balancer, multiplicando a taxa de tentativas permitidas pelo número de instâncias.
- **Plano de Correção:**
  - Tornar a presença do Redis mandatória para ambientes distribuídos de produção e invalidar a inicialização sem repositório centralizado de limite quando `ENVIRONMENT=production`.

#### **5. Ausência de Token Binding / Device Fingerprinting**
- **Localização:** [security.py:58-78](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/security.py#L58-L78)
- **Status:** **Verdadeiro**
- **Cenário de Risco (Mesmo com .env configurado):** 
  Os tokens de acesso JWT emitidos são *bearer tokens* padrão. Caso um token seja interceptado ou vazado, ele pode ser reutilizado por qualquer cliente, de qualquer IP ou localização, sem que haja validação de dispositivo.
- **Plano de Correção:**
  - Manter o tempo de vida do access token curto (15 min), utilizar rotação estrita de refresh tokens e incluir vinculação opcional de sessão (ex: hash de User-Agent/IP no payload ou validação na blacklist).

#### **6. Token de Reset de Senha Exposto em Eventos**
- **Localização:** [auth_service.py:206-217](file:///spot/NdDaniel/Code/Estudo/Auth/app/services/auth_service.py#L206-L217)
- **Status:** **Verdadeiro**
- **Cenário de Risco (Mesmo com .env configurado):** 
  Mesmo que a conexão com o RabbitMQ/Kafka utilize credenciais seguras e SSL no `.env`, a inclusão do `reset_token` no payload do evento `PASSWORD_RESET_REQUESTED` faz com que o token seja trafegado e armazenado em logs do Message Broker, ferramentas de monitoramento (ELK/Datadog) e consumidores do barramento. Qualquer operador ou serviço com acesso aos eventos poderá visualizar o token e redefinir a senha do usuário.
- **Plano de Correção:**
  - Remover o campo `reset_token` do payload do evento publicado no barramento de eventos.

#### **7. Flags de Segurança em Cookies (Informativo)**
- **Localização:** [routers/auth.py](file:///spot/NdDaniel/Code/Estudo/Auth/app/api/routers/auth.py)
- **Status:** **Informativo / Não Aplicável Atualmente**
- **Cenário de Risco:** 
  A API utiliza autenticação baseada em tokens JWT no corpo JSON da resposta e cabeçalho `Authorization: Bearer`. Não há manipulação de cookies no momento.
- **Plano de Correção:**
  - Caso cookies venham a ser adotados para armazenar tokens no futuro, garantir a definição obrigatória das flags `HttpOnly`, `Secure` e `SameSite=Lax` ou `Strict`.

#### **8. State Token OAuth Google Usa Secret Principal da Aplicação**
- **Localização:** [google_auth_service.py:47-51](file:///spot/NdDaniel/Code/Estudo/Auth/app/services/google_auth_service.py#L47-L51)
- **Status:** **Verdadeiro**
- **Cenário de Risco (Mesmo com .env configurado):** 
  `create_google_state` assina o token de estado CSRF utilizando a `SECRET_KEY` global da aplicação. Caso a `SECRET_KEY` principal seja exposta ou comprometida em um contexto isolado, um atacante pode assinar tokens de estado OAuth válidos para realizar ataques de login CSRF.
- **Plano de Correção:**
  - Criar uma variável de configuração dedicada (ex: `OAUTH_STATE_SECRET_KEY`) para a assinatura exclusiva de tokens de estado OAuth.

---

### 3. Média e Baixa Severidade

#### **9. Lista de Senhas Comuns Reduzida**
- **Localização:** [validators.py:20-45](file:///spot/NdDaniel/Code/Estudo/Auth/app/schemas/validators.py#L20-L45)
- **Status:** **Verdadeiro**
- **Cenário de Risco:** 
  A lista `COMMON_PASSWORDS` possui apenas 25 entradas. Senhas muito comuns no Brasil e no mundo (como `12345678`, `mudar123`, etc.) passam pela validação se não estiverem na lista reduzida.
- **Plano de Correção:**
  - Carregar um dicionário expandido de senhas fracas (ex: top 10.000 senhas comuns de listas como SecLists) em um arquivo ou estrutura eficiente (`set`/`frozenset`).

#### **10. Token de Verificação de Email na URL (Query String)**
- **Localização:** [auth_service.py:349](file:///spot/NdDaniel/Code/Estudo/Auth/app/services/auth_service.py#L349), [auth_service.py:199](file:///spot/NdDaniel/Code/Estudo/Auth/app/services/auth_service.py#L199)
- **Status:** **Verdadeiro**
- **Cenário de Risco:** 
  Ao enviar o token na URL em parâmetros de consulta (`?token=...`), ele pode ser registrado em logs de proxy/Nginx/CDN, histórico de navegadores e no cabeçalho `Referer` se o usuário clicar em links externos.
- **Plano de Correção:**
  - Configurar cabeçalho `Referrer-Policy: no-referrer` nas respostas e garantir que os tokens em URL possuam prazo de expiração curto e invalidação imediata após o primeiro uso.

#### **11. Sem Notificação de Lockout de Conta**
- **Localização:** [user_service.py:110-118](file:///spot/NdDaniel/Code/Estudo/Auth/app/services/user_service.py#L110-L118)
- **Status:** **Verdadeiro**
- **Cenário de Risco:** 
  Quando uma conta é temporariamente bloqueada por atingir o limite de tentativas de login falhas, o sistema gera um log de segurança interno, mas não notifica o titular da conta por e-mail sobre a atividade suspeita.
- **Plano de Correção:**
  - Disparar um evento/e-mail de alerta de segurança para o usuário informando sobre tentativas de acesso malsucedidas seguidas de bloqueio temporário.

#### **12. CORS Wildcard em Configuração de Teste**
- **Localização:** [config.py:371-373](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/config.py#L371-L373)
- **Status:** **Verdadeiro**
- **Cenário de Risco:** 
  Se um ambiente de teste ou staging for exposto publicamente com `CORS_ALLOWED_ORIGINS="*"`, sites maliciosos podem realizar requisições para a API de testes se houver credenciais compartilhadas.
- **Plano de Correção:**
  - Substituir o wildcard `*` em `TestSettings` por origens locais de teste explícitas.

#### **13. Sem Histórico de Senha / Prevenção de Reuso**
- **Status:** **Verdadeiro**
- **Cenário de Risco:** 
  Um usuário que teve suas credenciais vazadas em outro serviço pode redefinir a senha na aplicação informando exatamente a mesma senha anterior.
- **Plano de Correção:**
  - Implementar uma tabela `password_history` armazenando os últimos $N$ hashes de senhas e bloquear a reutilização de senhas recentes no fluxo de alteração/reset.

#### **14. Headers de Segurança Ausentes**
- **Localização:** [main.py](file:///spot/NdDaniel/Code/Estudo/Auth/app/main.py), [middleware.py](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/middleware.py)
- **Status:** **Verdadeiro**
- **Cenário de Risco:** 
  A ausência de cabeçalhos como `X-Frame-Options` (permite inclusão da página em `iframe` para ataques de clickjacking), `X-Content-Type-Options: nosniff` e `Strict-Transport-Security` reduz a proteção em profundidade do navegador.
- **Plano de Correção:**
  - Injetar um middleware global no FastAPI configurando cabeçalhos de segurança padrão HTTP.

#### **20. Docker Executando como Root**
- **Localização:** [Dockerfile](file:///spot/NdDaniel/Code/Estudo/Auth/Dockerfile)
- **Status:** **Verdadeiro**
- **Cenário de Risco:** 
  Sem a instrução `USER` no Dockerfile, o processo Uvicorn roda como `root` dentro do container. Em uma eventual vulnerabilidade de escapamento de container (container escape), o invasor ganha privilégios de `root` no host.
- **Plano de Correção:**
  - Adicionar criação e alternância para usuário não-privilegiado no `Dockerfile`:
    ```dockerfile
    RUN useradd -m -u 1000 appuser
    USER appuser
    ```

---

## Próximas Ações Recomendadas

1. **Correção Imediata (Fase 1 - Críticas e Alta Prioridade):**
   - Atualizar `config.py` para exigir segredos sem fallback e validação no `ProductionSettings`.
   - Modificar `redis.py` para alterar o comportamento de rate limit para *fail-closed*.
   - Remover `reset_token` do payload do evento em `auth_service.py`.
   - Adicionar diretiva `USER` no `Dockerfile`.

2. **Reforço de Segurança (Fase 2 - Média e Defesa em Profundidade):**
   - Criar middleware de Security Headers em `middleware.py`.
   - Expandir a validação de senhas fracas em `validators.py`.
   - Implementar tabela de histórico de senhas.
