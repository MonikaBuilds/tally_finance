import pytest

from app.chatbot import tools


@pytest.mark.asyncio
async def test_aged_receivables_30_days(
    monkeypatch
):
    async def fake_load_receivables(
        company_name=None
    ):
        return {
            "bills": [
                {
                    "party": "Customer A",
                    "outstanding_amount": 10000,
                    "overdue_days": 10
                },
                {
                    "party": "Customer B",
                    "outstanding_amount": 30000,
                    "overdue_days": 35
                },
                {
                    "party": "Customer C",
                    "outstanding_amount": 50000,
                    "overdue_days": 75
                }
            ]
        }

    monkeypatch.setattr(
        tools,
        "_load_receivables",
        fake_load_receivables
    )

    result = await tools.get_aged_receivables_tool(
        minimum_days=30
    )

    assert result["success"] is True
    assert result["data"]["count"] == 2
    assert result["data"]["total_overdue"] == 80000


@pytest.mark.asyncio
async def test_aged_payables_60_days(
    monkeypatch
):
    async def fake_load_payables(
        company_name=None
    ):
        return {
            "bills": [
                {
                    "party": "Supplier A",
                    "outstanding_amount": 15000,
                    "overdue_days": 20
                },
                {
                    "party": "Supplier B",
                    "outstanding_amount": 40000,
                    "overdue_days": 65
                },
                {
                    "party": "Supplier C",
                    "outstanding_amount": 60000,
                    "overdue_days": 120
                }
            ]
        }

    monkeypatch.setattr(
        tools,
        "_load_payables",
        fake_load_payables
    )

    result = await tools.get_aged_payables_tool(
        minimum_days=60
    )

    assert result["success"] is True
    assert result["data"]["count"] == 2
    assert result["data"]["total_overdue"] == 100000


@pytest.mark.asyncio
async def test_aged_receivables_90_days(
    monkeypatch
):
    async def fake_load_receivables(
        company_name=None
    ):
        return {
            "bills": [
                {
                    "party": "Customer A",
                    "outstanding_amount": 25000,
                    "overdue_days": 89
                },
                {
                    "party": "Customer B",
                    "outstanding_amount": 45000,
                    "overdue_days": 90
                },
                {
                    "party": "Customer C",
                    "outstanding_amount": 75000,
                    "overdue_days": 150
                }
            ]
        }

    monkeypatch.setattr(
        tools,
        "_load_receivables",
        fake_load_receivables
    )

    result = await tools.get_aged_receivables_tool(
        minimum_days=90
    )

    assert result["data"]["count"] == 2
    assert result["data"]["total_overdue"] == 120000


@pytest.mark.asyncio
async def test_full_aging_buckets(
    monkeypatch
):
    async def fake_load_receivables(
        company_name=None
    ):
        return {
            "bills": [
                {
                    "party": "A",
                    "outstanding_amount": 1000,
                    "overdue_days": 15
                },
                {
                    "party": "B",
                    "outstanding_amount": 2000,
                    "overdue_days": 45
                },
                {
                    "party": "C",
                    "outstanding_amount": 3000,
                    "overdue_days": 75
                },
                {
                    "party": "D",
                    "outstanding_amount": 4000,
                    "overdue_days": 120
                }
            ]
        }

    monkeypatch.setattr(
        tools,
        "_load_receivables",
        fake_load_receivables
    )

    result = await tools.get_aged_receivables_tool()

    buckets = result["data"]["buckets"]

    assert buckets["1_30"]["amount"] == 1000
    assert buckets["31_60"]["amount"] == 2000
    assert buckets["61_90"]["amount"] == 3000
    assert buckets["91_plus"]["amount"] == 4000


@pytest.mark.asyncio
async def test_non_overdue_bills_are_excluded(
    monkeypatch
):
    async def fake_load_payables(
        company_name=None
    ):
        return {
            "bills": [
                {
                    "party": "Supplier A",
                    "outstanding_amount": 10000,
                    "overdue_days": 0
                },
                {
                    "party": "Supplier B",
                    "outstanding_amount": 20000,
                    "overdue_days": 20
                }
            ]
        }

    monkeypatch.setattr(
        tools,
        "_load_payables",
        fake_load_payables
    )

    result = await tools.get_aged_payables_tool()

    assert result["data"]["count"] == 1
    assert result["data"]["total_overdue"] == 20000