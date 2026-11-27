"""
"As on" date filtering for Receivables and Payables.

Tally's Bills Receivable / Bills Payable are point-in-time reports: one
date decides which bills are still open, their outstanding amounts and
the overdue days. These tests pin that the chosen date reaches Tally as
SVTODATE, that it is part of the cache key, and that the two dates do
not share a cached answer.
"""

from datetime import date

import pytest
from fastapi.testclient import TestClient

from app.main import app
from app.api import reports
from app.tally import dashboard

pytestmark = pytest.mark.usefixtures("signed_in_superadmin")

client = TestClient(app)


def _bill(party, amount, overdue, kind):
    return {
        "party": party,
        "bill_reference": f"REF-{party}",
        "bill_date": "2026-01-01",
        "outstanding_amount": amount,
        "due_date": "2026-01-15",
        "overdue_days": overdue,
        "type": kind,
    }


@pytest.fixture
def captured_as_on(monkeypatch):
    """Record the as_on each fetch receives, and vary the answer by it."""
    seen = []

    def make(kind, label):
        async def fetch(company_name=None, as_on=None, **_):
            seen.append((label, as_on))
            if as_on == date(2025, 12, 31):
                return [_bill("Older Party", 5000.0, 274, kind)]
            return [_bill("Current Party", 600.0, 5, kind)]

        return fetch

    async def fake_allocations(company_name=None, **_):
        return []

    monkeypatch.setattr(
        reports, "fetch_bills_receivable", make("receivable", "receivable")
    )
    monkeypatch.setattr(
        reports, "fetch_bills_payable", make("payable", "payable")
    )
    monkeypatch.setattr(reports, "fetch_bill_allocations", fake_allocations)

    return seen


def test_receivables_forwards_the_selected_date(captured_as_on):
    response = client.get(
        "/api/v1/reports/receivables",
        params={"as_on": "2025-12-31"},
    )

    assert response.status_code == 200
    assert ("receivable", date(2025, 12, 31)) in captured_as_on
    assert response.json()["as_on"] == "2025-12-31"


def test_payables_forwards_the_selected_date(captured_as_on):
    response = client.get(
        "/api/v1/reports/payables",
        params={"as_on": "2025-12-31"},
    )

    assert response.status_code == 200
    assert ("payable", date(2025, 12, 31)) in captured_as_on
    assert response.json()["as_on"] == "2025-12-31"


def test_two_dates_do_not_share_one_cached_answer(captured_as_on):
    """
    The date is part of the cache key, so asking for a different date must
    reach Tally again instead of replaying the first answer.
    """
    older = client.get(
        "/api/v1/reports/receivables",
        params={"as_on": "2025-12-31", "force_refresh": True},
    ).json()

    current = client.get(
        "/api/v1/reports/receivables",
        params={"as_on": "2026-03-31", "force_refresh": True},
    ).json()

    assert older["data"]["total_receivable"] == 5000.0
    assert current["data"]["total_receivable"] == 600.0

    assert ("receivable", date(2025, 12, 31)) in captured_as_on
    assert ("receivable", date(2026, 3, 31)) in captured_as_on


def test_no_date_keeps_tallys_own_period(captured_as_on):
    response = client.get("/api/v1/reports/receivables")

    assert response.status_code == 200
    assert ("receivable", None) in captured_as_on
    assert response.json()["as_on"] is None


def test_an_invalid_date_is_rejected(captured_as_on):
    response = client.get(
        "/api/v1/reports/receivables",
        params={"as_on": "not-a-date"},
    )

    assert response.status_code == 422
    assert captured_as_on == []


@pytest.mark.parametrize("kind", ["receivable", "payable"])
def test_the_date_reaches_tally_as_svtodate(kind):
    """
    report_request(..., as_of=...) is what sets SVTODATE. Verify the date
    actually lands in the request Tally receives.
    """
    from app.tally.xml_builders.financial import (
        build_bills_payable_request,
        build_bills_receivable_request,
    )

    builder = (
        build_bills_receivable_request
        if kind == "receivable"
        else build_bills_payable_request
    )

    request = dashboard.report_request(
        builder(company_name="Test Co"),
        as_of=date(2025, 12, 31),
    )

    assert "<SVTODATE>20251231</SVTODATE>" in request
