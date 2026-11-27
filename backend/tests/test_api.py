import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api import reports
from app.api import dashboard

# Synthetic test users: see tests/conftest.py
pytestmark = pytest.mark.usefixtures("signed_in_superadmin")


client = TestClient(app)



# PROFIT & LOSS


def test_profit_loss_success(monkeypatch):

    async def fake_fetch_profit_loss(
        from_date=None,
        to_date=None,
        company_name=None
    ):
        return [
            {
                "name": "Sales Accounts",
                "main_amount": 1000.0,
                "sub_amount": None
            }
        ]

    monkeypatch.setattr(
        reports,
        "fetch_profit_loss",
        fake_fetch_profit_loss
    )

    response = client.get(
        "/api/v1/reports/profit-loss"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["source"] == "tally"
    assert len(body["report"]) == 1


def test_profit_loss_invalid_date_range():

    response = client.get(
        "/api/v1/reports/profit-loss",
        params={
            "from_date": "2026-05-01",
            "to_date": "2026-04-01"
        }
    )

    assert response.status_code == 400

    body = response.json()

    assert (
        body["detail"]
        == "from_date cannot be later than to_date"
    )


def test_profit_loss_tally_failure(monkeypatch):

    async def fake_failure(
        from_date=None,
        to_date=None
    ):
        raise RuntimeError(
            "Tally unavailable"
        )

    monkeypatch.setattr(
        reports,
        "fetch_profit_loss",
        fake_failure
    )

    response = client.get(
        "/api/v1/reports/profit-loss"
    )

    assert response.status_code == 502

    assert (
        response.json()["detail"]
        == "Unable to fetch Profit & Loss from Tally"
    )



# TRIAL BALANCE

def test_trial_balance_success(monkeypatch):

    async def fake_trial_balance(
        company_name=None,
        to_date=None
    ):
        return [
            {
                "name": "Cash",
                "debit": 500.0,
                "credit": None
            }
        ]

    monkeypatch.setattr(
        reports,
        "fetch_trial_balance",
        fake_trial_balance
    )

    response = client.get(
        "/api/v1/reports/trial-balance"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["report"][0]["name"] == "Cash"


def test_trial_balance_failure(monkeypatch):

    async def fake_failure():
        raise RuntimeError(
            "Tally unavailable"
        )

    monkeypatch.setattr(
        reports,
        "fetch_trial_balance",
        fake_failure
    )

    response = client.get(
        "/api/v1/reports/trial-balance"
    )

    assert response.status_code == 502


# RECEIVABLES

def test_receivables_success(monkeypatch):

    async def fake_receivable_report(
        company_name=None,
        as_on=None
    ):
        return [
            {
                "party": "Test Customer",
                "bill_reference": "INV-001",
                "bill_date": "2026-01-01",
                "outstanding_amount": 600.0,
                "due_date": "2026-01-15",
                "overdue_days": 5,
                "type": "receivable"
            }
        ]

    async def fake_allocations(
        company_name=None
    ):
        return [
            {
                "party": "Test Customer",
                "bill_reference": "INV-001",
                "bill_type": "New Ref",
                "bill_date": "2026-01-01",
                "amount": -600.0,
                "voucher_type": "Sales",
                "voucher_number": "S-001",
                "voucher_date": "2026-01-01",
                "guid": "test-guid"
            }
        ]

    monkeypatch.setattr(
        reports,
        "fetch_bills_receivable",
        fake_receivable_report
    )

    monkeypatch.setattr(
        reports,
        "fetch_bill_allocations",
        fake_allocations
    )

    response = client.get(
        "/api/v1/reports/receivables"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True

    assert (
        body["data"]["total_receivable"]
        == 600.0
    )

    assert body["data"]["count"] == 1

    bill = body["data"]["bills"][0]

    assert bill["party"] == "Test Customer"
    assert bill["outstanding_amount"] == 600.0
    assert bill["due_date"] == "2026-01-15"


def test_receivables_failure(monkeypatch):

    async def fake_failure():
        raise RuntimeError(
            "Tally unavailable"
        )

    monkeypatch.setattr(
        reports,
        "fetch_bills_receivable",
        fake_failure
    )

    response = client.get(
        "/api/v1/reports/receivables"
    )

    assert response.status_code == 502

    assert (
        response.json()["detail"]
        == "Unable to fetch receivables from Tally"
    )


# PAYABLES

def test_payables_success(monkeypatch):

    async def fake_payable_report(
        company_name=None,
        as_on=None
    ):
        return [
            {
                "party": "Test Supplier",
                "bill_reference": "PUR-001",
                "bill_date": "2026-01-01",
                "outstanding_amount": 1500.0,
                "due_date": "2026-01-20",
                "overdue_days": 3,
                "type": "payable"
            }
        ]

    async def fake_allocations(
        company_name=None
    ):
        return [
            {
                "party": "Test Supplier",
                "bill_reference": "PUR-001",
                "bill_type": "New Ref",
                "bill_date": "2026-01-01",
                "amount": 1500.0,
                "voucher_type": "Purchase",
                "voucher_number": "P-001",
                "voucher_date": "2026-01-01",
                "guid": "test-guid"
            }
        ]

    monkeypatch.setattr(
        reports,
        "fetch_bills_payable",
        fake_payable_report
    )

    monkeypatch.setattr(
        reports,
        "fetch_bill_allocations",
        fake_allocations
    )

    response = client.get(
        "/api/v1/reports/payables"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True

    assert (
        body["data"]["total_payable"]
        == 1500.0
    )

    assert body["data"]["count"] == 1



# DASHBOARD


# test_dashboard_summary_success was removed: it mocked the old dashboard
# that added P&L rows in Python. The current dashboard reads Tally's native
# reports and is covered by tests/test_dashboard_data.py.
    
def test_trial_balance_passes_company_name(
    monkeypatch
):
    received = {}

    async def fake_trial_balance(
        company_name=None,
        to_date=None
    ):
        received["company_name"] = company_name

        return [
            {
                "name": "Cash",
                "debit": 1000.0,
                "credit": None
            }
        ]

    monkeypatch.setattr(
        reports,
        "fetch_trial_balance",
        fake_trial_balance
    )

    response = client.get(
        "/api/v1/reports/trial-balance",
        params={
            "company_name": "Test Company"
        }
    )

    assert response.status_code == 200

    assert (
        received["company_name"]
        == "Test Company"
    )
    
def test_trial_balance_passes_to_date(
    monkeypatch
):
    received = {}

    async def fake_trial_balance(
        company_name=None,
        to_date=None
    ):
        received["to_date"] = to_date

        return [
            {
                "name": "Cash",
                "debit": 1000.0,
                "credit": None
            }
        ]

    monkeypatch.setattr(
        reports,
        "fetch_trial_balance",
        fake_trial_balance
    )

    response = client.get(
        "/api/v1/reports/trial-balance",
        params={
            "to_date": "2025-04-30"
        }
    )

    assert response.status_code == 200

    assert (
        str(received["to_date"])
        == "2025-04-30"
    )
    
def test_trial_balance_passes_to_date(
    monkeypatch
):
    received = {}

    async def fake_trial_balance(
        company_name=None,
        to_date=None
    ):
        received["to_date"] = to_date

        return [
            {
                "name": "Cash",
                "debit": 1000.0,
                "credit": None
            }
        ]

    monkeypatch.setattr(
        reports,
        "fetch_trial_balance",
        fake_trial_balance
    )

    response = client.get(
        "/api/v1/reports/trial-balance",
        params={
            "to_date": "2025-04-30"
        }
    )

    assert response.status_code == 200
    assert str(received["to_date"]) == "2025-04-30"


# TEST FIXTURE (not Tally data): the minimal shape returned by
# fetch_balance_sheet_report(), which the Balance Sheet route now uses.
def _fixture_balance_sheet_report():
    return {
        "liabilities": [{"name": "Capital Account", "amount": 10000.0}],
        "assets": [{"name": "Current Assets", "amount": 10000.0}],
        "total_liabilities": 10000.0,
        "total_assets": 10000.0,
        "difference": 0.0,
    }


def test_balance_sheet_success(
    monkeypatch
):
    async def fake_balance_sheet_report(
        company_name=None,
        from_date=None,
        to_date=None,
    ):
        return _fixture_balance_sheet_report()

    monkeypatch.setattr(
        reports,
        "fetch_balance_sheet_report",
        fake_balance_sheet_report
    )

    response = client.get(
        "/api/v1/reports/balance-sheet"
    )

    assert response.status_code == 200

    body = response.json()

    assert body["success"] is True
    assert body["source"] == "tally"
    assert body["report"]["assets"][0]["name"] == "Current Assets"
    assert body["report"]["total_assets"] == 10000.0


def test_balance_sheet_passes_to_date(
    monkeypatch
):
    received = {}

    async def fake_balance_sheet_report(
        company_name=None,
        from_date=None,
        to_date=None,
    ):
        received["to_date"] = to_date
        return _fixture_balance_sheet_report()

    monkeypatch.setattr(
        reports,
        "fetch_balance_sheet_report",
        fake_balance_sheet_report
    )

    response = client.get(
        "/api/v1/reports/balance-sheet",
        params={
            "to_date": "2025-03-31"
        }
    )

    assert response.status_code == 200
    assert str(received["to_date"]) == "2025-03-31"


def test_balance_sheet_passes_company_name(
    monkeypatch
):
    received = {}

    async def fake_balance_sheet_report(
        company_name=None,
        from_date=None,
        to_date=None,
    ):
        received["company_name"] = company_name
        return _fixture_balance_sheet_report()

    monkeypatch.setattr(
        reports,
        "fetch_balance_sheet_report",
        fake_balance_sheet_report
    )

    response = client.get(
        "/api/v1/reports/balance-sheet",
        params={
            "company_name": "Test Company"
        }
    )

    assert response.status_code == 200
    assert received["company_name"] == "Test Company"