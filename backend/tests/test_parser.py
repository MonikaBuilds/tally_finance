from app.tally.parsers.common import format_tally_date
from app.tally.parsers.financial import parse_outstanding_report


def test_format_tally_date_compact():
    result = format_tally_date("20250401")

    assert result == "2025-04-01"


def test_format_tally_date_report_style():
    result = format_tally_date("1-Apr-25")

    assert result == "2025-04-01"


def test_parse_receivable_outstanding_report():
    xml_response = """
    <ENVELOPE>
        <BILLFIXED>
            <BILLDATE>1-Apr-25</BILLDATE>
            <BILLREF>1</BILLREF>
            <BILLPARTY>Eagle Paradise Pvt. Ltd.</BILLPARTY>
        </BILLFIXED>
        <BILLCL>-80000.00</BILLCL>
        <BILLDUE>1-Apr-25</BILLDUE>
        <BILLOVERDUE>364</BILLOVERDUE>
    </ENVELOPE>
    """

    bills = parse_outstanding_report(
        xml_response,
        report_type="receivable"
    )

    assert len(bills) == 1

    bill = bills[0]

    assert bill["party"] == "Eagle Paradise Pvt. Ltd."
    assert bill["bill_reference"] == "1"
    assert bill["bill_date"] == "2025-04-01"
    assert bill["outstanding_amount"] == 80000.0
    assert bill["due_date"] == "2025-04-01"
    assert bill["overdue_days"] == 364
    assert bill["type"] == "receivable"


def test_parse_payable_outstanding_report():
    xml_response = """
    <ENVELOPE>
        <BILLFIXED>
            <BILLDATE>1-Apr-25</BILLDATE>
            <BILLREF>FIN/01/202526</BILLREF>
            <BILLPARTY>Apex Office Solutions</BILLPARTY>
        </BILLFIXED>
        <BILLCL>1170000.00</BILLCL>
        <BILLDUE>1-Apr-25</BILLDUE>
        <BILLOVERDUE>364</BILLOVERDUE>
    </ENVELOPE>
    """

    bills = parse_outstanding_report(
        xml_response,
        report_type="payable"
    )

    assert len(bills) == 1

    bill = bills[0]

    assert bill["party"] == "Apex Office Solutions"
    assert bill["bill_reference"] == "FIN/01/202526"
    assert bill["outstanding_amount"] == 1170000.0
    assert bill["type"] == "payable"