from __future__ import annotations

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import Any

from jose import jwt
from passlib.context import CryptContext

from app.core.config import get_settings

settings = get_settings()
pwd_context = CryptContext(schemes=["bcrypt_sha256", "bcrypt"], deprecated=["bcrypt"])
ALGORITHM = "HS256"


def hash_password(password: str) -> str:
    return pwd_context.hash(password)


def verify_password(plain_password: str, hashed_password: str) -> bool:
    try:
        return pwd_context.verify(plain_password, hashed_password)
    except ValueError:
        return False


def verify_and_update_password(plain_password: str, hashed_password: str) -> tuple[bool, str | None]:
    try:
        return pwd_context.verify_and_update(plain_password, hashed_password)
    except ValueError:
        return False, None


def create_token(payload: dict[str, Any], expires_delta: timedelta, token_type: str) -> str:
    now = datetime.now(timezone.utc)
    data = payload.copy()
    data.update(
        {
            "iat": int(now.timestamp()),
            "exp": int((now + expires_delta).timestamp()),
            "typ": token_type,
            "iss": settings.app_name,
            "aud": "apprentissage-langue-users",
            "jti": secrets.token_urlsafe(16),
        }
    )
    return jwt.encode(data, settings.secret_key, algorithm=ALGORITHM)


def decode_token(token: str) -> dict[str, Any]:
    return jwt.decode(
        token,
        settings.secret_key,
        algorithms=[ALGORITHM],
        issuer=settings.app_name,
        audience="apprentissage-langue-users",
        options={"verify_sub": False},
    )


def create_access_token(payload: dict[str, Any]) -> str:
    return create_token(payload, timedelta(minutes=settings.access_token_exp_minutes), "access")


def create_refresh_token(payload: dict[str, Any]) -> str:
    return create_token(payload, timedelta(days=settings.refresh_token_exp_days), "refresh")


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()
