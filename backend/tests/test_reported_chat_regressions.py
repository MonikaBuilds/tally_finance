"""Regressions for the reported chatbot screenshots; no live services required."""
from datetime import date
from unittest.mock import AsyncMock

import pytest

from app.chatbot import service, tools
from app.chatbot.date_resolver import InvalidDateRange, resolve_date_range
from app.chatbot.formatter import format_tool_response
from app.chatbot.intent_router import detect_local_intent
from app.chatbot.tool_registry import TOOL_DEFINITIONS, TOOL_FUNCTIONS
from app.security.permissions import DEFAULT_TOOL_PERMISSIONS
from app.tally import service as tally_service


@pytest.mark.parametrize('text,start,end', [
    ('revenue on 15 August 2025', date(2025, 8, 15), date(2025, 8, 15)),
    ('revenue on 15th August 2025', date(2025, 8, 15), date(2025, 8, 15)),
    ('revenue on 2025-08-15', date(2025, 8, 15), date(2025, 8, 15)),
    ('revenue on 15/08/2025', date(2025, 8, 15), date(2025, 8, 15)),
    ('revenue on 15-08-2025', date(2025, 8, 15), date(2025, 8, 15)),
    ('revenue in August 2025', date(2025, 8, 1), date(2025, 8, 31)),
    ('from 1 April 2025 to 31 March 2026', date(2025, 4, 1), date(2026, 3, 31)),
    ('from 2025-04-01 to 2026-03-31', date(2025, 4, 1), date(2026, 3, 31)),
    ('FY 2025-26', date(2025, 4, 1), date(2026, 3, 31)),
])
def test_specific_dates_precede_months(text, start, end):
    period = resolve_date_range(text, today=date(2026, 11, 26))
    assert (period.from_date, period.to_date) == (start, end)


@pytest.mark.parametrize('text', ['revenue on 31 February 2025', 'revenue on 2025-02-31'])
def test_impossible_day_does_not_become_a_month(text):
    with pytest.raises(InvalidDateRange):
        resolve_date_range(text)


@pytest.mark.parametrize('text,expected', [
    ('show me my pending bills', 'get_pending_invoices'),
    ('Which invoices are pending?', 'get_pending_invoices'),
    ('show pending invoices', 'get_pending_invoices'),
    ('show me all ledgers', 'get_ledger_list'),
    ('list ledgers', 'get_ledger_list'),
    ('show me the opening balance', 'follow_up_opening_balance'),
])
def test_common_queries_skip_ai(text, expected):
    assert detect_local_intent(text) == expected


@pytest.mark.parametrize('text,tool,key,name', [
    ('list the voucher in HDFC Bank from 1 April 2025 to 31 March 2026',
     'get_ledger_transactions', 'ledger_name', 'HDFC Bank'),
    ('show transactions of HDFC Bank last month',
     'get_ledger_transactions', 'ledger_name', 'HDFC Bank'),
    ('show complete details of HDFC Bank for August 2025',
     'get_ledger_report', 'ledger_name', 'HDFC Bank'),
    ('show customer statement for Eagle Paradise Pvt. Ltd. from 1 April 2025 to 31 March 2026',
     'get_customer_statement', 'party_name', 'Eagle Paradise Pvt. Ltd.'),
    ('show supplier statement for Apex Office Solutions last month',
     'get_supplier_statement', 'party_name', 'Apex Office Solutions'),
    ('show the opening balance of HDFC Bank from 1 April 2025 to 31 March 2026',
     'get_ledger_balance', 'ledger_name', 'HDFC Bank'),
])
def test_entity_names_exclude_periods(text, tool, key, name):
    result = detect_local_intent(text)
    assert result['tool_name'] == tool
    assert result['arguments'][key] == name


def test_ledger_list_is_registered_and_permission_protected():
    assert TOOL_FUNCTIONS['get_ledger_list'] is tools.get_ledger_list_tool
    assert DEFAULT_TOOL_PERMISSIONS['get_ledger_list'] == 'financial'
    assert any(d['name'] == 'get_ledger_list' for d in TOOL_DEFINITIONS)


@pytest.mark.asyncio
async def test_ledger_list_uses_selected_company(monkeypatch):
    fetch = AsyncMock(return_value=[{'name': 'HDFC Bank', 'parent': 'Bank Accounts'}])
    monkeypatch.setattr(tools, 'fetch_ledger_list', fetch)
    result = await tools.get_ledger_list_tool('ABC Pvt Ltd')
    fetch.assert_awaited_once_with(company_name='ABC Pvt Ltd')
    assert 'HDFC Bank' in format_tool_response('get_ledger_list', result)


@pytest.mark.asyncio
async def test_profit_uses_named_result_rather_than_raw_sign(monkeypatch):
    native = {
        'period_verified': True,
        'lines': dict.fromkeys(['sales_accounts', 'direct_incomes', 'indirect_incomes',
                               'purchase_accounts', 'direct_expenses', 'indirect_expenses', 'closing_stock']),
        'nett_profit': {'amount': -519053.47}, 'nett_loss': None,
        'tally_from_date': '2025-04-01', 'tally_to_date': '2026-03-31',
    }
    monkeypatch.setattr(tools, 'fetch_native_profit_loss_summary', AsyncMock(return_value=native))
    result = await tools.get_net_profit_tool()
    assert result['data']['result_type'] == 'profit'
    assert result['data']['amount'] == 519053.47
    assert 'net profit' in format_tool_response('get_net_profit', result)


@pytest.mark.asyncio
async def test_period_ledger_opening_uses_report_not_master(monkeypatch):
    monkeypatch.setattr(tools, 'fetch_ledger_list', AsyncMock(return_value=[{
        'name': 'HDFC Bank', 'opening_balance': 999, 'closing_balance': 999,
    }]))
    report = AsyncMock(return_value={'opening_balance': -50000, 'closing_balance': -10000})
    monkeypatch.setattr(tools, 'fetch_ledger_report', report)
    start, end = date(2025, 4, 1), date(2026, 3, 31)
    result = await tools.get_ledger_balance_tool('HDFC Bank', 'ABC', start, end, 'opening')
    report.assert_awaited_once_with(ledger_name='HDFC Bank', company_name='ABC', from_date=start, to_date=end)
    assert result['data']['opening_balance'] == -50000
    assert 'opening balance' in format_tool_response('get_ledger_balance', result)
    assert '999' not in format_tool_response('get_ledger_balance', result)


@pytest.mark.asyncio
async def test_missing_balance_is_not_zero(monkeypatch):
    monkeypatch.setattr(tools, 'fetch_ledger_list', AsyncMock(return_value=[{'name': 'HDFC Bank'}]))
    result = await tools.get_ledger_balance_tool('HDFC Bank')
    assert result['data']['closing_balance'] is None
    assert 'did not return' in format_tool_response('get_ledger_balance', result)


@pytest.mark.parametrize('derived', [False, True])
@pytest.mark.asyncio
async def test_opening_difference_is_selected_and_labelled(monkeypatch, derived):
    fetch = AsyncMock(return_value={
        'liabilities': [{'name': 'Loans', 'amount': 500000},
                        {'name': 'Difference in opening balances', 'amount': 10500000, 'derived': derived}],
        'assets': [{'name': 'Current Assets', 'amount': 11000000}],
    })
    monkeypatch.setattr(tools, 'fetch_balance_sheet_report', fetch)
    result = await tools.get_balance_sheet_tool('ABC', date(2026, 3, 31), date(2025, 4, 1), True)
    assert result['data']['amount'] == 10500000
    assert (result.get('calculation_method') == 'application_aggregation') is derived
    answer = format_tool_response('get_balance_sheet', result)
    assert 'Difference in opening balances' in answer
    assert 'Loans' not in answer


@pytest.mark.asyncio
async def test_balance_sheet_xml_keeps_both_dates(monkeypatch):
    send = AsyncMock(return_value='<ENVELOPE/>')
    monkeypatch.setattr(tally_service.client, 'send_xml', send)
    await tally_service.fetch_balance_sheet(from_date=date(2025, 4, 1), to_date=date(2026, 3, 31))
    request = send.await_args.args[0]
    assert '<SVFROMDATE>20250401</SVFROMDATE>' in request
    assert '<SVTODATE>20260331</SVTODATE>' in request


@pytest.mark.parametrize('question,tool,extra', [
    ('what was the revenue on 15 August 2025', 'get_revenue', {}),
    ('show trial balance on 15 August 2025', 'get_trial_balance', {}),
    ('show balance sheet as of 15 August 2025', 'get_balance_sheet', {}),
    ('show the difference in opening balance from balance sheet from 1 April 2025 to 31 March 2026',
     'get_balance_sheet', {'opening_difference_only': True}),
    ('show me all ledgers', 'get_ledger_list', {}),
    ('show me my pending bills', 'get_pending_invoices', {}),
    ('list the voucher in HDFC Bank from 1 April 2025 to 31 March 2026',
     'get_ledger_transactions', {'ledger_name': 'HDFC Bank'}),
])
@pytest.mark.asyncio
async def test_screenshot_queries_reach_executor_without_ai(monkeypatch, question, tool, extra):
    execute = AsyncMock(return_value={'success': True, 'source': 'tally', 'data': {}})
    select = AsyncMock(side_effect=AssertionError('Common query must not call AI'))
    monkeypatch.setattr(service, 'execute_tool', execute)
    monkeypatch.setattr(service, '_cached_select_tool', select)
    monkeypatch.setattr(service, 'save_session_state', AsyncMock())
    await service.process_chat_message(question, company_name='ABC')
    select.assert_not_awaited()
    assert execute.await_args.kwargs['tool_name'] == tool
    args = execute.await_args.kwargs['arguments']
    assert args['company_name'] == 'ABC'
    assert all(args[k] == v for k, v in extra.items())
    if '15 August' in question:
        assert args['to_date'] == '15-08-2025'
        if tool in {'get_trial_balance', 'get_balance_sheet'}:
            assert 'from_date' not in args
        else:
            assert args['from_date'] == '15-08-2025'
    if '1 April' in question:
        assert args['from_date'] == '01-04-2025'
        assert args['to_date'] == '31-03-2026'


@pytest.mark.asyncio
async def test_opening_follow_up_uses_entity_and_period(monkeypatch):
    monkeypatch.setattr(service, 'get_session_state', AsyncMock(return_value={
        'last_entity': 'HDFC Bank',
        'last_period': {'from_date': '01-04-2025', 'to_date': '31-03-2026'},
    }))
    monkeypatch.setattr(service, 'save_session_state', AsyncMock())
    execute = AsyncMock(return_value={'success': True, 'source': 'tally', 'data': {'opening_balance': 1000, 'balance_type': 'opening'}})
    monkeypatch.setattr(service, 'execute_tool', execute)
    result = await service.process_chat_message('show me the opening balance', company_name='ABC')
    assert result['success']
    assert 'opening balance' in result['answer']
    assert execute.await_args.kwargs['arguments'] == {
        'ledger_name': 'HDFC Bank', 'balance_type': 'opening',
        'from_date': '01-04-2025', 'to_date': '31-03-2026', 'company_name': 'ABC',
    }


@pytest.mark.asyncio
async def test_ambiguous_opening_balance_does_not_return_trial_balance(monkeypatch):
    monkeypatch.setattr(service, 'get_session_state', AsyncMock(return_value=None))
    execute = AsyncMock()
    monkeypatch.setattr(service, 'execute_tool', execute)
    result = await service.process_chat_message('show me the opening balance')
    assert 'specify the ledger' in result['answer']
    execute.assert_not_awaited()



@pytest.mark.parametrize("question", [
    "revenue on 31 February 2025", "revenue on 2025-02-31",
    "revenue from 31 March 2026 to 1 April 2025",
    "revenue from 2026-03-31 to 2025-04-01",
    "revenue from 31-03-2026 to 01-04-2025",
])
@pytest.mark.asyncio
async def test_invalid_explicit_dates_never_query_a_different_period(monkeypatch, question):
    execute = AsyncMock()
    monkeypatch.setattr(service, "execute_tool", execute)
    result = await service.process_chat_message(question)
    assert result["intent"] == "invalid_date"
    execute.assert_not_awaited()


@pytest.mark.parametrize("name", ["Rent May", "Bank May", "April Services", "Eagle Paradise Pvt. Ltd."])
def test_month_words_in_ledger_names_are_preserved(name):
    from app.chatbot.intent_router import _clean_ledger_name
    assert _clean_ledger_name(name) == name


@pytest.mark.parametrize("query,tool,arguments", [
    ("Show all journal entries for FY 2025-26", "get_day_book", {"voucher_type": "Journal"}),
    ("Show contra entries for FY 2025-26", "get_day_book", {"voucher_type": "Contra"}),
    ("Show every sales voucher with item details for FY 2025-26", "get_sales_transactions", {}),
    ("List all purchase entries for April 2025", "get_purchase_transactions", {}),
    ("List all sales for December 2025", "get_sales_transactions", {}),
])
def test_voucher_families_are_not_treated_as_ledger_or_item_names(query, tool, arguments):
    result = detect_local_intent(query)
    if isinstance(result, str):
        assert result == tool
    else:
        assert result["tool_name"] == tool
        assert result["arguments"] == arguments


@pytest.mark.asyncio
async def test_combined_receipts_and_payments_exclude_other_vouchers(monkeypatch):
    monkeypatch.setattr(tools, "fetch_day_book", AsyncMock(return_value={"rows": [
        {"voucher_type": "Sales"}, {"voucher_type": "Receipt"},
        {"voucher_type": "Payment"}, {"voucher_type": "Contra"},
    ]}))
    intent = detect_local_intent("Show today's receipts and payments")
    assert intent["tool_name"] == "get_day_book"
    result = await tools.get_day_book_tool(**intent["arguments"])
    assert [r["voucher_type"] for r in result["data"]["rows"]] == ["Receipt", "Payment"]


@pytest.mark.parametrize("query,tool", [
    ("Who owes us money?", "get_receivables"),
    ("Whom do I need to pay?", "get_payables"),
    ("What do we owe Apex Office Solutions?", "get_party_outstanding_summary"),
])
def test_outstanding_direction_does_not_require_ai(query, tool):
    result=detect_local_intent(query)
    assert (result if isinstance(result,str) else result["tool_name"]) == tool


def test_explicit_calendar_year_does_not_use_current_company_period():
    period=resolve_date_range("What was my revenue in 2015?")
    assert (period.from_date, period.to_date) == (date(2015,1,1), date(2015,12,31))


@pytest.mark.parametrize("query,tool", [
    ("Show all transactions from 1 April 2025 to 31 March 2026", "get_day_book"),
    ("Show bank transactions for FY 2025-26", "get_bank_transactions"),
    ("Show receipts for FY 2025-26", "get_receipt_transactions"),
    ("Show sales for December 2025", "get_sales_transactions"),
    ("Show all overdue customer balances", "get_overdue_receivables"),
    ("Top 5 customers who owe us", "get_top_receivables"),
    ("Ageing analysis of receivables", "get_aged_receivables"),
    ("Show overdue payables", "get_overdue_payables"),
    ("Compare profit and loss of December 2025 vs January 2026", "get_period_comparison"),
])
def test_live_acceptance_routing_regressions(query, tool):
    result=detect_local_intent(query)
    assert (result if isinstance(result,str) else result["tool_name"]) == tool


def test_combined_outstanding_request_returns_both_sides():
    assert detect_local_intent("What are my outstanding receivables and payables?") == "get_outstanding_summary"


def test_trial_balance_footer_is_labelled_as_a_sum_of_native_rows():
    result={"success": True,"source": "tally","data": {"rows": [
        {"name": "Cash", "debit": 100, "credit": 0},
        {"name": "Bank", "debit": 200, "credit": 0},
    ]}}
    answer=format_tool_response("get_trial_balance",result)
    assert "derived from displayed rows" in answer
    assert "Cash" in answer and "Bank" in answer
