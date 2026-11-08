import hashlib
import secrets
from datetime import UTC, datetime, timedelta
from typing import Any
from uuid import UUID

import jwt
from pwdlib import PasswordHash
from pwdlib.hashers.argon2 import Argon2Hasher

from app.core.config import get_settings


def _build_password_hasher() -> PasswordHash:
    """Argon2id with library-recommended parameters; a fast profile is used only in APP_ENV=test."""
    if get_settings().app_env == "test":
        return PasswordHash((Argon2Hasher(time_cost=1, memory_cost=8192, parallelism=1),))
    return PasswordHash.recommended()


password_hasher = _build_password_hasher()


def hash_password(raw_password: str) -> str:
    return password_hasher.hash(raw_password)


def verify_password(raw_password: str, password_hash: str) -> bool:
    try:
        return password_hasher.verify(raw_password, password_hash)
    except Exception:
        return False


def generate_secure_token(nbytes: int = 32) -> str:
    return secrets.token_urlsafe(nbytes)


def hash_token(raw_token: str) -> str:
    """Deterministic SHA-256 digest for single-use tokens and refresh tokens.
    Never store raw long-lived refresh, invitation, or recovery tokens in the database.
    """
    return hashlib.sha256(raw_token.encode("utf-8")).hexdigest()


def create_access_token(
    *,
    user_id: UUID,
    tenant_id: UUID | None = None,
    membership_id: UUID | None = None,
    roles: list[str] | None = None,
    is_platform_admin: bool = False,
    expires_delta: timedelta | None = None,
) -> str:
    settings = get_settings()
    now = datetime.now(UTC)
    expire = now + (
        expires_delta
        if expires_delta is not None
        else timedelta(minutes=settings.access_token_expire_minutes)
    )
    payload: dict[str, Any] = {
        "sub": str(user_id),
        "tid": str(tenant_id) if tenant_id else None,
        "mid": str(membership_id) if membership_id else None,
        "roles": roles or [],
        "padm": bool(is_platform_admin),
        "iat": int(now.timestamp()),
        "exp": int(expire.timestamp()),
        "jti": secrets.token_hex(8),
        "type": "access",
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != "access":
        raise jwt.InvalidTokenError("Invalid token type")
    return payload
