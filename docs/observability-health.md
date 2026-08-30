# Observabilidade, Métricas e Healthcheck

Documento de referência para monitoramento, métricas de performance, verificação de integridade (*healthcheck*) e logs estruturados da Auth API.

---

## 1. Endpoints de Monitoramento

A aplicação expõe três endpoints essenciais para orquestradores (Kubernetes, AWS ECS, Docker Swarm) e plataformas de monitoramento (Prometheus, Grafana, Datadog):

| Endpoint | Protocolo | Autenticação | Descrição |
| :--- | :--- | :--- | :--- |
| `GET /live` (ou `/api/live`) | HTTP | Pública | **Liveness Probe** (*shallow check* em memória para o processo ASGI) |
| `GET /api/health` | HTTP | Pública | **Readiness Probe** (*deep check* das dependências: DB e Redis) |
| `GET /metrics` | HTTP | Pública (ou restrita via proxy) | Métricas no formato Prometheus |

---

## 2. Liveness Probe (`GET /live`)

O endpoint `/live` é um *shallow check* que responde imediatamente com `{"status": "alive"}` (`200 OK`) sem realizar nenhuma consulta externa.

*   **Objetivo:** Informar ao orquestrador apenas se o processo Python / FastAPI continua vivo e responsivo.
*   **Ação em caso de falha:** O orquestrador reinicia o contêiner (pois indica travamento real de processo ou deadlock).

---

## 3. Readiness Probe e Healthcheck (`GET /api/health`)

O endpoint [`/api/health`](file:///spot/NdDaniel/Code/Estudo/Auth/app/main.py) realiza checagens ativas e assíncronas nas dependências críticas do sistema (PostgreSQL via `SELECT 1` e Redis).

### Exemplo de Resposta Saudável (`200 OK`):

```json
{
  "status": "healthy",
  "app": "Auth API",
  "version": "0.1.0",
  "environment": "production",
  "database": {
    "status": "ok",
    "engine": "postgresql"
  },
  "redis": {
    "status": "ok"
  }
}
```

### Exemplo de Resposta com Falha (`503 Service Unavailable`):

```json
{
  "status": "unhealthy",
  "app": "Auth API",
  "version": "0.1.0",
  "environment": "production",
  "database": {
    "status": "error",
    "details": "Connection timeout"
  },
  "redis": {
    "status": "disabled"
  }
}
```

> **⚠️ Diretrizes para Configuração de Sondas (Probes):**
> * **Liveness Probe (Kubernetes / Docker Swarm):** Deve apontar **obrigatoriamente para `/live`**. Nunca aponte para `/api/health`, pois oscilações no banco de dados farão o orquestrador reiniciar todos os contêineres ao mesmo tempo (*Thundering Herd*).
> * **Readiness Probe:** Deve apontar para `/api/health`. Se o banco cair, a instância é apenas removida do pool do Load Balancer sem reiniciar o processo da aplicação.

---

## 3. Métricas Prometheus (`GET /metrics`)

Coletadas automaticamente pelo [`MetricsMiddleware`](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/observability.py) em cada requisição HTTP recebida.

### Principais Métricas Exportadas:

| Nome da Métrica | Tipo | Labels | Descrição |
| :--- | :--- | :--- | :--- |
| `http_requests_total` | Counter | `method`, `handler`, `status` | Total de requisições HTTP processadas |
| `http_request_duration_seconds` | Histogram | `method`, `handler` | Latência das requisições em segundos (com buckets) |
| `http_requests_in_progress` | Gauge | `method`, `handler` | Número de requisições sendo executadas no momento |
| `app_info` | Gauge | `app_name`, `version`, `environment` | Metadados da aplicação e versão em execução |

### Configuração de Scraping no `prometheus.yml`:

```yaml
scrape_configs:
  - job_name: 'auth-api'
    scrape_interval: 15s
    metrics_path: '/metrics'
    static_configs:
      - targets: ['auth-api:8000']
```

---

## 4. Logs Estruturados em JSON (`python-json-logger`)

Em ambientes de produção, os logs são emitidos em JSON estruturado para facilitar a indexação em ferramentas como **Grafana Loki**, **Datadog**, **ELK Stack** ou **AWS CloudWatch Logs**.

### Exemplo de Log Emitido:

```json
{
  "timestamp": "2026-08-18T16:30:15.123456Z",
  "level": "INFO",
  "logger": "app.core.middleware",
  "service": "Auth API",
  "message": "HTTP Request Processed",
  "http_method": "POST",
  "http_path": "/api/auth/login",
  "status_code": 200,
  "duration_ms": 42.15,
  "client_ip": "192.168.1.50"
}
```
