import pytest

from app.chatbot import tools


@pytest.mark.asyncio
async def test_top_receivables(
    monkeypatch
):
    async def mock_load_receivables(
        company_name=None
    ):
        return {
            "bills": [
                {
                    "party": "Party A",
                    "bill_reference": "A-1",
                    "outstanding_amount": 10000
                },
                {
                    "party": "Party B",
                    "bill_reference": "B-1",
                    "outstanding_amount": 50000
                },
                {
                    "party": "Party C",
                    "bill_reference": "C-1",
                    "outstanding_amount": 30000
                }
            ]
        }

    monkeypatch.setattr(
        tools,
        "_load_receivables",
        mock_load_receivables
    )

    result = await tools.get_top_receivables_tool(
        limit=2
    )

    assert result["success"] is True

    bills = result["data"]["bills"]

    assert len(bills) == 2
    assert bills[0]["party"] == "Party B"
    assert bills[1]["party"] == "Party C"


@pytest.mark.asyncio
async def test_top_payables(
    monkeypatch
):
    async def mock_load_payables(
        company_name=None
    ):
        return {
            "bills": [
                {
                    "party": "Supplier A",
                    "bill_reference": "P-1",
                    "outstanding_amount": 15000
                },
                {
                    "party": "Supplier B",
                    "bill_reference": "P-2",
                    "outstanding_amount": 75000
                },
                {
                    "party": "Supplier C",
                    "bill_reference": "P-3",
                    "outstanding_amount": 40000
                }
            ]
        }

    monkeypatch.setattr(
        tools,
        "_load_payables",
        mock_load_payables
    )

    result = await tools.get_top_payables_tool(
        limit=2
    )

    assert result["success"] is True

    bills = result["data"]["bills"]

    assert len(bills) == 2
    assert bills[0]["party"] == "Supplier B"
    assert bills[1]["party"] == "Supplier C"


@pytest.mark.asyncio
async def test_top_receivables_default_limit(
    monkeypatch
):
    async def mock_load_receivables(
        company_name=None
    ):
        return {
            "bills": [
                {
                    "party": f"Party {index}",
                    "outstanding_amount": index * 1000
                }
                for index in range(
                    1,
                    8
                )
            ]
        }

    monkeypatch.setattr(
        tools,
        "_load_receivables",
        mock_load_receivables
    )

    result = await tools.get_top_receivables_tool()

    assert result["success"] is True
    assert result["data"]["count"] == 5


@pytest.mark.asyncio
async def test_top_limit_is_capped(
    monkeypatch
):
    async def mock_load_payables(
        company_name=None
    ):
        return {
            "bills": [
                {
                    "party": f"Supplier {index}",
                    "outstanding_amount": index * 1000
                }
                for index in range(
                    1,
                    31
                )
            ]
        }

    monkeypatch.setattr(
        tools,
        "_load_payables",
        mock_load_payables
    )

    result = await tools.get_top_payables_tool(
        limit=100
    )

    assert result["success"] is True
    assert result["data"]["count"] == 20