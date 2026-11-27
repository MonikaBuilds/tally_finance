from datetime import date
from io import BytesIO
from unittest.mock import AsyncMock
from urllib.parse import urlparse

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from openpyxl import load_workbook

from app.chatbot import context, exports, monthly, service, tools
from app.chatbot.intent_router import detect_local_intent
from app.chatbot.formatter import format_tool_response
from app.api import chat
from app.security.auth import UserContext, get_current_user


@pytest.fixture(autouse=True)
def isolated_cache(monkeypatch):
    monkeypatch.setattr(exports.cache_manager, 'set_entry', AsyncMock(return_value=False))
    monkeypatch.setattr(exports.cache_manager, 'get_entry', AsyncMock(return_value=(None, None, None)))
    exports._local.clear()


def token(download):
    return urlparse(download['url']).path.rsplit('/', 1)[1].split('.')[0]


@pytest.mark.asyncio
async def test_snapshot_scope_immutability_full_rows_and_excel_types():
    rows = [{'name': '=SUM(1,2)' if i == 0 else f'Item {i}', 'amount': -i - .25} for i in range(85)]
    result = {'success': True, 'source': 'tally', 'data': {'rows': rows}}
    link = await exports.save_export('alice', 'org1', 'ABC', 'get_stock_summary', {}, result, '85 rows')
    rows[0]['amount'] = 999
    record = await exports.load_export('alice', 'org1', 'abc', token(link))
    assert record['result']['data']['rows'][0]['amount'] == -.25
    for user, org, company in [('bob','org1','ABC'), ('alice','org2','ABC'), ('alice','org1','XYZ')]:
        assert await exports.load_export(user, org, company, token(link)) is None
    workbook = load_workbook(BytesIO(exports.export_excel(record)))
    cells = [c for sheet in workbook for row in sheet for c in row]
    assert len([c for c in cells if isinstance(c.value, str) and c.value.startswith('Item ')]) == 84
    assert next(c for c in cells if c.value == '=SUM(1,2)').data_type == 's'
    assert any(c.value == -84.25 and c.data_type == 'n' for c in cells)
    record['result']['data']['rows'].clear()
    assert len((await exports.load_export('alice','org1','ABC',token(link)))['result']['data']['rows']) == 85


@pytest.mark.asyncio
async def test_expired_snapshots_and_size_limit(monkeypatch):
    link = await exports.save_export('alice','org','ABC','get_stock_items',{}, {'data':{'rows':[{'name':'a'}]}},'ok')
    monkeypatch.setattr(exports.time, 'time', lambda: 999999999999)
    assert await exports.load_export('alice','org','ABC',token(link)) is None
    monkeypatch.setattr(exports, 'MAX_SNAPSHOT_BYTES', 5)
    assert await exports.save_export('alice','org','ABC','get_stock_items',{}, {'data':{}},'ok') is None


@pytest.mark.asyncio
async def test_excel_route_auth_scope_and_revoked_permission(monkeypatch):
    link = await exports.save_export('alice','org','ABC','get_stock_items',{}, {'data':{'rows':[{'name':'a','qty':2}]}},'ok')
    app = FastAPI(); app.include_router(chat.router)
    with TestClient(app) as client:
        assert client.get(link['url']).status_code == 401
        app.dependency_overrides[get_current_user] = lambda: UserContext(user_id='alice',allowed_companies=('ABC',),organization_id='org')
        monkeypatch.setattr(chat,'can_execute_tool',lambda *_: True)
        response=client.get(link['url']); assert response.status_code == 200
        assert response.content.startswith(b'PK') and response.headers['cache-control'] == 'no-store'
        assert client.get(link['url'].replace('company_name=ABC','company_name=XYZ')).status_code == 403
        monkeypatch.setattr(chat,'can_execute_tool',lambda *_: False)
        assert client.get(link['url']).status_code == 403
        monkeypatch.setattr(chat,'can_execute_tool',lambda *_: True)
        app.dependency_overrides[get_current_user] = lambda: UserContext(user_id='bob',allowed_companies=('ABC',),organization_id='org')
        assert client.get(link['url']).status_code == 410


@pytest.mark.parametrize('message,start,end', [
    ('What about March?', '01-03-2026','31-03-2026'),
    ('And January', '01-01-2026','31-01-2026'),
    ('How about March 2025?', '01-03-2025','31-03-2025'),
    ('For the same period last year','01-12-2024','31-12-2024'),
])
def test_follow_up_financial_year_and_explicit_year(message,start,end):
    session={'last_tool':'get_ledger_transactions','last_arguments':{'ledger_name':'HDFC'},'last_period':{'from_date':'2025-12-01','to_date':'2025-12-31'}}
    selected=context.follow_up_selection(message,session,service.DATE_AWARE_TOOLS)
    assert selected['arguments'] == {'ledger_name':'HDFC','from_date':start,'to_date':end}


def test_follow_up_entity_leap_year_and_no_context():
    session={'last_tool':'get_ledger_transactions','last_arguments':{'ledger_name':'HDFC','from_date':'01-02-2024','to_date':'29-02-2024'},'last_period':{'from_date':'01-02-2024','to_date':'29-02-2024'}}
    assert context.follow_up_selection('and same month last year',session,service.DATE_AWARE_TOOLS)['arguments']['to_date']=='28-02-2023'
    assert context.follow_up_selection('what about SBI Bank',session,service.DATE_AWARE_TOOLS)['arguments']['ledger_name']=='SBI Bank'
    assert context.follow_up_selection('and March',None,service.DATE_AWARE_TOOLS) is None


@pytest.mark.parametrize('query,metric', [('monthly sales','revenue'),('show purchases month wise','purchases'),('monthly expenses','expenses'),('monthly net profit','net_profit')])
def test_monthly_routing(query,metric):
    assert detect_local_intent(query)['arguments']['metric'] == metric


@pytest.fixture
def ledger_data(monkeypatch):
    monkeypatch.setattr(monthly,'company_financial_year',AsyncMock(return_value=(date(2025,4,1),date(2026,3,31))))
    monkeypatch.setattr(monthly,'fetch_ledger_list',AsyncMock(return_value=[{'name':'Sales','parent':'Nested Sales'},{'name':'Tax','parent':'Duties & Taxes'}]))
    monkeypatch.setattr(monthly,'fetch_native_balances',AsyncMock(return_value=[{'name':'Nested Sales','parent':'Sales Accounts'}]))
    mock=AsyncMock(return_value={'entries':[
        {'date':'2025-04-01','credit':100,'debit':0},
        {'date':'2025-04-30','credit':0,'debit':20},
        {'date':'2025-05-02','credit':10,'debit':0},
        {'date':'2025-05-03','credit':999,'is_cancelled':True},
        {'date':'2025-03-31','credit':888},
    ]})
    monkeypatch.setattr(monthly,'fetch_ledger_report',mock)
    return mock


@pytest.mark.asyncio
async def test_monthly_verified_movements_returns_zero_activity_and_nested_groups(ledger_data):
    result=await monthly.get_monthly_summary_tool(company_name='ABC')
    values=[row['value'] for row in result['data']['periods']]
    assert values == [80,10]+[0]*10
    assert result['calculation_method']=='application_aggregation'
    assert result['data']['ledgers']==['Sales']
    assert ledger_data.call_args.kwargs['to_date']==date(2026,3,31)


@pytest.mark.asyncio
async def test_monthly_partial_period_and_missing_amount(ledger_data):
    result=await monthly.get_monthly_summary_tool('ABC',date(2025,4,15),date(2025,5,2))
    assert [r['value'] for r in result['data']['periods']]==[-20,10]
    ledger_data.return_value={'entries':[{'date':'2025-04-15'}]}
    with pytest.raises(ValueError,match='debit/credit'):
        await monthly.get_monthly_summary_tool('ABC',date(2025,4,15),date(2025,5,2))


@pytest.mark.asyncio
async def test_monthly_native_unverified_is_unavailable_and_loss_negative(monkeypatch):
    native=AsyncMock(side_effect=[{'period_verified':False,'nett_profit':{'amount':500}}, {'period_verified':True,'nett_loss':{'amount':250}}])
    monkeypatch.setattr(monthly,'fetch_native_profit_loss_summary',native)
    result=await monthly.get_monthly_summary_tool('ABC',date(2025,4,1),date(2025,5,31),'net_profit')
    assert [r['value'] for r in result['data']['periods']]==[None,-250]
    assert 'Unavailable' in format_tool_response('get_monthly_summary',result)
    with pytest.raises(ValueError,match='24 months'):
        await monthly.get_monthly_summary_tool('ABC',date(2023,1,1),date(2025,1,1),'net_profit')


@pytest.mark.asyncio
async def test_stock_item_movement_scoped_and_unknown_never_returns_all(monkeypatch):
    monkeypatch.setattr(tools,'fetch_stock_item_list',AsyncMock(return_value=[{'name':'SmartMind AI'}]))
    movement=AsyncMock(return_value={'rows':[{'name':'SmartMind AI','quantity':1}]})
    monkeypatch.setattr(tools,'fetch_tally_stock_movement',movement)
    assert (await tools.get_stock_movement_tool(company_name='ABC',item_name='SmartMind AI'))['success']
    assert movement.call_args.kwargs['stock_item_name']=='SmartMind AI'
    movement.reset_mock()
    assert not (await tools.get_stock_movement_tool(company_name='ABC',item_name='Unknown Widget'))['success']
    movement.assert_not_called()


@pytest.mark.asyncio
async def test_export_follow_up_uses_snapshot_without_tool_or_ai(monkeypatch):
    session='export-turn'
    monkeypatch.setattr(service,'execute_tool',AsyncMock(return_value={'success':True,'source':'tally','data':{'rows':[{'name':'Sales','amount':50}]}}))
    monkeypatch.setattr(service,'can_execute_tool',lambda *_: True)
    first=await service.process_chat_message('show stock summary','ABC',['ABC'],'alice','org',session_id=session)
    service.execute_tool.reset_mock()
    second=await service.process_chat_message('export this to Excel','ABC',['ABC'],'alice','org',session_id=session)
    assert second['success'] and second['downloads']==first['downloads']
    service.execute_tool.assert_not_called()


@pytest.mark.asyncio
async def test_follow_up_period_and_subject_change_integration(monkeypatch):
    execute=AsyncMock(return_value={'success':True,'source':'tally','data':{'ledger_name':'Sales','rows':[]}})
    monkeypatch.setattr(service,'execute_tool',execute)
    args=dict(company_name='ABC',allowed_companies=['ABC'],user_id='follow-user',session_id='period-chain')
    await service.process_chat_message('show transactions of Sales for December 2025',**args)
    await service.process_chat_message('what about March',**args)
    assert execute.call_args.kwargs['arguments']['to_date']=='31-03-2026'
    await service.process_chat_message('now show only cash transactions',**args)
    call=execute.call_args.kwargs
    assert call['tool_name']=='get_cash_transactions' and call['arguments']['to_date']=='31-03-2026'
    assert 'ledger_name' not in call['arguments']

@pytest.mark.asyncio
async def test_stock_details_period_balances_and_pronoun_dates(monkeypatch):
    monkeypatch.setattr(tools,'fetch_stock_item_list',AsyncMock(return_value=[{'name':'SmartMind AI','closing_balance':'999 Nos'}]))
    summary=AsyncMock(return_value={'rows':[{'name':'SmartMind AI','opening_quantity':0,'closing_quantity':2,'closing_value':200}]})
    monkeypatch.setattr(tools,'fetch_tally_stock_summary',summary)
    result=await tools.get_stock_item_details_tool('SmartMind AI','ABC',date(2025,4,1),date(2026,3,31))
    assert result['data']['item']['closing_balance']==2
    assert 'Opening Quantity: 0' in format_tool_response('get_stock_item_details',result)
    execute=AsyncMock(return_value=result)
    monkeypatch.setattr(service,'execute_tool',execute)
    args=dict(company_name='ABC',allowed_companies=['ABC'],user_id='stock-user',session_id='stock-period-chain')
    await service.process_chat_message('show stock item details of SmartMind AI for FY 2025-26',**args)
    await service.process_chat_message('show its stock movements',**args)
    assert execute.call_args.kwargs['arguments']['from_date']=='01-04-2025'
    assert execute.call_args.kwargs['arguments']['item_name']=='SmartMind AI'


@pytest.mark.asyncio
async def test_monthly_metric_follow_up_and_failed_query_clears_export(monkeypatch):
    execute=AsyncMock(return_value={"success":True,"source":"tally","data":{"metric":"revenue","periods":[],"from_date":"2025-04-01","to_date":"2026-03-31"}})
    monkeypatch.setattr(service,"execute_tool",execute)
    args=dict(company_name="ABC",allowed_companies=["ABC"],user_id="monthly-user",session_id="metric-context")
    await service.process_chat_message("monthly sales for FY 2025-26",**args)
    await service.process_chat_message("what about purchases",**args)
    call=execute.call_args.kwargs
    assert call["tool_name"]=="get_monthly_summary" and call["arguments"]["metric"]=="purchases"
    assert call["arguments"]["to_date"]=="31-03-2026"
    execute.return_value={"success":False,"source":"tally","message":"No movements"}
    await service.process_chat_message("what about March",**args)
    exported=await service.process_chat_message("export this to Excel",**args)
    assert not exported["success"] and not exported.get("downloads")


@pytest.mark.asyncio
async def test_comparison_export_rechecks_every_included_company(monkeypatch):
    link=await exports.save_export("alice","org","ABC","get_company_comparison",{"company_names":["ABC","XYZ"]},{"data":{"companies":[]}},"ok")
    app=FastAPI(); app.include_router(chat.router)
    app.dependency_overrides[get_current_user]=lambda: UserContext(user_id="alice",allowed_companies=("ABC",),organization_id="org")
    monkeypatch.setattr(chat,"can_execute_tool",lambda *_: True)
    with TestClient(app) as client:
        assert client.get(link["url"]).status_code==403


@pytest.mark.asyncio
async def test_missing_company_dates_uses_verified_native_period(monkeypatch):
    monkeypatch.setattr(monthly.client,"send_xml",AsyncMock(return_value="<ENVELOPE><COMPANY NAME='ABC'/></ENVELOPE>"))
    native=AsyncMock(return_value={"period_verified":True,"tally_from_date":"2025-04-01","tally_to_date":"2026-03-31"})
    monkeypatch.setattr(monthly,"fetch_native_profit_loss_summary",native)
    assert await monthly.company_financial_year("ABC")== (date(2025,4,1),date(2026,3,31))
    native.return_value={"period_verified":False}
    with pytest.raises(ValueError,match="specify a period"):
        await monthly.company_financial_year("ABC")

@pytest.mark.parametrize('metric,expected,names',[
    ('purchases',150,['Purchases']),('expenses',180,['Purchases','Rent']),
])
@pytest.mark.asyncio
async def test_monthly_purchase_returns_and_expense_groups(monkeypatch,metric,expected,names):
    monkeypatch.setattr(monthly,'fetch_ledger_list',AsyncMock(return_value=[{'name':'Purchases','parent':'Purchase Accounts'},{'name':'Rent','parent':'Indirect Expenses'},{'name':'GST','parent':'Duties & Taxes'}]))
    monkeypatch.setattr(monthly,'fetch_native_balances',AsyncMock(return_value=[]))
    async def report(ledger_name,**kwargs):
        return {'entries':[{'date':'2025-04-15','debit':200,'credit':50}]} if ledger_name=='Purchases' else {'entries':[{'date':'2025-04-15','debit':30,'credit':0}]}
    monkeypatch.setattr(monthly,'fetch_ledger_report',report)
    result=await monthly.get_monthly_summary_tool('ABC',date(2025,4,1),date(2025,4,30),metric)
    assert result['data']['periods'][0]['value']==expected
    assert result['data']['ledgers']==names


@pytest.mark.asyncio
async def test_legacy_trends_never_turn_failed_period_into_zero(monkeypatch):
    monkeypatch.setattr(tools,'get_revenue_tool',AsyncMock(return_value={'success':False}))
    monkeypatch.setattr(tools,'get_expenses_tool',AsyncMock(return_value={'success':True,'data':{'expenses':0}}))
    monkeypatch.setattr(tools,'get_net_profit_tool',AsyncMock(return_value={'success':False}))
    result=await tools.get_financial_trends_tool('ABC',date(2025,4,1),date(2025,4,30))
    row=result['data']['periods'][0]
    assert row['revenue'] is None and row['net_profit'] is None and row['total_expenses']==0
    answer=format_tool_response('get_financial_trends',result)
    assert answer.count('Unavailable')==2


@pytest.mark.asyncio
async def test_obvious_non_financial_query_does_not_depend_on_provider(monkeypatch):
    model=AsyncMock(side_effect=AssertionError("AI must not be called"))
    monkeypatch.setattr(service,"_cached_select_tool",model)
    result=await service.process_chat_message("What is the weather in Delhi today?")
    assert not result["success"] and result["intent"]=="unsupported"
    assert detect_local_intent("show transactions of Weather Ltd")!="unsupported"
    model.assert_not_called()


@pytest.mark.asyncio
async def test_export_preserves_identical_rows_under_different_entities():
    rows=[{"quantity":1.125,"amount":25}]
    link=await exports.save_export("alice","org","ABC","get_ledger_list",{}, {"data":{"ledgers":[{"name":"A","entries":rows},{"name":"B","entries":rows}]}},"ok")
    record=await exports.load_export("alice","org","ABC",token(link))
    spec=exports.snapshot_spec(record)
    entries=[section for section in spec["sections"] if section["title"].endswith("Entries")]
    assert len(entries)==2 and entries[0]["rows"]==entries[1]["rows"]
    assert next(c for c in entries[0]["columns"] if c["key"]=="quantity")["type"]=="qty"


@pytest.mark.parametrize("question,expected",[("what about next month",("01-01-2026","31-01-2026")),("what about previous month",("01-11-2025","30-11-2025")),("and last month",("01-11-2025","30-11-2025"))])
def test_relative_month_follow_up_uses_report_period_not_computer_clock(question,expected):
    session={"last_tool":"get_monthly_summary","last_arguments":{"metric":"revenue"},"last_period":{"from_date":"2025-12-01","to_date":"2025-12-31"}}
    selected=context.follow_up_selection(question,session,service.DATE_AWARE_TOOLS)["arguments"]
    assert (selected["from_date"],selected["to_date"])==expected
