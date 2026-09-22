import pytest

from app.chatbot.service import process_chat_message


@pytest.mark.asyncio
async def test_delete_request_is_blocked():
    result = await process_chat_message(
        "Delete invoice 1"
    )

    assert result["success"] is False
    assert result["intent"] == "write_operation"
    assert result["source"] is None
    assert result["data"] is None


@pytest.mark.asyncio
async def test_update_request_is_blocked():
    result = await process_chat_message(
        "Update the payable amount to 50000"
    )

    assert result["success"] is False
    assert result["intent"] == "write_operation"


@pytest.mark.asyncio
async def test_create_request_is_blocked():
    result = await process_chat_message(
        "Create a new payment voucher"
    )

    assert result["success"] is False
    assert result["intent"] == "write_operation"