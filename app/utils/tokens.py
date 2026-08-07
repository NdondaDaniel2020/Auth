from __future__ import annotations

import hashlib
import secrets


def generate_opaque_token() -> str:
    """Generate a high-entropy, URL-safe opaque token (e.g. 32 random bytes)."""
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    """Return the SHA-256 hex digest of a token for safe storage."""
    return hashlib.sha256(token.encode('utf-8')).hexdigest()
