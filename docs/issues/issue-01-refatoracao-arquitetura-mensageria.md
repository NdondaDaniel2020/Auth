# 📋 Issue: Redesenho e Centralização da Arquitetura do Módulo de Mensageria (EDA)

**Tipo:** `Refactor / Architecture`  
**Escopo:** `messaging`  
**Status:** `Proposto / Em Discussão`  

---

## 🎯 Contexto e Declaração do Problema

Atualmente, o sistema de mensageria e eventos da aplicação (`Auth`) possui implementação técnica funcional (suportando retentativas, backoff exponencial, Dead-Letter Queue no Redis e abstração de RabbitMQ/Kafka). No entanto, a organização arquitetural do código apresenta problemas de coesão, acoplamento e espalhamento de responsabilidades:

1. **Mistura de Responsabilidades em `events.py`**: O ficheiro [`app/core/events/events.py`](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/events/events.py) acumula a interface abstrata, a implementação em memória, o gerenciamento de DLQ no Redis e a definição dos nomes dos eventos.
2. **Abstrações Duplicadas e Paralelas**: Existem duas interfaces paralelas para mensageria — `EventBus` em [`events.py`](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/events/events.py) e `BrokerPublisher` em [`broker.py`](file:///spot/NdDaniel/Code/Estudo/Auth/app/core/infrastructure/broker.py) —, gerando dúvida sobre qual abstração utilizar.
3. **Fragmentação de Módulos**: O código de mensageria está espalhado entre `app/core/events/`, `app/core/infrastructure/broker.py`, `app/schemas/notification.py`, `app/services/notification_service.py` e `app/services/websocket_service.py`.
4. **Eventos Fracamente Tipados**: O evento base utiliza `payload: dict[str, Any]`, forçando conversores manuais nos consumidores e perdendo o autocompletar e validação estática de tipos da IDE.

---

## 🏗️ Proposta de Arquitetura Limpa (`app/messaging/`)

Centralizar toda a infraestrutura, contratos, barramentos, eventos tipados e consumidores dentro de um módulo exclusivo e coeso: `app/messaging/`.

```text
app/messaging/
├── __init__.py               # Exporta contratos principais e get_event_bus()
├── base.py                   # Contratos abstratos: Event, DomainEvent, Command, EventBus, EventHandler
├── events/                   # Schemas de Eventos Fortemente Tipados
│   ├── __init__.py
│   ├── auth_events.py        # PasswordResetRequestedEvent, PasswordResetCompletedEvent, etc.
│   └── user_events.py        # UserCreatedEvent, UserDeactivatedEvent, RolesChangedEvent, etc.
├── buses/                    # Implementações do Barramento (Strategy Pattern)
│   ├── __init__.py
│   ├── factory.py             # Instancia o bus correto baseado em BROKER_TYPE
│   ├── in_memory.py          # InMemoryEventBus (Dev / Testes)
│   ├── rabbitmq.py           # RabbitMQEventBus (aio-pika)
│   └── kafka.py              # KafkaEventBus (aiokafka)
├── dlq/                      # Gerenciamento de Mensagens Mortas (Dead-Letter Queue)
│   ├── __init__.py
│   └── redis_dlq.py          # Salva, inspeciona e reprocessa falhas na chave events:dlq
└── consumers/                # Consumidores / Handlers Desacoplados
    ├── __init__.py
    ├── email_consumer.py     # Consome eventos -> delega para email_service
    └── websocket_consumer.py # Consome eventos -> envia frames WebSocket
```

---

## 💡 Distinção Entre Eventos de Domínio e Comandos

* **DomainEvent (Passado / Pub-Sub)**: Representa um fato ocorrido no domínio (`user.created`, `user.deactivated`). Pode ter **múltiplos inscritos** de forma transparente.
* **Command (Imperativo / Point-to-Point)**: Representa uma ordem de ação intencional dirigida a **um único executor** (ex.: `send_email_command`).

---

## 🛠️ Plano de Implementação (Fases & Tarefas)

### Fase 1: Contratos Base & Eventos Tipados
- [ ] Criar `app/messaging/base.py` com `Event`, `DomainEvent`, `Command` e `EventBus(ABC)`.
- [ ] Criar `app/messaging/events/user_events.py` com dataclasses/Pydantic para cada evento de utilizador.
- [ ] Criar `app/messaging/events/auth_events.py` com dataclasses/Pydantic para cada evento de autenticação.

### Fase 2: Refatoração dos Barramentos (Buses) & Factory
- [ ] Mover e refatorar `InMemoryEventBus` para `app/messaging/buses/in_memory.py`.
- [ ] Unificar `RabbitMQPublisher` e `KafkaPublisher` em `RabbitMQEventBus` e `KafkaEventBus` (implementando a interface única `EventBus`).
- [ ] Criar `app/messaging/buses/factory.py` com a função `get_event_bus()`.

### Fase 3: Módulo de DLQ Redis
- [ ] Extrair a lógica de Dead-Letter Queue para `app/messaging/dlq/redis_dlq.py`.
- [ ] Garantir métodos reutilizáveis: `push_to_dlq()`, `get_dlq_messages()`, `requeue_dlq_message()`.

### Fase 4: Extração dos Consumidores (Consumers)
- [ ] Criar `app/messaging/consumers/email_consumer.py` desacoplado dos serviços de negócio.
- [ ] Criar `app/messaging/consumers/websocket_consumer.py` tratando desacoplamento do `WebSocketManager`.

### Fase 5: Integração, Clean-up e Validação
- [ ] Atualizar `user_service.py` e `auth_service.py` para emitirem os novos eventos tipados.
- [ ] Atualizar `app/core/lifespan.py` para inicializar a fábrica de mensageria e consumidores.
- [ ] Remover ficheiros legados em desuso (`app/core/events/events.py` e `app/core/infrastructure/broker.py`).
- [ ] Executar suíte completa de testes (`pytest`) e linters (`ruff check`).

---

## ✅ Critérios de Aceitação (Definition of Done)

1. **Zero Breaking Changes**: Todas as funcionalidades existentes (notificações por e-mail, encerramento de WebSocket em tempo real e retentativas) continuam a funcionar 100%.
2. **Tipagem Forte**: Nenhuma emissão de evento utiliza `dict[str, Any]` genérico.
3. **Interface Única**: `EventBus` é a única interface de barramento da aplicação.
4. **Testes Verificados**: Todos os testes unitários e de integração passam sem regressões (`pytest`).
