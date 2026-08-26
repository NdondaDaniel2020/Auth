from __future__ import annotations

from uuid import uuid4

import pyotp
import pytest
from httpx import ASGITransport, AsyncClient

from app.core.security import decode_access_token
from app.main import create_app

PASSWORD = 'StrongPassword123!'


@pytest.fixture
def app():
    return create_app()


@pytest.mark.asyncio
async def test_full_mfa_flow(app, isolated_session_factory):
    """Test full MFA lifecycle: register -> login -> setup -> enable -> 2-step login -> disable."""
    async with AsyncClient(
        transport=ASGITransport(app=app), base_url='http://test'
    ) as client:
        # 1. Register a user with unique email
        email = f'mfauser_{uuid4().hex[:8]}@example.com'
        reg_res = await client.post(
            '/api/auth/register',
            json={'email': email, 'password': PASSWORD},
        )
        assert reg_res.status_code == 201

        # 2. Initial login (MFA disabled) -> returns access & refresh tokens
        login_res = await client.post(
            '/api/auth/login',
            json={'email': email, 'password': PASSWORD},
        )
        assert login_res.status_code == 200
        data = login_res.json()
        assert data['mfa_required'] is False
        assert data['access_token'] is not None
        token = data['access_token']
        headers = {'Authorization': f'Bearer {token}'}

        # Verify default amr claim in access token
        decoded = decode_access_token(token)
        assert decoded['amr'] == ['pwd']

        # 3. Setup MFA
        setup_res = await client.post('/api/mfa/totp/setup', headers=headers)
        assert setup_res.status_code == 200
        setup_data = setup_res.json()
        secret = setup_data['secret']
        assert len(secret) == 32
        assert setup_data['otpauth_uri'].startswith('otpauth://totp/')

        # 4. Enable MFA with invalid code -> expect 400
        invalid_enable = await client.post(
            '/api/mfa/totp/enable',
            headers=headers,
            json={'code': '000000'},
        )
        assert invalid_enable.status_code == 400

        # 5. Enable MFA with valid code
        totp = pyotp.TOTP(secret)
        valid_code = totp.now()
        enable_res = await client.post(
            '/api/mfa/totp/enable',
            headers=headers,
            json={'code': valid_code},
        )
        assert enable_res.status_code == 200
        enable_data = enable_res.json()
        assert enable_data['message'] == 'MFA ativado com sucesso'
        backup_codes = enable_data['backup_codes']
        assert len(backup_codes) == 8

        # 6. Login again -> expects mfa_required = True and mfa_pending_token
        mfa_login_res = await client.post(
            '/api/auth/login',
            json={'email': email, 'password': PASSWORD},
        )
        assert mfa_login_res.status_code == 200
        mfa_login_data = mfa_login_res.json()
        assert mfa_login_data['mfa_required'] is True
        assert mfa_login_data['mfa_pending_token'] is not None
        pending_token = mfa_login_data['mfa_pending_token']

        # 7. Challenge with invalid TOTP code -> expect 401
        invalid_challenge = await client.post(
            '/api/auth/login/mfa-challenge',
            json={'mfa_pending_token': pending_token, 'code': '111111'},
        )
        assert invalid_challenge.status_code == 401

        # 8. Challenge with valid TOTP code -> returns final tokens with amr: ["pwd", "mfa"]
        valid_totp = totp.now()
        challenge_res = await client.post(
            '/api/auth/login/mfa-challenge',
            json={'mfa_pending_token': pending_token, 'code': valid_totp},
        )
        assert challenge_res.status_code == 200
        final_data = challenge_res.json()
        assert final_data['access_token'] is not None
        mfa_access_token = final_data['access_token']

        decoded_mfa = decode_access_token(mfa_access_token)
        assert decoded_mfa['amr'] == ['pwd', 'mfa']

        # 9. Test Challenge with Backup Code
        mfa_login_2 = await client.post(
            '/api/auth/login',
            json={'email': email, 'password': PASSWORD},
        )
        pending_token_2 = mfa_login_2.json()['mfa_pending_token']

        backup_code = backup_codes[0]
        backup_challenge_res = await client.post(
            '/api/auth/login/mfa-challenge',
            json={'mfa_pending_token': pending_token_2, 'code': backup_code},
        )
        assert backup_challenge_res.status_code == 200

        # 10. Disable MFA
        mfa_headers = {'Authorization': f'Bearer {mfa_access_token}'}
        disable_res = await client.request(
            'DELETE',
            '/api/mfa/totp/disable',
            headers=mfa_headers,
            json={'password': PASSWORD, 'code': totp.now()},
        )
        assert disable_res.status_code == 200
        assert disable_res.json()['message'] == 'MFA desativado com sucesso'

        # 11. Login after disabling -> returns normal access token directly
        final_login = await client.post(
            '/api/auth/login',
            json={'email': email, 'password': PASSWORD},
        )
        assert final_login.status_code == 200
        assert final_login.json()['mfa_required'] is False
