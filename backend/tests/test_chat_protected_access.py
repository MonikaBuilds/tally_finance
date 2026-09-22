import jwt
from fastapi.testclient import TestClient

from app.main import app
import app.api.chat as chat_api


TEST_SECRET = (
    "test-chatbot-jwt-secret-key-that-is-long-enough-123456"
)


def _create_token(
    user_id: str,
    companies: list[str],
) -> str:
    return jwt.encode(
        {
            "sub": user_id,
            "companies": companies,
        },
        TEST_SECRET,
        algorithm="HS256",
    )


def _enable_auth(monkeypatch):
    monkeypatch.setenv(
        "CHAT_AUTH_ENABLED",
        "true",
    )
    monkeypatch.setenv(
        "CHAT_JWT_SECRET",
        TEST_SECRET,
    )
    monkeypatch.setenv(
        "CHAT_JWT_ALGORITHM",
        "HS256",
    )


def test_chat_rejects_request_without_token(
    monkeypatch,
):
    _enable_auth(monkeypatch)

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            json={
                "message": "What is my cash balance?",
                "company_name": "ABC Pvt Ltd",
            },
        )

    assert response.status_code == 401
    assert response.json()["detail"] == (
        "Authentication required."
    )


def test_chat_accepts_valid_user(
    monkeypatch,
):
    _enable_auth(monkeypatch)

    async def fake_process_chat_message(
        message,
        company_name=None,
    ):
        return {
            "success": True,
            "answer": "Your cash balance is available.",
            "intent": "get_cash_balance",
            "source": "tally",
            "data": {
                "company": company_name,
            },
        }

    monkeypatch.setattr(
        chat_api,
        "process_chat_message",
        fake_process_chat_message,
    )

    token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "message": "What is my cash balance?",
                "company_name": "ABC Pvt Ltd",
            },
        )

    assert response.status_code == 200

    data = response.json()

    assert data["success"] is True
    assert data["data"]["company"] == "ABC Pvt Ltd"


def test_chat_blocks_unauthorized_company(
    monkeypatch,
):
    _enable_auth(monkeypatch)

    token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "message": "What is my cash balance?",
                "company_name": "XYZ Pvt Ltd",
            },
        )

    assert response.status_code == 403
    assert response.json()["detail"] == (
        "You are not authorized to access this company."
    )


def test_single_company_is_selected_automatically(
    monkeypatch,
):
    _enable_auth(monkeypatch)

    received_company = None

    async def fake_process_chat_message(
        message,
        company_name=None,
    ):
        nonlocal received_company
        received_company = company_name

        return {
            "success": True,
            "answer": "Financial data retrieved.",
            "intent": "get_cash_balance",
            "source": "tally",
            "data": {},
        }

    monkeypatch.setattr(
        chat_api,
        "process_chat_message",
        fake_process_chat_message,
    )

    token = _create_token(
        user_id="user-001",
        companies=["ABC Pvt Ltd"],
    )

    with TestClient(app) as client:
        response = client.post(
            "/api/v1/chat",
            headers={
                "Authorization": f"Bearer {token}",
            },
            json={
                "message": "What is my cash balance?",
                "company_name": None,
            },
        )

    assert response.status_code == 200
    assert received_company == "ABC Pvt Ltd"