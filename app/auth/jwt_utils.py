from __future__ import annotations

from datetime import datetime, timedelta, timezone
import logging
import bcrypt
from jose import jwt, JWTError
from app.config import settings

log = logging.getLogger(__name__)

_ALGORITHM = "HS256"
_EXPIRE_DAYS = 7


def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode(), bcrypt.gensalt()).decode()


def verify_password(plain: str, hashed: str) -> bool:
    try:
        return bcrypt.checkpw(plain.encode(), hashed.encode())
    except Exception as e:
        log.error("bcrypt verify_password error: %s", e)
        return False


def create_access_token(employee_id: int) -> str:
    expire = datetime.now(timezone.utc) + timedelta(days=_EXPIRE_DAYS)
    return jwt.encode(
        {"sub": str(employee_id), "exp": expire},
        settings.jwt_secret,
        algorithm=_ALGORITHM,
    )


def decode_access_token(token: str) -> int | None:
    """Return employee_id (sub) from a valid token, or None if invalid/expired."""
    if not settings.jwt_secret:
        return None
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
        sub = payload.get("sub")
        if sub is None:
            return None
        return int(sub)
    except (JWTError, ValueError):
        return None
