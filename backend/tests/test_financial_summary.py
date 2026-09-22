from datetime import date

import pytest

import app.chatbot.tools as tools


@pytest.mark.asyncio
async def test_financial_summary(monkeypatch):
    async def fake_load_financial_summary(
        company_name=None,
        from_date=None,
        to_date=None
    ):
        return {
            "revenue": 741000,
            "expenses": 520000,
            "net_profit": 221000
        }

    async def fake_receivables(company_name=None):
        return {
            "success": True,
            "source": "tally",
            "data": {
                "total_receivable": 80000,
                "count": 1,
                "bills": []
            }
        }

    async def fake_payables(company_name=None):
        return {
            "success": True,
            "source": "tally",
            "data": {
                "total_payable": 117000,
                "count": 2,
                "bills": []
            }
        }

    async def fake_pending_invoices(company_name=None):
        return {
            "success": True,
            "source": "tally",
            "data": {
                "count": 2,
                "invoices": []
            }
        }

    monkeypatch.setattr(
        tools,
        "_load_financial_summary",
        fake_load_financial_summary
    )
    monkeypatch.setattr(
        tools,
        "get_receivables_tool",
        fake_receivables
    )
    monkeypatch.setattr(
        tools,
        "get_payables_tool",
        fake_payables
    )
    monkeypatch.setattr(
        tools,
        "get_pending_invoices_tool",
        fake_pending_invoices
    )

    result = await tools.get_financial_summary_tool(
        company_name="Demo Company",
        from_date=date(2026, 8, 1),
        to_date=date(2026, 8, 31)
    )

    assert result["success"] is True
    assert result["source"] == "tally"

    data = result["data"]

    assert data["from_date"] == "2026-08-01"
    assert data["to_date"] == "2026-08-31"
    assert data["revenue"] == 741000
    assert data["expenses"] == 520000
    assert data["net_profit"] == 221000
    assert data["receivables"] == 80000
    assert data["payables"] == 117000
    assert data["pending_invoices"] == 2


@pytest.mark.asyncio
async def test_financial_summary_without_dates(monkeypatch):
    async def fake_load_financial_summary(
        company_name=None,
        from_date=None,
        to_date=None
    ):
        return {
            "revenue": 100000,
            "expenses": 75000,
            "net_profit": 25000
        }

    async def fake_receivables(company_name=None):
        return {
            "success": True,
            "source": "tally",
            "data": {
                "total_receivable": 20000
            }
        }

    async def fake_payables(company_name=None):
        return {
            "success": True,
            "source": "tally",
            "data": {
                "total_payable": 15000
            }
        }

    async def fake_pending_invoices(company_name=None):
        return {
            "success": True,
            "source": "tally",
            "data": {
                "count": 1
            }
        }

    monkeypatch.setattr(
        tools,
        "_load_financial_summary",
        fake_load_financial_summary
    )
    monkeypatch.setattr(
        tools,
        "get_receivables_tool",
        fake_receivables
    )
    monkeypatch.setattr(
        tools,
        "get_payables_tool",
        fake_payables
    )
    monkeypatch.setattr(
        tools,
        "get_pending_invoices_tool",
        fake_pending_invoices
    )

    result = await tools.get_financial_summary_tool()

    data = result["data"]

    assert data["from_date"] is None
    assert data["to_date"] is None
    assert data["revenue"] == 100000
    assert data["expenses"] == 75000
    assert data["net_profit"] == 25000
    assert data["receivables"] == 20000
    assert data["payables"] == 15000
    assert data["pending_invoices"] == 1