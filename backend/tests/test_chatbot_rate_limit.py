import pytest

import app.chatbot.service as chatbot_service


@pytest.mark.asyncio
async def test_gemini_rate_limit_is_handled(
    monkeypatch
):
    async def fake_select_tool(message):
        return {
            "tool_name": None,
            "arguments": {},
            "error": "rate_limit"
        }

    monkeypatch.setattr(
        chatbot_service,
        "select_tool",
        fake_select_tool
    )

    result = await chatbot_service.process_chat_message(
        "What are my payables?"
    )

    assert result["success"] is False
    assert result["intent"] == "model_rate_limit"
    assert result["source"] is None
    assert result["data"] is None
    assert "temporarily busy" in result["answer"]


@pytest.mark.asyncio
async def test_gemini_authentication_error_is_handled(
    monkeypatch
):
    async def fake_select_tool(message):
        return {
            "tool_name": None,
            "arguments": {},
            "error": "authentication"
        }

    monkeypatch.setattr(
        chatbot_service,
        "select_tool",
        fake_select_tool
    )

    result = await chatbot_service.process_chat_message(
        "What are my payables?"
    )

    assert result["success"] is False
    assert (
        result["intent"]
        == "model_authentication_error"
    )
    assert result["source"] is None


@pytest.mark.asyncio
async def test_model_unavailable_is_handled(
    monkeypatch
):
    async def fake_select_tool(message):
        return {
            "tool_name": None,
            "arguments": {},
            "error": "model_unavailable"
        }

    monkeypatch.setattr(
        chatbot_service,
        "select_tool",
        fake_select_tool
    )

    result = await chatbot_service.process_chat_message(
        "What are my payables?"
    )

    assert result["success"] is False
    assert result["intent"] == "model_error"
    assert result["source"] is None