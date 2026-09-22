from fastapi.testclient import TestClient

import app.api.chat as chat_api
from app.main import app


client = TestClient(app)


def test_write_request_is_blocked():
    response = client.post(
        "/api/v1/chat",
        json={
            "message": "Delete invoice 1",
            "company_name": None
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["success"] is False
    assert data["intent"] == "write_operation"
    assert data["source"] is None


def test_empty_message_is_rejected():
    response = client.post(
        "/api/v1/chat",
        json={
            "message": "",
            "company_name": None
        }
    )

    assert response.status_code in (
        200,
        422
    )


def test_missing_message_is_rejected():
    response = client.post(
        "/api/v1/chat",
        json={
            "company_name": None
        }
    )

    assert response.status_code == 422


def test_chat_api_returns_expected_structure(
    monkeypatch
):
    async def fake_process_chat_message(
        message,
        company_name=None
    ):
        return {
            "success": True,
            "answer": (
                "Your total outstanding payables "
                "are ₹5,00,000."
            ),
            "intent": "get_payables",
            "source": "tally",
            "data": {
                "total_payable": 500000
            }
        }

    monkeypatch.setattr(
        chat_api,
        "process_chat_message",
        fake_process_chat_message
    )

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "What are my payables?",
            "company_name": None
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["success"] is True
    assert data["intent"] == "get_payables"
    assert data["source"] == "tally"
    assert (
        data["data"]["total_payable"]
        == 500000
    )


def test_tally_failure_is_returned_safely(
    monkeypatch
):
    async def fake_process_chat_message(
        message,
        company_name=None
    ):
        return {
            "success": False,
            "answer": (
                "Unable to retrieve the requested "
                "financial data from Tally right now."
            ),
            "intent": "get_payables",
            "source": "tally",
            "data": None
        }

    monkeypatch.setattr(
        chat_api,
        "process_chat_message",
        fake_process_chat_message
    )

    response = client.post(
        "/api/v1/chat",
        json={
            "message": "What are my payables?",
            "company_name": None
        }
    )

    assert response.status_code == 200

    data = response.json()

    assert data["success"] is False
    assert data["source"] == "tally"
    assert data["data"] is None
    assert (
        "Unable to retrieve"
        in data["answer"]
    )