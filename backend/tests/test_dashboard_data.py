"""Dashboard-only contracts using captured report shapes and boundary cases."""

import asyncio
from datetime import date
from xml.etree import ElementTree as ET

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api import dashboard
from app.api.dashboard_mapper import map_dashboard_summary
from app.security.auth import get_authorized_company
from app.tally.dashboard import (
    collection_request, parse_balances, parse_native_table,
    parse_outstanding_table, parse_profit_loss_rows,
)


START, END = date(2025, 4, 1), date(2026, 3, 31)


def pl_xml(sales='7410000.00', purchase='16800000.00'):
    return f'''<ENVELOPE>
    <DSPACCNAME><DSPDISPNAME>Sales Accounts</DSPDISPNAME></DSPACCNAME>
    <PLAMT><PLSUBAMT></PLSUBAMT><BSMAINAMT>{sales}</BSMAINAMT></PLAMT>
    <DSPACCNAME><DSPDISPNAME>Add: Purchase Accounts</DSPDISPNAME></DSPACCNAME>
    <PLAMT><PLSUBAMT>{purchase}</PLSUBAMT><BSMAINAMT></BSMAINAMT></PLAMT>
    <DSPACCNAME><DSPDISPNAME>Opening Stock</DSPDISPNAME></DSPACCNAME>
    <PLAMT><PLSUBAMT>-10500000.00</PLSUBAMT></PLAMT>
    <DSPACCNAME><DSPDISPNAME>Indirect Expenses</DSPDISPNAME></DSPACCNAME>
    <PLAMT><BSMAINAMT>-270000.00</BSMAINAMT></PLAMT>
    </ENVELOPE>'''


def table(rows):
    return '<html><table>' + ''.join('<tr>' + ''.join(f'<td>{cell}</td>' for cell in row) + '</tr>' for row in rows) + '</table></html>'


def reports():
    return {
        'profit_loss': parse_profit_loss_rows(pl_xml()),
        'profit_loss_totals': parse_native_table(table([
            ['Example company'], ['Particulars', '1-Apr-25 to 31-Mar-26'],
            ['', 'Nett Loss', '', '2,65,000.00'],
        ])),
        'groups': [{'name': 'Cash-in-Hand', 'parent': 'Current Assets', 'amount': -10000.0, 'raw': '-10000.00', 'field': 'GROUP/CLOSINGBALANCE'}],
        'ledgers': [{'name': 'Cash', 'parent': 'Cash-in-Hand', 'amount': -10000.0, 'raw': '-10000.00'}],
    }


@pytest.mark.parametrize('raw,expected', [('', None), ('0.00', 0.0), ('-1.25', -1.25), ('16800000.00', 16800000.0)])
def test_purchase_preserves_native_optional_signed_amount(raw, expected):
    result = map_dashboard_summary({'profit_loss': parse_profit_loss_rows(pl_xml(purchase=raw))}, START, END, 'Example company')
    assert result['total_purchases'] == expected
    assert result['metric_sources']['total_purchases']['raw'] == raw


def test_sales_and_expenses_do_not_include_stock_purchase_or_profit():
    result = map_dashboard_summary(reports(), START, END, 'Example company')
    assert result['total_sales'] == 7410000.0
    assert result['sales_breakdown'] == [{'label': 'Sales Accounts', 'value': 7410000.0}]
    assert result['expense_breakdown'] == [{'label': 'Indirect Expenses', 'value': -270000.0}]
    assert result['net_loss'] == 265000.0
    assert result['net_profit'] is None  # No opposite-result zero is fabricated.


def test_net_result_requires_same_company_and_period():
    assert map_dashboard_summary(reports(), START, END, 'Other company')['net_loss'] is None
    assert map_dashboard_summary(reports(), START, date(2026, 9, 28), 'Example company')['net_loss'] is None


def test_tax_totals_are_not_inferred_from_duties_balances():
    source = reports()
    source['groups'].append({'name': 'Duties & Taxes', 'amount': 198900.0})
    result = map_dashboard_summary(source, START, END, 'Example company')
    assert result['gst_payable'] is None
    assert result['tds_payable'] is None


def test_cash_preserves_tally_sign_and_nested_groups():
    source = reports()
    source['groups'].append({'name': 'Petty cash group', 'parent': 'Cash-in-Hand'})
    source['ledgers'][0]['parent'] = 'Petty cash group'
    result = map_dashboard_summary(source, START, END, 'Example company')
    assert result['cash_in_hand'] == -10000.0
    assert result['cash_bank_accounts'][0]['balance'] == -10000.0


def outstanding_html(footer=True):
    rows = [
        ['Bills Receivable'], ['Group :', '1-Apr-25 to 31-Mar-26'],
        ['Date', 'Ref. No.', "Party's Name", 'Pending', 'Due on', 'Overdue'],
        ['1-Apr-25', '1', 'Customer', '80,000.25', '1-Apr-25', '364'],
    ]
    if footer:
        rows.append(['', '', '', '80,000.25', '', ''])
    return table(rows)


def test_outstanding_total_comes_from_native_footer_not_sum():
    parsed = parse_outstanding_table(outstanding_html())
    assert parsed['total'] == 80000.25
    assert parsed['bills'][0]['days_overdue'] == 364
    assert parse_outstanding_table(outstanding_html(False))['total'] is None
    result = map_dashboard_summary({'receivables': parsed}, START, END, 'Example company')
    assert result['receivables'] == 80000.25
    assert result['top_receivables'][0]['amount'] == 80000.25


def test_outstanding_wrong_date_is_not_presented_as_current():
    result = map_dashboard_summary({'receivables': parse_outstanding_table(outstanding_html())}, START, date(2026, 9, 28), 'Example company')
    assert result['receivables'] is None
    assert result['top_receivables'] is None
    assert result['report_contexts']['receivables']['to_date'] == '2026-03-31'


def test_no_borrowed_amount_and_no_duplicate_account_guess():
    rows = parse_profit_loss_rows('<ENVELOPE><DSPACCNAME><DSPDISPNAME>Sales Accounts</DSPDISPNAME></DSPACCNAME>' + pl_xml()[10:])
    assert rows[0]['amount'] is None
    assert map_dashboard_summary({'profit_loss': rows}, START, END, 'Example company')['total_sales'] is None


def test_collection_request_company_is_escaped_and_as_of_is_dynamic():
    root = ET.fromstring(collection_request('A & B <Company>', END, 'Group'))
    assert root.findtext('.//SVCURRENTCOMPANY') == 'A & B <Company>'
    assert root.findtext('.//SVTODATE') == '20260331'
    assert root.findtext('.//COLLECTION/TYPE') == 'Group'


def test_balance_collection_blank_is_not_zero():
    rows = parse_balances('<ENVELOPE><COLLECTION><GROUP NAME="Cash-in-Hand"><CLOSINGBALANCE/></GROUP></COLLECTION></ENVELOPE>', 'Group')
    assert rows[0]['amount'] is None


def test_month_windows_clip_both_edges_and_include_year():
    windows = list(dashboard.month_windows(date(2025, 12, 20), date(2026, 2, 3)))
    assert windows == [(date(2025, 12, 20), date(2025, 12, 31)), (date(2026, 1, 1), date(2026, 1, 31)), (date(2026, 2, 1), date(2026, 2, 3))]


def test_monthly_failure_preserves_gap(monkeypatch):
    async def fail(*args, **kwargs):
        raise RuntimeError('Disconnected')
    monkeypatch.setattr(dashboard.TallyClient, 'send_xml', fail)
    result = asyncio.run(dashboard._fetch_monthly_income_expense_series('Example company', START, START))
    assert result[0]['income'] is None
    assert result[0]['expense'] is None
    assert result[0]['status'] == 'unavailable'


def test_api_preserves_purchase_and_validates_dates(monkeypatch):
    app = FastAPI()
    app.include_router(dashboard.router)
    app.dependency_overrides[get_authorized_company] = lambda: 'Example company'

    async def fetch(company, start, end):
        assert company == 'Example company'
        assert (start, end) == (START, END)
        return reports(), {}

    async def series(*args):
        return []

    monkeypatch.setattr(dashboard, 'fetch_dashboard_reports', fetch)
    monkeypatch.setattr(dashboard, '_fetch_monthly_income_expense_series', series)
    client = TestClient(app)
    response = client.get('/summary', params={'from_date': START.isoformat(), 'to_date': END.isoformat()})
    assert response.status_code == 200
    assert response.json()['data']['total_purchases'] == 16800000.0
    assert client.get('/summary', params={'from_date': END.isoformat(), 'to_date': START.isoformat()}).status_code == 422


def test_api_remains_authenticated(monkeypatch):
    monkeypatch.setenv('CHAT_AUTH_ENABLED', 'true')
    app = FastAPI()
    app.include_router(dashboard.router)
    assert TestClient(app).get('/summary').status_code in (401, 403)
