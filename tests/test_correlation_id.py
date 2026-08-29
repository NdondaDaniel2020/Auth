import io
import json
import logging

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.core.observability.context import (
    get_request_id,
    get_user_id,
    set_request_id,
    set_user_id,
)
from app.core.observability.observability import JSONFormatter
from app.core.web.middleware import setup_correlation_id_middleware
from app.messaging.base import Event
from app.messaging.buses.in_memory import InMemoryEventBus


@pytest.fixture
def app_with_correlation_id():
    app = FastAPI()
    setup_correlation_id_middleware(app)

    @app.get('/api/test-context')
    async def test_endpoint():
        return {
            'current_request_id': get_request_id(),
            'current_user_id': get_user_id(),
        }

    return app


def test_correlation_id_generated_and_returned_in_headers(
    app_with_correlation_id,
):
    client = TestClient(app_with_correlation_id)
    response = client.get('/api/test-context')

    assert response.status_code == 200
    header_request_id = response.headers.get('X-Request-ID')
    assert header_request_id is not None
    assert len(header_request_id) > 0
    assert response.json()['current_request_id'] == header_request_id


def test_correlation_id_preserved_when_provided(app_with_correlation_id):
    client = TestClient(app_with_correlation_id)
    custom_id = 'trace-uuid-12345-abcde'
    response = client.get(
        '/api/test-context', headers={'X-Request-ID': custom_id}
    )

    assert response.status_code == 200
    assert response.headers.get('X-Request-ID') == custom_id
    assert response.json()['current_request_id'] == custom_id


def test_json_formatter_includes_request_id_and_user_id():
    log_capture = io.StringIO()
    handler = logging.StreamHandler(log_capture)
    formatter = JSONFormatter('%(message)s')
    handler.setFormatter(formatter)

    logger = logging.getLogger('test_correlation_logger')
    logger.handlers = [handler]
    logger.setLevel(logging.INFO)

    # Set context
    set_request_id('req-999')
    set_user_id('user-42')

    try:
        logger.info('Test log message with context')
    finally:
        set_request_id(None)
        set_user_id(None)

    log_output = log_capture.getvalue().strip()
    log_data = json.loads(log_output)

    assert log_data['message'] == 'Test log message with context'
    assert log_data['request_id'] == 'req-999'
    assert log_data['user_id'] == 'user-42'
    assert log_data['service'] == 'auth-api'


@pytest.mark.asyncio
async def test_event_bus_propagates_and_restores_correlation_id():
    bus = InMemoryEventBus()
    captured_context_ids = []

    async def sample_handler(event: Event):
        captured_context_ids.append(get_request_id())

    await bus.subscribe('test.event', sample_handler)

    # Simulate running inside request context
    set_request_id('ctx-trace-event-777')
    try:
        event = Event(type='test.event', payload={'data': 'sample'})
        assert event.correlation_id == 'ctx-trace-event-777'
    finally:
        set_request_id(None)

    # Context is now cleared outside, but publish will restore it inside handler
    await bus.publish(event)

    assert len(captured_context_ids) == 1
    assert captured_context_ids[0] == 'ctx-trace-event-777'
