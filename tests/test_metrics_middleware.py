import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from prometheus_client import REGISTRY

from app.core.observability.observability import MetricsMiddleware


@pytest.fixture
def test_app():
    app = FastAPI()
    app.add_middleware(MetricsMiddleware)

    @app.get('/api/items/{item_id}')
    async def get_item(item_id: int):
        return {'item_id': item_id}

    return app


def test_metrics_middleware_normalizes_route(test_app):
    client = TestClient(test_app)

    # Request dynamic route
    response = client.get('/api/items/12345')
    assert response.status_code == 200
    assert response.json() == {'item_id': 12345}

    # Verify counter contains normalized route label
    sample_value = REGISTRY.get_sample_value(
        'http_requests_total',
        labels={
            'endpoint': '/api/items/{item_id}',
            'method': 'GET',
            'status': '200',
        },
    )
    assert sample_value is not None
    assert sample_value >= 1.0


def test_metrics_middleware_groups_unmatched_routes(test_app):
    client = TestClient(test_app)

    # Request non-existent routes
    res1 = client.get('/non-existent-path-1')
    res2 = client.get('/non-existent-path-2')
    assert res1.status_code == 404
    assert res2.status_code == 404

    # Verify both 404s were aggregated under unmatched_route
    sample_value = REGISTRY.get_sample_value(
        'http_requests_total',
        labels={
            'endpoint': 'unmatched_route',
            'method': 'GET',
            'status': '404',
        },
    )
    assert sample_value is not None
    assert sample_value >= 2.0
