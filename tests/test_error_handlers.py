from fastapi import Body, FastAPI
from fastapi.testclient import TestClient

from app.core.error_handlers import register_exception_handlers
from app.core.exceptions import BusinessRuleError, NotFoundError


def create_test_app() -> FastAPI:
    app = FastAPI()
    register_exception_handlers(app)

    @app.get('/not-found')
    def _not_found():
        raise NotFoundError('item not found')

    @app.get('/business')
    def _business():
        raise BusinessRuleError(
            'cannot do that', payload={'reason': 'constraint'}
        )

    @app.post('/validate')
    def _validate(payload: dict = Body(...)):
        # expects JSON object; pydantic will validate missing body
        return {'ok': True}

    @app.get('/boom')
    def _boom():
        raise RuntimeError('boom')

    return app


def test_not_found_handler():
    app = create_test_app()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.get('/not-found')
    assert r.status_code == 404
    assert r.json()['error']['message'] == 'item not found'
    assert r.json()['error']['type'] == 'NotFoundError'


def test_business_handler():
    app = create_test_app()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.get('/business')
    assert r.status_code == 400
    body = r.json()
    assert body['error']['message'] == 'cannot do that'
    assert body['error']['details']['reason'] == 'constraint'


def test_validation_handler():
    app = create_test_app()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.post('/validate', json=None)
    assert r.status_code == 422
    body = r.json()
    assert body['error']['type'] == 'RequestValidationError'


def test_generic_exception_hides_details():
    app = create_test_app()
    client = TestClient(app, raise_server_exceptions=False)

    r = client.get('/boom')
    assert r.status_code == 500
    body = r.json()
    assert body['error']['message'] == 'Internal server error'
    # should not include exception text in the public error message
    assert 'boom' not in body['error']['message']
