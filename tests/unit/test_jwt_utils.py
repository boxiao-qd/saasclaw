"""Unit tests for app.auth.jwt_utils — hash, verify, JWT encode/decode."""
import logging
from datetime import datetime, timedelta, timezone

import pytest
from jose import jwt

from app.auth.jwt_utils import (
    _ALGORITHM,
    create_access_token,
    decode_access_token,
    hash_password,
    verify_password,
)
from app.config import settings


class TestHashPassword:
    def test_returns_bcrypt_hash(self):
        h = hash_password("mypassword")
        assert h.startswith("$2b$") or h.startswith("$2a$")

    def test_different_salts_per_call(self):
        h1 = hash_password("mypassword")
        h2 = hash_password("mypassword")
        assert h1 != h2


class TestVerifyPassword:
    def test_correct_password(self):
        h = hash_password("secret123")
        assert verify_password("secret123", h) is True

    def test_wrong_password(self):
        h = hash_password("secret123")
        assert verify_password("wrongpass", h) is False

    def test_invalid_hash_returns_false_and_logs_error(self, caplog):
        with caplog.at_level(logging.ERROR, logger="app.auth.jwt_utils"):
            result = verify_password("anypassword", "not-a-valid-hash")
        assert result is False
        assert any(r.levelno == logging.ERROR for r in caplog.records)


class TestCreateAccessToken:
    def test_returns_non_empty_string(self):
        token = create_access_token("testuser")
        assert isinstance(token, str) and len(token) > 0

    def test_sub_claim_matches_username(self):
        token = create_access_token("alice")
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
        assert payload["sub"] == "alice"

    def test_exp_claim_is_present(self):
        token = create_access_token("alice")
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[_ALGORITHM])
        assert "exp" in payload


class TestDecodeAccessToken:
    def test_valid_token_returns_username(self):
        token = create_access_token("bob")
        assert decode_access_token(token) == "bob"

    def test_invalid_token_returns_none(self):
        assert decode_access_token("not.a.valid.token") is None

    def test_expired_token_returns_none(self):
        expired = jwt.encode(
            {"sub": "alice", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
            settings.jwt_secret,
            algorithm=_ALGORITHM,
        )
        assert decode_access_token(expired) is None

    def test_wrong_secret_returns_none(self):
        bad = jwt.encode(
            {"sub": "alice", "exp": datetime.now(timezone.utc) + timedelta(days=1)},
            "wrong_secret",
            algorithm=_ALGORITHM,
        )
        assert decode_access_token(bad) is None

    def test_empty_secret_returns_none(self):
        original = settings.jwt_secret
        settings.jwt_secret = ""
        try:
            token = jwt.encode({"sub": "alice"}, "any", algorithm=_ALGORITHM)
            assert decode_access_token(token) is None
        finally:
            settings.jwt_secret = original
