import pytest

import app.chatbot.service as chatbot_service


@pytest.mark.asyncio
async def test_payables_question_uses_payables_tool(
    monkeypatch
):
    async def fake_select_tool(message):
        return {
            "tool_name": "get_payables",
            "arguments": {}
        }

    async def fake_execute_tool(
        tool_name,
        arguments,
        user_id=None
    ):
        assert tool_name == "get_payables"

        return {
            "success": True,
            "source": "tally",
            "data": {
                "total_payable": 500000,
                "count": 2,
                "bills": []
            }
        }

    monkeypatch.setattr(
        chatbot_service,
        "select_tool",
        fake_select_tool
    )

    monkeypatch.setattr(
        chatbot_service,
        "execute_tool",
        fake_execute_tool
    )

    result = await chatbot_service.process_chat_message(
        "What are my payables?"
    )

    assert result["success"] is True
    assert result["intent"] == "get_payables"
    assert result["source"] == "tally"
    assert "₹5,00,000" in result["answer"]


@pytest.mark.asyncio
async def test_highest_payable_response(
    monkeypatch
):
    async def fake_select_tool(message):
        return {
            "tool_name": "get_highest_payable",
            "arguments": {}
        }

    async def fake_execute_tool(
        tool_name,
        arguments,
        user_id=None,
    ):
        return {
            "success": True,
            "source": "tally",
            "data": {
                "party": "Test Supplier",
                "amount": 750000,
                "bill_reference": "TEST-001",
                "due_date": "01-04-2025",
                "overdue_days": 10
            }
        }

    # Force this unit test to use the mocked AI tool selector
    # instead of the real local intent router.
    monkeypatch.setattr(
        chatbot_service,
        "detect_local_intent",
        lambda message: None,
    )

    monkeypatch.setattr(
        chatbot_service,
        "select_tool",
        fake_select_tool
    )

    monkeypatch.setattr(
        chatbot_service,
        "execute_tool",
        fake_execute_tool
    )

    result = await chatbot_service.process_chat_message(
        "Kiska payable sabse jyada hai?"
    )

    assert result["success"] is True
    assert result["intent"] == "get_highest_payable"
    assert "Test Supplier" in result["answer"]
    assert "₹7,50,000" in result["answer"]


@pytest.mark.asyncio
async def test_company_name_is_passed_to_tool(
    monkeypatch
):
    async def fake_select_tool(message):
        return {
            "tool_name": "get_payables",
            "arguments": {}
        }

    async def fake_execute_tool(
        tool_name,
        arguments,
        user_id=None,
    ):
        assert arguments["company_name"] == "Demo Company"

        return {
            "success": True,
            "source": "tally",
            "data": {
                "total_payable": 100000,
                "count": 1,
                "bills": []
            }
        }

    monkeypatch.setattr(
        chatbot_service,
        "select_tool",
        fake_select_tool
    )

    monkeypatch.setattr(
        chatbot_service,
        "execute_tool",
        fake_execute_tool
    )

    result = await chatbot_service.process_chat_message(
        message="What are my payables?",
        company_name="Demo Company"
    )

    assert result["success"] is True


@pytest.mark.asyncio
async def test_tally_failure_does_not_hallucinate(
    monkeypatch
):
    async def fake_select_tool(message):
        return {
            "tool_name": "get_payables",
            "arguments": {}
        }

    async def fake_execute_tool(
        tool_name,
        arguments,
        user_id=None,
    ):
        return {
            "success": False,
            "source": "tally",
            "message": (
                "Unable to retrieve the requested "
                "financial data from Tally right now."
            ),
            "data": None
        }

    monkeypatch.setattr(
        chatbot_service,
        "select_tool",
        fake_select_tool
    )

    monkeypatch.setattr(
        chatbot_service,
        "execute_tool",
        fake_execute_tool
    )

    result = await chatbot_service.process_chat_message(
        "What are my payables?"
    )

    assert result["success"] is False
    assert result["source"] == "tally"
    assert result["data"] is None
    assert "Unable to retrieve" in result["answer"]


@pytest.mark.asyncio
async def test_unsupported_question_does_not_call_tool(
    monkeypatch
):
    async def fake_select_tool(message):
        return {
            "tool_name": None,
            "arguments": {}
        }

    monkeypatch.setattr(
        chatbot_service,
        "select_tool",
        fake_select_tool
    )

    result = await chatbot_service.process_chat_message(
        "What is the weather today?"
    )

    assert result["success"] is False
    assert result["intent"] == "unsupported"
    assert result["source"] is None
    assert result["data"] is None