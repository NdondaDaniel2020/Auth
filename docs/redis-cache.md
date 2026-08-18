# Redis: Cache, Rate Limiting Distribuído e Sessões

Documento de referência para o uso e configuração do Redis na Auth API.
Descreve as responsabilidades do Redis, a política de *fail-closed* em produção, o suporte a instâncias gerenciadas em nuvem (Upstash/Redis Cloud) e o modo de fallback.

---

## 1. Responsabilidades do Redis na Aplicação

O Redis atua como uma camada de alta performance e compartilhamento de estado entre réplicas da API:

```mermaid
graph TD
    API[Auth API FastAPI] --> R[(Redis)]
    R --> C[1. Cache de Dados com TTL]
    R --> RL[2. Rate Limiter Distribuído]
    R --> S[3. Armazenamento de Sessões]
    R --> WS[4. Canal Pub/Sub de WebSockets]
```

1. **Cache de Dados:** Métodos utilitários assíncronos (`cache_get`, `cache_set`, `cache_delete`, `cache_delete_pattern`) com expiração automática (TTL).
2. **Rate Limiting Distribuído:** Controle de taxa de requisições compartilhado entre todos os nós da aplicação via algoritmo de *Sliding Window Counter*.
3. **Gerenciamento de Sessões:** Persistência temporária de sessões e revogação em lote de dispositivos (`session_delete_user_sessions`).
4. **Pub/Sub para WebSockets:** Canal de broadcast `ws:events` para entrega de mensagens em tempo real entre servidores.

---

## 2. Política de Confiabilidade (Fail-Closed vs Fail-Open)

O módulo [`app/core/redis.py`](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/redis.py) adota políticas diferenciadas por ambiente:

| Ambiente | Se o Redis estiver indisponível ou desconectado |
| :--- | :--- |
| **Desenvolvimento (`development`) / Testes (`test`)** | **Fail-Open:** A API continua funcionando normalmente. Cache é ignorado e o rate limiter permite a passagem para não travar o desenvolvimento local. |
| **Produção (`production`)** | **Fail-Closed:** Se o Redis cair, o rate limiter bloqueia tentativas abusivas por segurança (`logger.error('Redis unavailable... enforcing fail-closed')`). |

---

## 3. Configuração de Variáveis de Ambiente

```env
# URL de conexão com o Redis (suporta redis:// e rediss:// com TLS)
REDIS_URL=rediss://default:SEU_TOKEN@seu-host.upstash.io:6379

# Limite máximo de conexões no pool assíncrono
REDIS_MAX_CONNECTIONS=10
```

---

## 4. Provedor Gratuito Recomendado: Upstash Redis

Para deploys Serverless (como Vercel, AWS Lambda ou Docker):
* **Cadastro:** [upstash.com](https://upstash.com/) (10.000 requisições/dia gratuitas, sem cartão de crédito).
* **Conexão:** Use sempre a URL com prefixo `rediss://` (TLS habilitado).
