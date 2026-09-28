"""Balance Sheet regression evidence; these values are never production defaults."""

from xml.sax.saxutils import escape

import pytest

from app.tally.parsers.financial import parse_balance_sheet


def native_pair(name, amount):
    return (
        f"<BSNAME><DSPACCNAME><DSPDISPNAME>{escape(name)}</DSPDISPNAME>"
        "</DSPACCNAME></BSNAME>"
        f"<BSAMT><BSSUBAMT></BSSUBAMT><BSMAINAMT>{amount}</BSMAINAMT></BSAMT>"
    )


# Values captured from the live Balance Sheet, plus an explicit-zero edge case.
@pytest.mark.parametrize(
    "name,raw,expected",
    [
        ("Loans (Liability)", "500000.00", 500000.0),
        ("Current Liabilities", "-15456200.00", -15456200.0),
        ("Profit & Loss A/c", "-265000.00", -265000.0),
        ("Capital Account", "", None),
        ("Current Assets", "4721200.00", 4721200.0),
        ("Explicit zero", "0.00", 0.0),
    ],
)
def test_native_signed_and_optional_amounts(name, raw, expected):
    report = parse_balance_sheet(f"<ENVELOPE>{native_pair(name, raw)}</ENVELOPE>")

    assert report == {
        "success": True,
        "rows": [{"name": name, "amount": expected}],
        "count": 1,
    }


def test_sequential_pairs_preserve_correspondence_and_order():
    xml = "<ENVELOPE>" + "".join(
        [
            native_pair("Capital Account", ""),
            native_pair("Loans (Liability)", "500000.00"),
            native_pair("Current Liabilities", "-15456200.00"),
            native_pair("Profit & Loss A/c", "-265000.00"),
            native_pair("Current Assets", "4721200.00"),
        ]
    ) + "</ENVELOPE>"

    report = parse_balance_sheet(xml)

    assert report["rows"] == [
        {"name": "Capital Account", "amount": None},
        {"name": "Loans (Liability)", "amount": 500000.0},
        {"name": "Current Liabilities", "amount": -15456200.0},
        {"name": "Profit & Loss A/c", "amount": -265000.0},
        {"name": "Current Assets", "amount": 4721200.0},
    ]
    assert report["count"] == 5


def test_missing_amount_does_not_borrow_from_next_account():
    xml = (
        "<ENVELOPE><BSNAME><DSPACCNAME><DSPDISPNAME>Capital Account</DSPDISPNAME>"
        "</DSPACCNAME></BSNAME>"
        + native_pair("Loans (Liability)", "500000.00")
        + "<BSNAME><DSPACCNAME><DSPDISPNAME>Trailing account</DSPDISPNAME>"
        "</DSPACCNAME></BSNAME></ENVELOPE>"
    )

    assert parse_balance_sheet(xml)["rows"] == [
        {"name": "Capital Account", "amount": None},
        {"name": "Loans (Liability)", "amount": 500000.0},
        {"name": "Trailing account", "amount": None},
    ]


@pytest.mark.parametrize("main", ["", "<BSMAINAMT></BSMAINAMT>"])
def test_subamount_is_not_used_as_a_replacement(main):
    xml = (
        "<ENVELOPE><BSNAME><DSPACCNAME><DSPDISPNAME>Capital Account</DSPDISPNAME>"
        "</DSPACCNAME></BSNAME><BSAMT><BSSUBAMT>500000.00</BSSUBAMT>"
        f"{main}</BSAMT></ENVELOPE>"
    )

    assert parse_balance_sheet(xml)["rows"][0]["amount"] is None


@pytest.mark.parametrize("tag", ["DSPCLAMT", "DSPAMOUNT", "AMOUNT"])
@pytest.mark.parametrize("raw,expected", [("-265000.00", -265000.0), ("0.00", 0.0), ("", None)])
def test_legacy_amount_fields_remain_supported(tag, raw, expected):
    xml = (
        "<ENVELOPE><DSPACCNAME><NAME>Legacy account</NAME>"
        f"<{tag}>{raw}</{tag}></DSPACCNAME></ENVELOPE>"
    )

    assert parse_balance_sheet(xml)["rows"] == [
        {"name": "Legacy account", "amount": expected}
    ]


def test_native_and_legacy_rows_can_coexist_in_a_report_container():
    xml = (
        "<ENVELOPE><REPORT>"
        + native_pair("Loans (Liability)", "500000.00")
        + "<DSPACCNAME><DSPDISPNAME>Legacy account</DSPDISPNAME>"
        "<AMOUNT>-265000.00</AMOUNT></DSPACCNAME></REPORT></ENVELOPE>"
    )

    assert parse_balance_sheet(xml)["rows"] == [
        {"name": "Loans (Liability)", "amount": 500000.0},
        {"name": "Legacy account", "amount": -265000.0},
    ]
