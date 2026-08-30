from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from app.main import create_app


@pytest.fixture
def client():
    app = create_app()
    return TestClient(app)


def test_liveness_probe_root_live(client):
    response = client.get('/live')
    assert response.status_code == 200
    assert response.json() == {'status': 'alive'}


def test_liveness_probe_api_live(client):
    response = client.get('/api/live')
    assert response.status_code == 200
    assert response.json() == {'status': 'alive'}


@patch('app.main.get_health_status', new_callable=AsyncMock)
def test_health_readiness_probe(mock_health, client):
    mock_health.return_value = {
        'status': 'ok',
        'checks': {'database': {'status': 'ok'}},
    }

    response = client.get('/api/health')
    assert response.status_code == 200
    assert response.json() == {
        'status': 'ok',
        'checks': {'database': {'status': 'ok'}},
    }
