from datetime import date

from fastapi.testclient import TestClient

from app.main import app
from app.api import reports
from app.tally.xml_builders import build_trial_balance_request


client = TestClient(app)


# TRIAL BALANCE - From Date / To Date filter


def test_trial_balance_request_contains_from_and_to_date():
    xml = build_trial_balance_request(
        company_name="ABC Pvt Ltd",
        from_date=date(2025, 4, 1),
        to_date=date(2026, 3, 31),
    )

    assert "<SVFROMDATE>20250401</SVFROMDATE>" in xml
    assert "<SVTODATE>20260331</SVTODATE>" in xml


def test_trial_balance_request_without_from_date_is_unchanged():
    xml = build_trial_balance_request(to_date=date(2025, 3, 31))

    assert "SVFROMDATE" not in xml
    assert "<SVTODATE>20250331</SVTODATE>" in xml


def test_trial_balance_forwards_from_and_to_date(monkeypatch):
    seen = {}

    async def fake_trial_balance(
        company_name=None,
        to_date=None,
        from_date=None
    ):
        seen["from_date"] = from_date
        seen["to_date"] = to_date

        return [{"name": "Cash", "debit": 500.0, "credit": None}]

    monkeypatch.setattr(
        reports,
        "fetch_trial_balance",
        fake_trial_balance
    )

    response = client.get(
        "/api/v1/reports/trial-balance",
        params={
            "from_date": "2025-04-01",
            "to_date": "2026-03-31"
        }
    )

    assert response.status_code == 200
    assert seen["from_date"] == date(2025, 4, 1)
    assert seen["to_date"] == date(2026, 3, 31)


def test_trial_balance_invalid_date_range():
    response = client.get(
        "/api/v1/reports/trial-balance",
        params={
            "from_date": "2026-05-01",
            "to_date": "2026-04-01"
        }
    )

    assert response.status_code == 400


def test_trial_balance_purchase_bills_pending_only_receipt_notes(monkeypatch):
    async def fake_stock_movement(
        company_name=None,
        from_date=None,
        to_date=None,
        stock_item_name=None,
        godown_name=None
    ):
        return {
            "rows": [
                {
                    "date": "2025-04-01",
                    "voucher_type": "Receipt Note",
                    "voucher_number": "1",
                    "stock_item": "SmartMind AI",
                    "party": "Eagle Paradise Pvt. Ltd.",
                    "quantity": 30,
                    "rate": 600000,
                    "amount": 18000000
                },
                {
                    "date": "2025-05-01",
                    "voucher_type": "Sales",
                    "voucher_number": "9",
                    "stock_item": "SmartMind AI",
                    "party": "Someone",
                    "quantity": -8,
                    "rate": 1,
                    "amount": -1
                }
            ]
        }

    monkeypatch.setattr(
        reports,
        "fetch_stock_movement",
        fake_stock_movement
    )

    response = client.get(
        "/api/v1/reports/trial-balance/purchase-bills-pending",
        params={
            "from_date": "2025-04-01",
            "to_date": "2026-03-31"
        }
    )

    assert response.status_code == 200

    body = response.json()

    assert body["count"] == 1
    assert body["report"][0]["tracking_number"] == "1"
    assert body["total_value"] == 18000000
