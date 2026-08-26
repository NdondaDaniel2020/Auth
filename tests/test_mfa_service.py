from __future__ import annotations

from app.schemas.mfa import (
    MfaChallengeRequest,
    MfaDisableRequest,
    MfaEnableRequest,
    MfaEnableResponse,
    MfaSetupResponse,
)
from app.services.mfa_service import MfaService


def test_mfa_service_generate_secret_and_uri():
    secret = MfaService.generate_totp_secret()
    assert isinstance(secret, str)
    assert len(secret) == 32

    uri = MfaService.get_totp_uri(
        'user@example.com', secret, issuer_name='TestApp'
    )
    assert uri.startswith('otpauth://totp/TestApp:user')
    assert f'secret={secret}' in uri
    assert 'issuer=TestApp' in uri


def test_mfa_service_verify_totp_code():
    import pyotp

    secret = MfaService.generate_totp_secret()
    totp = pyotp.TOTP(secret)
    current_code = totp.now()

    assert MfaService.verify_totp_code(secret, current_code) is True
    assert MfaService.verify_totp_code(secret, '000000') is False
    assert MfaService.verify_totp_code(secret, 'invalid') is False
    assert MfaService.verify_totp_code('', current_code) is False


def test_mfa_service_backup_codes():
    codes = MfaService.generate_backup_codes(count=8)
    assert len(codes) == 8
    assert len(set(codes)) == 8
    for code in codes:
        assert len(code) == 11
        assert '-' in code

    hashed = MfaService.hash_backup_codes(codes)
    assert len(hashed) == 8

    # Verify and consume the first code
    first_code = codes[0]
    valid, remaining = MfaService.verify_and_consume_backup_code(
        first_code, hashed
    )
    assert valid is True
    assert len(remaining) == 7

    # Trying to reuse the same code should fail
    valid_again, remaining_again = MfaService.verify_and_consume_backup_code(
        first_code, remaining
    )
    assert valid_again is False
    assert len(remaining_again) == 7

    # Verify input formatting (without hyphen)
    second_code_no_hyphen = codes[1].replace('-', '')
    valid_second, remaining_second = MfaService.verify_and_consume_backup_code(
        second_code_no_hyphen, remaining
    )
    assert valid_second is True
    assert len(remaining_second) == 6


def test_mfa_schemas_instantiation():
    setup = MfaSetupResponse(
        secret='JBSWY3DPEHPK3PXP', otpauth_uri='otpauth://totp/...'
    )
    assert setup.secret == 'JBSWY3DPEHPK3PXP'

    enable_req = MfaEnableRequest(code='123456')
    assert enable_req.code == '123456'

    enable_resp = MfaEnableResponse(backup_codes=['ABCDE-12345'])
    assert len(enable_resp.backup_codes) == 1

    disable_req = MfaDisableRequest(password='secret123', code='123456')
    assert disable_req.password == 'secret123'

    challenge_req = MfaChallengeRequest(
        mfa_pending_token='jwt.token.here', code='123456'
    )
    assert challenge_req.mfa_pending_token == 'jwt.token.here'
