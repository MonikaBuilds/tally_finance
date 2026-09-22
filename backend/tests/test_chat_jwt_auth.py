import os
from datetime import datetime, timedelta, timezone

import jwt
import pytest
from fastapi import HTTPException

from app.security.auth import _decode_token


TEST_SECRET = "test-secret-key"
TEST_ALGORITHM = "HS256"


@pytest.fixture(autouse=True)
def configure_jwt_env(monkeypatch):
    monkeypatch.setenv(
        "CHAT_JWT_SECRET",
        TEST_SECRET,
    )
    monkeypatch.setenv(
        "CHAT_JWT_ALGORITHM",
        TEST_ALGORITHM,
    )


def test_valid_token_is_decoded():
    payload = {
        "sub": "user-101",
        "companies": ["ABC Pvt Ltd"],
        "exp": datetime.now(timezone.utc)
        + timedelta(minutes=10),
    }

    token = jwt.encode(
        payload,
        TEST_SECRET,
        algorithm=TEST_ALGORITHM,
    )

    decoded = _decode_token(token)

    assert decoded["sub"] == "user-101"
    assert decoded["companies"] == ["ABC Pvt Ltd"]


def test_invalid_token_is_rejected():
    with pytest.raises(HTTPException) as exc:
        _decode_token("invalid-token")

    assert exc.value.status_code == 401


def test_token_with_wrong_secret_is_rejected():
    payload = {
        "sub": "user-101",
        "companies": ["ABC Pvt Ltd"],
    }

    token = jwt.encode(
        payload,
        "wrong-secret",
        algorithm=TEST_ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc:
        _decode_token(token)

    assert exc.value.status_code == 401


def test_expired_token_is_rejected():
    payload = {
        "sub": "user-101",
        "companies": ["ABC Pvt Ltd"],
        "exp": datetime.now(timezone.utc)
        - timedelta(minutes=1),
    }

    token = jwt.encode(
        payload,
        TEST_SECRET,
        algorithm=TEST_ALGORITHM,
    )

    with pytest.raises(HTTPException) as exc:
        _decode_token(token)

    assert exc.value.status_code == 401


def test_missing_secret_returns_server_error(
    monkeypatch,
):
    monkeypatch.delenv(
        "CHAT_JWT_SECRET",
        raising=False,
    )

    with pytest.raises(HTTPException) as exc:
        _decode_token("some-token")

    assert exc.value.status_code == 500