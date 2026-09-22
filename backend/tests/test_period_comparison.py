import pytest
from datetime import date

import app.chatbot.tools as tools


@pytest.mark.asyncio
async def test_revenue_period_comparison(monkeypatch):
    async def fake_load_financial_summary(
        company_name=None,
        from_date=None,
        to_date=None
    ):
        if from_date == date(2026, 8, 1):
            return {
                "revenue": 800000,
                "expenses": 500000,
                "net_profit": 300000
            }

        return {
            "revenue": 700000,
            "expenses": 450000,
            "net_profit": 250000
        }

    monkeypatch.setattr(
        tools,
        "_load_financial_summary",
        fake_load_financial_summary
    )

    result = await tools.get_period_comparison_tool(
        metric="revenue",
        first_from_date=date(2026, 8, 1),
        first_to_date=date(2026, 8, 31),
        second_from_date=date(2026, 7, 1),
        second_to_date=date(2026, 7, 31)
    )

    assert result["success"] is True

    data = result["data"]

    assert data["metric"] == "revenue"
    assert data["first_period"]["value"] == 800000
    assert data["second_period"]["value"] == 700000
    assert data["difference"] == 100000
    assert data["percentage_change"] == 14.29


@pytest.mark.asyncio
async def test_expenses_period_comparison(monkeypatch):
    async def fake_load_financial_summary(
        company_name=None,
        from_date=None,
        to_date=None
    ):
        if from_date == date(2026, 8, 1):
            return {
                "revenue": 900000,
                "expenses": 400000,
                "net_profit": 500000
            }

        return {
            "revenue": 850000,
            "expenses": 500000,
            "net_profit": 350000
        }

    monkeypatch.setattr(
        tools,
        "_load_financial_summary",
        fake_load_financial_summary
    )

    result = await tools.get_period_comparison_tool(
        metric="expenses",
        first_from_date=date(2026, 8, 1),
        first_to_date=date(2026, 8, 31),
        second_from_date=date(2026, 7, 1),
        second_to_date=date(2026, 7, 31)
    )

    data = result["data"]

    assert data["first_period"]["value"] == 400000
    assert data["second_period"]["value"] == 500000
    assert data["difference"] == -100000
    assert data["percentage_change"] == -20.0


@pytest.mark.asyncio
async def test_net_profit_period_comparison(monkeypatch):
    async def fake_load_financial_summary(
        company_name=None,
        from_date=None,
        to_date=None
    ):
        if from_date == date(2026, 8, 1):
            return {
                "revenue": 1000000,
                "expenses": 600000,
                "net_profit": 400000
            }

        return {
            "revenue": 800000,
            "expenses": 550000,
            "net_profit": 250000
        }

    monkeypatch.setattr(
        tools,
        "_load_financial_summary",
        fake_load_financial_summary
    )

    result = await tools.get_period_comparison_tool(
        metric="net_profit",
        first_from_date=date(2026, 8, 1),
        first_to_date=date(2026, 8, 31),
        second_from_date=date(2026, 7, 1),
        second_to_date=date(2026, 7, 31)
    )

    data = result["data"]

    assert data["first_period"]["value"] == 400000
    assert data["second_period"]["value"] == 250000
    assert data["difference"] == 150000
    assert data["percentage_change"] == 60.0


@pytest.mark.asyncio
async def test_comparison_when_previous_value_is_zero(monkeypatch):
    async def fake_load_financial_summary(
        company_name=None,
        from_date=None,
        to_date=None
    ):
        if from_date == date(2026, 8, 1):
            return {
                "revenue": 500000,
                "expenses": 0,
                "net_profit": 500000
            }

        return {
            "revenue": 0,
            "expenses": 0,
            "net_profit": 0
        }

    monkeypatch.setattr(
        tools,
        "_load_financial_summary",
        fake_load_financial_summary
    )

    result = await tools.get_period_comparison_tool(
        metric="revenue",
        first_from_date=date(2026, 8, 1),
        first_to_date=date(2026, 8, 31),
        second_from_date=date(2026, 7, 1),
        second_to_date=date(2026, 7, 31)
    )

    data = result["data"]

    assert data["difference"] == 500000
    assert data["percentage_change"] is None


@pytest.mark.asyncio
async def test_unsupported_comparison_metric():
    result = await tools.get_period_comparison_tool(
        metric="cash_balance",
        first_from_date=date(2026, 8, 1),
        first_to_date=date(2026, 8, 31),
        second_from_date=date(2026, 7, 1),
        second_to_date=date(2026, 7, 31)
    )

    assert result["success"] is False
    assert result["source"] == "tally"
    assert result["data"] is None