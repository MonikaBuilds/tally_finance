import pytest

import app.chatbot.gemini_client as gemini_client


class FakeFunctionCall:
    def __init__(
        self,
        name=None,
        args=None
    ):
        self.name = name
        self.args = args or {}


class FakeResponse:
    def __init__(
        self,
        function_name=None,
        arguments=None
    ):
        if function_name:
            self.function_calls = [
                FakeFunctionCall(
                    name=function_name,
                    args=arguments or {}
                )
            ]
        else:
            self.function_calls = []


class FakeModels:
    def __init__(
        self,
        response
    ):
        self.response = response

    def generate_content(
        self,
        **kwargs
    ):
        return self.response


class FakeClient:
    def __init__(
        self,
        response
    ):
        self.models = FakeModels(
            response
        )


async def run_selection_with_mock(
    monkeypatch,
    question,
    tool_name,
    arguments=None
):
    fake_response = FakeResponse(
        function_name=tool_name,
        arguments=arguments
    )

    fake_client = FakeClient(
        fake_response
    )

    monkeypatch.setattr(
        gemini_client,
        "client",
        fake_client
    )

    return await gemini_client.select_tool(
        question
    )


@pytest.mark.asyncio
async def test_select_payables_tool(
    monkeypatch
):
    result = await run_selection_with_mock(
        monkeypatch,
        "What are my total payables?",
        "get_payables"
    )

    assert result["tool_name"] == "get_payables"


@pytest.mark.asyncio
async def test_select_highest_payable_tool(
    monkeypatch
):
    result = await run_selection_with_mock(
        monkeypatch,
        "Kiska payable sabse jyada hai?",
        "get_highest_payable"
    )

    assert (
        result["tool_name"]
        == "get_highest_payable"
    )


@pytest.mark.asyncio
async def test_select_receivables_tool(
    monkeypatch
):
    result = await run_selection_with_mock(
        monkeypatch,
        "How much money do customers owe us?",
        "get_receivables"
    )

    assert (
        result["tool_name"]
        == "get_receivables"
    )


@pytest.mark.asyncio
async def test_select_highest_receivable_tool(
    monkeypatch
):
    result = await run_selection_with_mock(
        monkeypatch,
        "Which customer owes us the most?",
        "get_highest_receivable"
    )

    assert (
        result["tool_name"]
        == "get_highest_receivable"
    )


@pytest.mark.asyncio
async def test_select_pending_invoices_tool(
    monkeypatch
):
    result = await run_selection_with_mock(
        monkeypatch,
        "Show me the pending invoices.",
        "get_pending_invoices"
    )

    assert (
        result["tool_name"]
        == "get_pending_invoices"
    )


@pytest.mark.asyncio
async def test_select_overdue_receivables_tool(
    monkeypatch
):
    result = await run_selection_with_mock(
        monkeypatch,
        "Show overdue customer payments.",
        "get_overdue_receivables"
    )

    assert (
        result["tool_name"]
        == "get_overdue_receivables"
    )


@pytest.mark.asyncio
async def test_select_overdue_payables_tool(
    monkeypatch
):
    result = await run_selection_with_mock(
        monkeypatch,
        "Which supplier payments are overdue?",
        "get_overdue_payables"
    )

    assert (
        result["tool_name"]
        == "get_overdue_payables"
    )


@pytest.mark.asyncio
async def test_select_aged_receivables_tool(
    monkeypatch
):
    result = await run_selection_with_mock(
        monkeypatch,
        "Show receivables overdue by 30 days.",
        "get_aged_receivables",
        {
            "minimum_days": 30
        }
    )

    assert (
        result["tool_name"]
        == "get_aged_receivables"
    )

    assert (
        result["arguments"]["minimum_days"]
        == 30
    )


@pytest.mark.asyncio
async def test_select_aged_payables_tool(
    monkeypatch
):
    result = await run_selection_with_mock(
        monkeypatch,
        "Show supplier dues overdue by 60 days.",
        "get_aged_payables",
        {
            "minimum_days": 60
        }
    )

    assert (
        result["tool_name"]
        == "get_aged_payables"
    )

    assert (
        result["arguments"]["minimum_days"]
        == 60
    )


@pytest.mark.asyncio
async def test_unsupported_question_has_no_tool(
    monkeypatch
):
    fake_response = FakeResponse()

    fake_client = FakeClient(
        fake_response
    )

    monkeypatch.setattr(
        gemini_client,
        "client",
        fake_client
    )

    result = await gemini_client.select_tool(
        "What is the weather today?"
    )

    assert result["tool_name"] is None