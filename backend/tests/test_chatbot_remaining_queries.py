import pytest
import asyncio

from app.chatbot.intent_router import detect_local_intent
from app.chatbot.tools import get_invoice_details_tool, get_stock_summary_tool
from app.financial.service import build_outstanding_summary
from app.tally.parsers.financial import parse_bill_allocations
import app.chatbot.tools as chatbot_tools


def test_bill_allocation_parser_reads_invoice_and_receipt_rows():
    xml = """
    <ENVELOPE><BODY><DATA>
      <VOUCHER>
        <DATE>20250401</DATE><GUID>sale-guid</GUID>
        <VOUCHERTYPENAME>Sales</VOUCHERTYPENAME><VOUCHERNUMBER>S-1</VOUCHERNUMBER>
        <PARTYLEDGERNAME>Acme Customer</PARTYLEDGERNAME>
        <ALLLEDGERENTRIES.LIST><LEDGERNAME>Acme Customer</LEDGERNAME>
          <BILLALLOCATIONS.LIST><NAME>INV-1</NAME><BILLTYPE>New Ref</BILLTYPE>
            <AMOUNT>-123.00</AMOUNT></BILLALLOCATIONS.LIST>
        </ALLLEDGERENTRIES.LIST>
      </VOUCHER>
      <VOUCHER>
        <DATE>20250410</DATE><GUID>receipt-guid</GUID>
        <VOUCHERTYPENAME>Receipt</VOUCHERTYPENAME><VOUCHERNUMBER>R-1</VOUCHERNUMBER>
        <PARTYLEDGERNAME>Acme Customer</PARTYLEDGERNAME>
        <ALLLEDGERENTRIES.LIST><LEDGERNAME>Acme Customer</LEDGERNAME>
          <BILLALLOCATIONS.LIST><NAME>INV-1</NAME><BILLTYPE>Agst Ref</BILLTYPE>
            <AMOUNT>100.00</AMOUNT></BILLALLOCATIONS.LIST>
        </ALLLEDGERENTRIES.LIST>
      </VOUCHER>
    </DATA></BODY></ENVELOPE>
    """

    rows = parse_bill_allocations(xml)["rows"]
    invoices = build_outstanding_summary(rows)

    assert len(rows) == 2
    assert rows[0]["party"] == "Acme Customer"
    assert rows[0]["bill_reference"] == "INV-1"
    assert rows[0]["bill_date"] == "2025-04-01"
    assert invoices[0]["outstanding_amount"] == 23.0
    assert invoices[0]["status"] == "pending"


def test_cancelled_bill_allocations_are_excluded_from_outstanding():
    rows = [
        {
            "party": "Acme",
            "bill_reference": "INV-CANCELLED",
            "bill_type": "New Ref",
            "voucher_type": "Sales",
            "amount": -250,
            "is_cancelled": True,
        },
    ]

    assert build_outstanding_summary(rows) == []


@pytest.mark.asyncio
async def test_invoice_search_filters_tally_bill_rows(monkeypatch):
    async def fake_bill_allocations(**kwargs):
        return [
            {
                "party": "Acme Customer",
                "bill_reference": "INV-1",
                "bill_date": "2025-04-01",
                "voucher_type": "Sales",
                "voucher_number": "S-1",
                "bill_type": "New Ref",
                "amount": -123.0,
            },
            {
                "party": "Acme Customer",
                "bill_reference": "INV-1",
                "bill_date": "2025-04-10",
                "voucher_type": "Receipt",
                "voucher_number": "R-1",
                "bill_type": "Agst Ref",
                "amount": 100.0,
            },
        ]

    monkeypatch.setattr(
        chatbot_tools,
        "fetch_bill_allocations",
        fake_bill_allocations,
    )

    result = await get_invoice_details_tool(
        party_name="Acme",
        amount=123,
    )

    assert result["success"] is True
    assert result["data"]["count"] == 1
    assert result["data"]["invoices"][0]["invoice_number"] == "INV-1"
    assert result["data"]["invoices"][0]["amount"] == -123.0
    assert "status" not in result["data"]["invoices"][0]


@pytest.mark.asyncio
async def test_invoice_status_search_does_not_calculate_missing_tally_field():
    result = await get_invoice_details_tool(status="paid")

    assert result["success"] is False
    assert "does not include a paid/unpaid status field" in result["message"]


@pytest.mark.asyncio
async def test_stock_valuation_returns_tally_rows_without_adding_a_total(monkeypatch):
    async def fake_stock_valuation(**kwargs):
        return {
            "success": True,
            "count": 1,
            "rows": [{"name": "Item A", "quantity": 4, "value": 72}],
        }

    monkeypatch.setattr(chatbot_tools, "fetch_stock_valuation", fake_stock_valuation)

    result = await get_stock_summary_tool(valuation_only=True)

    assert result["success"] is True
    assert result["calculation_method"] == "tally_report_rows"
    assert result["data"]["valuation_rows"][0]["value"] == 72
    assert "total_stock_value" not in result["data"]


def test_inventory_valuation_phrase_uses_tally_valuation_mode():
    intent = detect_local_intent("Show current inventory valuation")

    assert intent["tool_name"] == "get_stock_summary"
    assert intent["arguments"]["valuation_only"] is True


def test_invoice_party_search_routes_to_existing_invoice_tool():
    intent = detect_local_intent("Show invoices for Acme Customer")

    assert intent["tool_name"] == "get_invoice_details"
    assert intent["arguments"]["party_name"] == "Acme Customer"


@pytest.mark.asyncio
async def test_gemini_timeout_uses_configured_openrouter_fallback(monkeypatch):
    import app.chatbot.gemini_client as gemini_client

    class FakeGeminiModels:
        async def generate_content(self, **kwargs):
            raise asyncio.TimeoutError

    class FakeGeminiClient:
        class aio:
            models = FakeGeminiModels()

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{
                    "message": {
                        "tool_calls": [{
                            "function": {
                                "name": "get_trial_balance",
                                "arguments": "{}",
                            },
                        }],
                    },
                }],
            }

    class FakeHttpClient:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def post(self, url, **kwargs):
            assert url == gemini_client.OPENROUTER_CHAT_COMPLETIONS_URL
            assert kwargs["headers"]["Authorization"] == "Bearer test-key"
            assert kwargs["json"]["model"] == "test/model"
            assert kwargs["json"]["stream"] is False
            return FakeResponse()

    monkeypatch.setattr(gemini_client, "client", FakeGeminiClient())
    monkeypatch.setattr(gemini_client, "MODEL_NAME", "test-gemini")
    monkeypatch.setattr(gemini_client, "FALLBACK_MODEL_NAME", None)
    monkeypatch.setattr(gemini_client, "OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(gemini_client, "OPENROUTER_MODEL", "test/model")
    monkeypatch.setattr(gemini_client.httpx, "AsyncClient", FakeHttpClient)

    result = await gemini_client.select_tool("Show trial balance")

    assert result == {
        "tool_name": "get_trial_balance",
        "arguments": {},
        "error": None,
    }
