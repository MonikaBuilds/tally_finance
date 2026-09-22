import uuid
from pathlib import Path

import jwt
from fastapi.testclient import TestClient

from app.main import app
from app.security.user_store import (
    create_user,
    initialize_user_store,
)


TEST_DB_DIRECTORY = Path(__file__).parent / ".test_data"


def _setup_test_auth(monkeypatch):
    """
    Create an isolated SQLite authentication database for each test.

    The database is stored inside the project test directory instead
    of the Windows temporary directory.
    """
    TEST_DB_DIRECTORY.mkdir(
        parents=True,
        exist_ok=True,
    )

    db_path = (
        TEST_DB_DIRECTORY
        / f"chat_auth_{uuid.uuid4().hex}.db"
    )

    monkeypatch.setenv(
        "CHAT_AUTH_DB_PATH",
        str(db_path),
    )
    monkeypatch.setenv(
        "CHAT_JWT_SECRET",
        "test-secret-key-for-chatbot-authentication-only",
    )
    monkeypatch.setenv(
        "CHAT_JWT_ALGORITHM",
        "HS256",
    )
    monkeypatch.setenv(
        "CHAT_JWT_EXPIRE_MINUTES",
        "60",
    )

    initialize_user_store()

    create_user(
        user_id="test-user-001",
        username="monika-test",
        password="TestPassword123",
        companies=["ABC Pvt Ltd"],
    )

    return db_path


def _cleanup_test_db(db_path: Path):
    """
    Test databases are intentionally left in .test_data during
    the test run.

    The directory is ignored by Git, so these temporary databases
    are never committed to the repository.

    Avoid deleting them immediately on Windows because SQLite or
    another process may still briefly hold a file handle.
    """
    return


def test_login_with_valid_credentials(monkeypatch):
    db_path = _setup_test_auth(monkeypatch)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "username": "monika-test",
                    "password": "TestPassword123",
                },
            )

        assert response.status_code == 200

        data = response.json()

        assert data["token_type"] == "bearer"
        assert data["user_id"] == "test-user-001"
        assert data["username"] == "monika-test"
        assert data["companies"] == ["ABC Pvt Ltd"]
        assert data["access_token"]

    finally:
        _cleanup_test_db(db_path)


def test_login_token_contains_user_permissions(monkeypatch):
    db_path = _setup_test_auth(monkeypatch)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "username": "monika-test",
                    "password": "TestPassword123",
                },
            )

        assert response.status_code == 200

        token = response.json()["access_token"]

        payload = jwt.decode(
            token,
            "test-secret-key-for-chatbot-authentication-only",
            algorithms=["HS256"],
        )

        assert payload["sub"] == "test-user-001"
        assert payload["companies"] == ["ABC Pvt Ltd"]
        assert "iat" in payload
        assert "exp" in payload

    finally:
        _cleanup_test_db(db_path)


def test_login_with_wrong_password(monkeypatch):
    db_path = _setup_test_auth(monkeypatch)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "username": "monika-test",
                    "password": "WrongPassword",
                },
            )

        assert response.status_code == 401
        assert response.json()["detail"] == (
            "Invalid username or password."
        )

    finally:
        _cleanup_test_db(db_path)


def test_login_with_unknown_user(monkeypatch):
    db_path = _setup_test_auth(monkeypatch)

    try:
        with TestClient(app) as client:
            response = client.post(
                "/api/v1/auth/login",
                json={
                    "username": "unknown-user",
                    "password": "TestPassword123",
                },
            )

        assert response.status_code == 401
        assert response.json()["detail"] == (
            "Invalid username or password."
        )

    finally:
        _cleanup_test_db(db_path)