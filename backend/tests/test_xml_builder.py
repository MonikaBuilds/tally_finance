from datetime import date

from app.tally.xml_builders.common import build_company_variable
from app.tally.xml_builders.financial import (
    build_profit_loss_request,
    build_trial_balance_request,
    build_balance_sheet_request,
    build_voucher_bills_request,
)


def test_company_name_is_escaped():
    xml = build_company_variable(
        "A & B Enterprises"
    )

    assert (
        "<SVCURRENTCOMPANY>"
        "A &amp; B Enterprises"
        "</SVCURRENTCOMPANY>"
    ) in xml


def test_profit_loss_contains_dates():
    xml = build_profit_loss_request(
        from_date=date(2025, 4, 1),
        to_date=date(2025, 4, 30)
    )

    assert "<SVFROMDATE>20250401</SVFROMDATE>" in xml
    assert "<SVTODATE>20250430</SVTODATE>" in xml


def test_trial_balance_contains_to_date():
    xml = build_trial_balance_request(
        to_date=date(2025, 3, 31)
    )

    assert "<SVTODATE>20250331</SVTODATE>" in xml


def test_balance_sheet_contains_to_date():
    xml = build_balance_sheet_request(
        to_date=date(2025, 3, 31)
    )

    assert "<SVTODATE>20250331</SVTODATE>" in xml


def test_voucher_collection_contains_date_range():
    xml = build_voucher_bills_request(
        from_date=date(2025, 4, 1),
        to_date=date(2025, 4, 30)
    )

    assert "<SVFROMDATE>20250401</SVFROMDATE>" in xml
    assert "<SVTODATE>20250430</SVTODATE>" in xml