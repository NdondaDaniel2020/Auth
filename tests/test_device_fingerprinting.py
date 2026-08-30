from __future__ import annotations

from unittest.mock import MagicMock

from app.core.device import extract_client_ip, parse_user_agent


def test_parse_user_agent_known_browsers_and_os():
    # macOS + Chrome
    ua_mac_chrome = (
        'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36'
    )
    assert parse_user_agent(ua_mac_chrome) == 'Chrome no macOS'

    # iPhone + Safari
    ua_ios_safari = (
        'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5 like Mac OS X) '
        'AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1'
    )
    assert parse_user_agent(ua_ios_safari) == 'Safari no iPhone'

    # Windows + Edge
    ua_win_edge = (
        'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
        'AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36 Edg/128.0.0.0'
    )
    assert parse_user_agent(ua_win_edge) == 'Edge no Windows'

    # Linux + Firefox
    ua_linux_firefox = 'Mozilla/5.0 (X11; Ubuntu; Linux x86_64; rv:129.0) Gecko/20100101 Firefox/129.0'
    assert parse_user_agent(ua_linux_firefox) == 'Firefox no Linux'

    # Postman
    assert parse_user_agent('PostmanRuntime/7.39.0') == 'Postman'

    # cURL
    assert parse_user_agent('curl/8.4.0') == 'cURL'

    # Desconhecido / Vazio
    assert parse_user_agent(None) == 'Dispositivo Desconhecido'
    assert parse_user_agent('') == 'Dispositivo Desconhecido'
    assert parse_user_agent('   ') == 'Dispositivo Desconhecido'


def test_extract_client_ip():
    # Sem request
    assert extract_client_ip(None) is None

    # X-Forwarded-For com múltiplos IPs
    req_forwarded = MagicMock()
    req_forwarded.headers = {
        'x-forwarded-for': '203.0.113.195, 70.41.3.18, 150.172.238.178'
    }
    assert extract_client_ip(req_forwarded) == '203.0.113.195'

    # X-Real-IP
    req_real = MagicMock()
    req_real.headers = {'x-real-ip': '198.51.100.22'}
    assert extract_client_ip(req_real) == '198.51.100.22'

    # client.host fallback
    req_host = MagicMock()
    req_host.headers = {}
    req_host.client.host = '192.168.1.50'
    assert extract_client_ip(req_host) == '192.168.1.50'


def test_session_management_flow(full_client):
    email = 'session_test@example.com'
    password = 'T3st!Passw0rd'

    # Registrar usuário
    reg = full_client.post(
        '/auth/register',
        json={'email': email, 'password': password},
    )
    assert reg.status_code == 201

    # 1. Realizar Login 1 (Desktop macOS Chrome)
    login_res_1 = full_client.post(
        '/auth/login',
        json={'email': email, 'password': password},
        headers={
            'User-Agent': (
                'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) '
                'Chrome/128.0.0.0 Safari/537.36'
            ),
            'X-Forwarded-For': '187.30.20.10',
        },
    )
    assert login_res_1.status_code == 200
    data_1 = login_res_1.json()
    token_1 = data_1['access_token']
    refresh_1 = data_1['refresh_token']

    # 2. Realizar Login 2 (iPhone Safari)
    login_res_2 = full_client.post(
        '/auth/login',
        json={'email': email, 'password': password},
        headers={
            'User-Agent': (
                'Mozilla/5.0 (iPhone; CPU iPhone OS 17_5) Safari/604.1'
            ),
            'X-Forwarded-For': '177.10.5.2',
        },
    )
    assert login_res_2.status_code == 200
    data_2 = login_res_2.json()
    refresh_2 = data_2['refresh_token']

    # 3. Listar Sessões pelo Token 1 (GET /users/me/sessions)
    sessions_res = full_client.get(
        '/users/me/sessions',
        headers={'Authorization': f'Bearer {token_1}'},
    )
    assert sessions_res.status_code == 200
    sessions_data = sessions_res.json()
    assert sessions_data['total'] >= 2

    device_names = [s['device_name'] for s in sessions_data['sessions']]
    assert any('Chrome no macOS' in d for d in device_names if d)
    assert any('Safari no iPhone' in d for d in device_names if d)

    # Encontrar a sessão do iPhone para revogar
    iphone_session = next(
        s
        for s in sessions_data['sessions']
        if s.get('device_name') == 'Safari no iPhone'
    )
    iphone_jti = iphone_session['jti']

    # 4. Revogar a sessão do iPhone usando o Token 1 (DELETE /users/me/sessions/{jti})
    revoke_res = full_client.delete(
        f'/users/me/sessions/{iphone_jti}',
        headers={'Authorization': f'Bearer {token_1}'},
    )
    assert revoke_res.status_code == 200
    assert revoke_res.json()['revoked_count'] == 1

    # 5. Tentar usar o Refresh Token do iPhone (deve falhar pois foi revogado)
    refresh_fail = full_client.post(
        '/auth/refresh',
        json={'refresh_token': refresh_2},
    )
    assert refresh_fail.status_code == 401

    # 6. Usar o Refresh Token do Desktop (deve funcionar normalmente)
    refresh_ok = full_client.post(
        '/auth/refresh',
        json={'refresh_token': refresh_1},
    )
    assert refresh_ok.status_code == 200

    # 7. Tentar revogar sessão inexistente ou já revogada (deve retornar 404)
    revoke_again = full_client.delete(
        f'/users/me/sessions/{iphone_jti}',
        headers={'Authorization': f'Bearer {token_1}'},
    )
    assert revoke_again.status_code == 404


def test_revoke_all_sessions_endpoint(full_client):
    email = 'revoke_all@example.com'
    password = 'T3st!Passw0rd'

    # Registrar
    full_client.post(
        '/auth/register',
        json={'email': email, 'password': password},
    )

    # Login 1
    log1 = full_client.post(
        '/auth/login',
        json={'email': email, 'password': password},
    ).json()

    # Login 2
    log2 = full_client.post(
        '/auth/login',
        json={'email': email, 'password': password},
    ).json()

    # Revogar todas as sessões
    revoke_all_res = full_client.delete(
        '/users/me/sessions',
        headers={'Authorization': f'Bearer {log1["access_token"]}'},
    )
    assert revoke_all_res.status_code == 200

    # Ambas as sessões de refresh devem estar revogadas
    assert (
        full_client.post(
            '/auth/refresh',
            json={'refresh_token': log1['refresh_token']},
        ).status_code
        == 401
    )
    assert (
        full_client.post(
            '/auth/refresh',
            json={'refresh_token': log2['refresh_token']},
        ).status_code
        == 401
    )
