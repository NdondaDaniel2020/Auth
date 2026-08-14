"""Unit tests for EventBus retry policy with exponential backoff and DLQ."""

from __future__ import annotations

import pytest

from app.core.events import Event, InMemoryEventBus


@pytest.mark.asyncio
async def test_event_bus_handler_succeeds_first_try() -> None:
    bus = InMemoryEventBus(max_retries=3, initial_delay=0.01)
    call_count = 0

    async def _success_handler(event: dict) -> None:
        nonlocal call_count
        call_count += 1

    await bus.subscribe('test.event', _success_handler)
    event = Event(type='test.event', payload={'data': 'test'})
    await bus.publish(event)

    assert call_count == 1
    dlq = await bus.get_dlq_events()
    assert len(dlq) == 0


@pytest.mark.asyncio
async def test_event_bus_retries_and_succeeds() -> None:
    bus = InMemoryEventBus(
        max_retries=3, initial_delay=0.01, backoff_factor=1.5
    )
    call_count = 0

    async def _flaky_handler(event: dict) -> None:
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise ConnectionError('SMTP server temporary timeout')

    await bus.subscribe('test.flaky', _flaky_handler)
    event = Event(type='test.flaky', payload={'data': 'retry_test'})
    await bus.publish(event)

    assert call_count == 2
    dlq = await bus.get_dlq_events()
    assert len(dlq) == 0


@pytest.mark.asyncio
async def test_event_bus_exhausts_retries_and_pushes_to_dlq() -> None:
    bus = InMemoryEventBus(
        max_retries=3, initial_delay=0.01, backoff_factor=1.5
    )
    call_count = 0

    async def _failing_handler(event: dict) -> None:
        nonlocal call_count
        call_count += 1
        raise RuntimeError('Permanent SMTP error')

    await bus.subscribe('test.failed', _failing_handler)
    event = Event(type='test.failed', payload={'data': 'dlq_test'})
    await bus.publish(event)

    assert call_count == 3
    dlq = await bus.get_dlq_events()
    assert len(dlq) == 1
    assert dlq[0]['event']['type'] == 'test.failed'
    assert dlq[0]['event']['payload'] == {'data': 'dlq_test'}
    assert 'Permanent SMTP error' in dlq[0]['error']


@pytest.mark.asyncio
async def test_event_bus_reprocess_dlq_events() -> None:
    bus = InMemoryEventBus(max_retries=2, initial_delay=0.01)
    should_fail = True
    processed = 0

    async def _handler(event: dict) -> None:
        nonlocal processed
        if should_fail:
            raise ValueError('Temporary error')
        processed += 1

    await bus.subscribe('test.reprocess', _handler)
    event = Event(type='test.reprocess', payload={'msg': 'hello'})

    # 1. Publish while handler fails -> goes to DLQ
    await bus.publish(event)
    assert processed == 0
    dlq = await bus.get_dlq_events()
    assert len(dlq) == 1

    # 2. Fix condition and reprocess DLQ
    should_fail = False
    reprocessed_count = await bus.reprocess_dlq_events()
    assert reprocessed_count == 1
    assert processed == 1

    # DLQ should now be empty
    dlq_after = await bus.get_dlq_events()
    assert len(dlq_after) == 0
