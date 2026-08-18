# Observabilidade, Métricas e Healthcheck

Documento de referência para monitoramento, métricas de performance, verificação de integridade (*healthcheck*) e logs estruturados da Auth API.

---

## 1. Endpoints de Monitoramento

A aplicação expõe dois endpoints essenciais para orquestradores (Kubernetes, AWS ECS, Docker Swarm) e plataformas de monitoramento (Prometheus, Grafana, Datadog):

| Endpoint | Protocolo | Autenticação | Descrição |
| :--- | :--- | :--- | :--- |
| `GET /api/health` | HTTP | Pública | Healthcheck da API e dependências (DB e Redis) |
| `GET /metrics` | HTTP | Pública (ou restrita via proxy) | Métricas no formato Prometheus |

---

## 2. Healthcheck (`GET /api/health`)

O endpoint [`/api/health`](file:///spot/NdDaniel/Code/Estudo/Auth/app/main.py#L43-L45) realiza checagens ativas e assíncronas nas dependências críticas do sistema.

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

> **Nota para Liveness e Readiness Probes:**
> * **Liveness Probe (Kubernetes):** Pode apontar para `/api/health` para reiniciar contêineres que travaram.
> * **Readiness Probe:** Garante que o tráfego só chegue após o banco de dados responder com sucesso.

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
