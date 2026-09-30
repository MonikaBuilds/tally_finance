"""Dashboard-only contracts using captured report shapes and boundary cases."""

import asyncio
from datetime import date, datetime
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


def native_pl(start=START, end=END, company='Example company', rows=()):
    return parse_native_table(table([
        [company],
        ['Particulars', f"{start.strftime('%-d-%b-%y')} to {end.strftime('%-d-%b-%y')}"],
        *rows,
    ]))


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
    result = map_dashboard_summary({'profit_loss': parse_profit_loss_rows(pl_xml(purchase=raw)), 'profit_loss_totals': native_pl()}, START, END, 'Example company')
    assert result['total_purchases'] == expected
    assert result['metric_sources']['total_purchases']['raw'] == raw


def test_sales_and_expenses_do_not_include_stock_purchase_or_profit():
    result = map_dashboard_summary(reports(), START, END, 'Example company')
    assert result['total_sales'] == 7410000.0
    assert result['sales_breakdown'] == [{'label': 'Sales Accounts', 'value': 7410000.0}]
    assert result['expense_breakdown'] == [{'label': 'Indirect Expenses', 'value': -270000.0}]
    assert result['net_loss'] == 265000.0
    assert result['net_profit'] == 0.0  # Verified period with Net Loss derives Net Profit of 0.0


def test_net_result_requires_same_company_and_period():
    assert map_dashboard_summary(reports(), START, END, 'Other company')['net_loss'] is None
    assert map_dashboard_summary(reports(), START, date(2026, 9, 28), 'Example company')['net_loss'] is None


def test_tax_totals_are_not_inferred_from_duties_balances():
    source = reports()
    source['groups'].append({'name': 'Duties & Taxes', 'amount': 198900.0})
    result = map_dashboard_summary(source, START, END, 'Example company')
    assert result['gst_payable'] is None
    assert result['tds_payable'] is None


def test_gst_payable_computed_from_cgst_sgst_ledgers():
    source = reports()
    source['ledgers'].extend([
        {'name': 'Input CGST', 'parent': 'Duties & Taxes', 'amount': -567450.0, 'raw': '-567450.00'},
        {'name': 'Input SGST', 'parent': 'Duties & Taxes', 'amount': -567450.0, 'raw': '-567450.00'},
        {'name': 'Output CGST', 'parent': 'Duties & Taxes', 'amount': 666900.0, 'raw': '666900.00'},
        {'name': 'Output SGST', 'parent': 'Duties & Taxes', 'amount': 666900.0, 'raw': '666900.00'},
    ])
    result = map_dashboard_summary(source, START, END, 'Example company')
    assert result['gst_payable'] == 198900.0
    assert result['tds_payable'] == 0.0


def test_tds_payable_computed_from_tds_ledgers():
    source = reports()
    source['ledgers'].extend([
        {'name': 'TDS Payable', 'parent': 'Duties & Taxes', 'amount': 25000.0, 'raw': '25000.00'},
        {'name': 'Output CGST', 'parent': 'Duties & Taxes', 'amount': 50000.0, 'raw': '50000.00'},
    ])
    result = map_dashboard_summary(source, START, END, 'Example company')
    assert result['tds_payable'] == 25000.0
    assert result['gst_payable'] == 50000.0


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

    async def series(*args, **kwargs):
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


def test_sales_breakdown_includes_income_lines_of_the_same_pl():
    rows = parse_profit_loss_rows(pl_xml().replace('</ENVELOPE>', '''
    <DSPACCNAME><DSPDISPNAME>Indirect Incomes</DSPDISPNAME></DSPACCNAME>
    <PLAMT><BSMAINAMT>12500.00</BSMAINAMT></PLAMT>
    </ENVELOPE>'''))
    result = map_dashboard_summary({'profit_loss': rows, 'profit_loss_totals': native_pl()}, START, END, 'Example company')
    assert result['sales_breakdown'] == [
        {'label': 'Sales Accounts', 'value': 7410000.0},
        {'label': 'Indirect Incomes', 'value': 12500.0},
    ]


def test_monthly_series_skips_months_after_today(monkeypatch):
    requested = []

    async def send(self, xml):
        root = ET.fromstring(xml)
        if root.findtext('.//SVEXPORTFORMAT') != '$$SysName:HTML':
            # Signed values come from the XML export.
            return pl_xml(sales='-500000.00')
        requested.append(root.findtext('.//SVFROMDATE'))
        start = datetime.strptime(root.findtext('.//SVFROMDATE'), '%Y%m%d').date()
        end = datetime.strptime(root.findtext('.//SVTODATE'), '%Y%m%d').date()
        # The HTML report confirms the period; its amounts carry no sign.
        return table([
            ['Example company'],
            ['Particulars', f"{start.strftime('%-d-%b-%y')} to {end.strftime('%-d-%b-%y')}"],
            ['', 'Sales Accounts', '', '5,00,000.00'],
        ])

    monkeypatch.setattr(dashboard.TallyClient, 'send_xml', send)
    result = asyncio.run(dashboard._fetch_monthly_income_expense_series(
        'Example company', START, END, today=date(2025, 6, 15),
    ))
    assert requested == ['20250401', '20250501', '20250601']
    assert [point['month'] for point in result] == ['Apr 2025', 'May 2025', 'Jun 2025']
    assert result[-1]['to_date'] == '2025-06-15'
    assert result[0]['income'] == -500000.0
    assert result[0]['expense'] == 16800000.0
    assert result[0]['status'] == 'available'


def test_monthly_series_is_empty_for_a_future_period(monkeypatch):
    async def send(self, xml):
        raise AssertionError('Tally must not be queried for future months')

    monkeypatch.setattr(dashboard.TallyClient, 'send_xml', send)
    result = asyncio.run(dashboard._fetch_monthly_income_expense_series(
        'Example company', START, END, today=date(2025, 3, 1),
    ))
    assert result == []


def test_missing_outstanding_report_is_not_described_as_a_date_mismatch():
    result = map_dashboard_summary(reports(), START, END, 'Example company')
    assert result['payables'] is None
    assert result['top_payables'] is None
    assert result['metric_sources']['payables']['message'].startswith('Tally did not return')


def test_summary_and_monthly_are_separate_endpoints(monkeypatch):
    app = FastAPI()
    app.include_router(dashboard.router)
    app.dependency_overrides[get_authorized_company] = lambda: 'Example company'

    async def fetch(company, start, end):
        return reports(), {}

    async def series(company, start, end, **kwargs):
        assert kwargs['is_disconnected'] is not None
        return [{'month': 'Apr 2025', 'income': 1.0, 'expense': 2.0}]

    monkeypatch.setattr(dashboard, 'fetch_dashboard_reports', fetch)
    monkeypatch.setattr(dashboard, '_fetch_monthly_income_expense_series', series)
    client = TestClient(app)
    params = {'from_date': START.isoformat(), 'to_date': END.isoformat()}

    summary = client.get('/summary', params=params).json()['data']
    assert 'income_vs_expense' not in summary

    monthly = client.get('/monthly', params=params)
    assert monthly.status_code == 200
    assert monthly.json()['data']['income_vs_expense'][0]['income'] == 1.0
    assert client.get('/monthly', params={'from_date': END.isoformat(), 'to_date': START.isoformat()}).status_code == 422


def test_monthly_series_stops_when_the_client_leaves(monkeypatch):
    requested = []

    async def send(self, xml):
        requested.append(xml)
        return pl_xml()

    checks = iter([False, True])

    async def is_disconnected():
        return next(checks, True)

    monkeypatch.setattr(dashboard.TallyClient, 'send_xml', send)
    result = asyncio.run(dashboard._fetch_monthly_income_expense_series(
        'Example company', START, END, today=date(2025, 12, 1),
        is_disconnected=is_disconnected,
    ))
    assert len(requested) == 1
    assert len(result) == 1


def test_pl_figures_hidden_when_tally_uses_a_different_period():
    source = reports()
    # Tally substituted the whole year for a one-month request.
    result = map_dashboard_summary(source, date(2025, 4, 1), date(2025, 4, 30), 'Example company')
    assert result['period_verified'] is False
    for key in ('total_sales', 'total_purchases', 'net_profit', 'net_loss'):
        assert result[key] is None
        assert '1-Apr-2025 to 31-Mar-2026' in result['metric_sources'][key]['message']
    assert result['sales_breakdown'] is None
    assert result['expense_breakdown'] is None


def test_monthly_point_with_substituted_period_is_left_empty(monkeypatch):
    async def send(self, xml):
        return table([
            ['Example company'], ['Particulars', '1-Apr-25 to 31-Mar-26'],
            ['', 'Sales Accounts', '', '74,10,000.00'],
        ])

    monkeypatch.setattr(dashboard.TallyClient, 'send_xml', send)
    result = asyncio.run(dashboard._fetch_monthly_income_expense_series(
        'Example company', date(2025, 4, 1), date(2025, 4, 30), today=date(2025, 6, 1),
    ))
    assert result[0]['status'] == 'unverified'
    assert result[0]['income'] is None
    assert (result[0]['tally_from_date'], result[0]['tally_to_date']) == ('2025-04-01', '2026-03-31')


@pytest.mark.parametrize('start,end,expected', [
    (date(2025, 4, 1), date(2026, 3, 31), (date(2024, 4, 1), date(2025, 3, 31))),
    (date(2025, 5, 1), date(2025, 5, 31), (date(2025, 4, 1), date(2025, 4, 30))),
    (date(2025, 1, 1), date(2025, 3, 31), (date(2024, 10, 1), date(2024, 12, 31))),
    (date(2025, 6, 10), date(2025, 6, 16), (date(2025, 6, 3), date(2025, 6, 9))),
])
def test_previous_period(start, end, expected):
    from app.tally.dashboard import previous_period
    assert previous_period(start, end) == expected


def test_comparison_uses_the_verified_previous_period():
    source = reports()
    prev_start, prev_end = date(2024, 4, 1), date(2025, 3, 31)
    source['previous_profit_loss'] = parse_profit_loss_rows(pl_xml(sales='5000000.00'))
    source['previous_profit_loss_totals'] = native_pl(prev_start, prev_end, rows=[['', 'Nett Profit', '', '1,00,000.00']])
    comparison = map_dashboard_summary(source, START, END, 'Example company')['comparison']
    assert comparison['period_verified'] is True
    assert comparison['total_sales'] == 5000000.0
    assert comparison['net_profit'] == 100000.0
    assert comparison['net_loss'] == 0.0
    assert (comparison['from_date'], comparison['to_date']) == ('2024-04-01', '2025-03-31')

    source['previous_profit_loss_totals'] = native_pl(START, END)
    unverified = map_dashboard_summary(source, START, END, 'Example company')['comparison']
    assert unverified['period_verified'] is False
    assert unverified['total_sales'] is None


def test_ageing_buckets_follow_days_overdue():
    from app.api.dashboard_mapper import ageing
    buckets = ageing([
        {'amount': 100.0, 'days_overdue': None},
        {'amount': 50.0, 'days_overdue': 0},
        {'amount': 10.0, 'days_overdue': 30},
        {'amount': 20.0, 'days_overdue': 31},
        {'amount': 30.0, 'days_overdue': 90},
        {'amount': 40.0, 'days_overdue': 364},
        {'amount': None, 'days_overdue': 5},
    ])
    assert [(b['key'], b['amount'], b['count']) for b in buckets] == [
        ('not_due', 150.0, 2), ('1_30', 10.0, 1), ('31_60', 20.0, 1),
        ('61_90', 30.0, 1), ('over_90', 40.0, 1),
    ]


def test_summary_includes_ageing_for_verified_outstanding():
    result = map_dashboard_summary({'receivables': parse_outstanding_table(outstanding_html())}, START, END, 'Example company')
    assert result['receivables_ageing'][-1] == {'key': 'over_90', 'label': 'Over 90 days', 'amount': 80000.25, 'count': 1}
    assert map_dashboard_summary({}, START, END, 'Example company')['receivables_ageing'] is None


def test_html_amount_reads_tally_negative_notation():
    from app.tally.dashboard import html_amount
    assert html_amount('(-)5,00,000.00') == -500000.0
    assert html_amount('5,00,000.00') == 500000.0
    assert html_amount('') is None


def test_confirmed_month_without_lines_has_no_entries(monkeypatch):
    async def send(self, xml):
        if '$$SysName:HTML' in xml:
            return table([['Example company'], ['Particulars', '1-May-25 to 31-May-25'], ['', 'Opening Stock', '', '1.00']])
        return '<ENVELOPE><DSPACCNAME><DSPDISPNAME>Opening Stock</DSPDISPNAME></DSPACCNAME><PLAMT><BSMAINAMT>1.00</BSMAINAMT></PLAMT></ENVELOPE>'

    monkeypatch.setattr(dashboard.TallyClient, 'send_xml', send)
    result = asyncio.run(dashboard._fetch_monthly_income_expense_series(
        'Example company', date(2025, 5, 1), date(2025, 5, 31), today=date(2025, 6, 1),
    ))
    assert result[0]['status'] == 'no_entries'
    assert result[0]['income'] is None


def test_line_missing_from_a_confirmed_pl_means_no_entries():
    rows = [row for row in parse_profit_loss_rows(pl_xml()) if 'Purchase' not in row['name']]
    result = map_dashboard_summary({'profit_loss': rows, 'profit_loss_totals': native_pl()}, START, END, 'Example company')
    assert result['total_purchases'] is None
    assert result['metric_sources']['total_purchases']['status'] == 'none'
    assert result['metric_sources']['total_purchases']['message'] == 'No purchase entries in Tally for this period.'


def test_blank_line_in_a_confirmed_pl_means_no_entries():
    result = map_dashboard_summary({'profit_loss': parse_profit_loss_rows(pl_xml(purchase='')), 'profit_loss_totals': native_pl()}, START, END, 'Example company')
    assert result['total_purchases'] is None
    assert result['metric_sources']['total_purchases']['status'] == 'none'
    assert result['metric_sources']['total_purchases']['raw'] == ''
