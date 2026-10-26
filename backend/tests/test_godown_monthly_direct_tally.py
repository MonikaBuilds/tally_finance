import pytest
from datetime import date
from unittest.mock import AsyncMock, patch

from app.tally.parsers.inventory import (
    parse_item_monthly_summary,
    parse_tally_vouchers_report,
    parse_stock_movement,
)
from app.tally.xml_builders.inventory import (
    build_item_monthly_summary_request,
    build_stock_vouchers_request,
    build_stock_movement_request,
)
from app.tally.service import fetch_godown_item_monthly, fetch_stock_item_monthly


SAMPLE_ITEM_MONTHLY_XML = """<ENVELOPE>
 <DSPPERIOD>April</DSPPERIOD>
 <DSPSTKINFO>
  <DSPSTKIN>
   <DSPINQTY>13 NOS</DSPINQTY>
   <DSPDRAMTA>-1210000.00</DSPDRAMTA>
  </DSPSTKIN>
  <DSPSTKOUT>
   <DSPOUTQTY>1 NOS</DSPOUTQTY>
   <DSPNETTCRAMTA>100000.00</DSPNETTCRAMTA>
  </DSPSTKOUT>
  <DSPSTKCL>
   <DSPCLQTY>27 NOS</DSPCLQTY>
   <DSPCLAMTA>-2613214.29</DSPCLAMTA>
  </DSPSTKCL>
 </DSPSTKINFO>
 <DSPPERIOD>March</DSPPERIOD>
 <DSPSTKINFO>
  <DSPSTKIN>
   <DSPINQTY>40 NOS</DSPINQTY>
   <DSPDRAMTA>-400000.00</DSPDRAMTA>
  </DSPSTKIN>
  <DSPSTKOUT>
   <DSPOUTQTY></DSPOUTQTY>
   <DSPNETTCRAMTA></DSPNETTCRAMTA>
  </DSPSTKOUT>
  <DSPSTKCL>
   <DSPCLQTY>67 NOS</DSPCLQTY>
   <DSPCLAMTA>-3064264.71</DSPCLAMTA>
  </DSPSTKCL>
 </DSPSTKINFO>
</ENVELOPE>"""

SAMPLE_VOUCHERS_XML = """<ENVELOPE>
 <DSPVCHDATE>1-Apr-25</DSPVCHDATE>
 <DSPVCHITEMACCOUNT>SmartMind AI</DSPVCHITEMACCOUNT>
 <DSPVCHTYPE>Stk Jrnl</DSPVCHTYPE>
 <DSPINBLOCK>
  <DSPVCHINQTY></DSPVCHINQTY>
  <DSPVCHINAMT></DSPVCHINAMT>
 </DSPINBLOCK>
 <DSPOUTBLOCK>
  <DSPVCHOUTQTY>1 NOS</DSPVCHOUTQTY>
  <DSPVCHNETTOUTAMT>100000.00</DSPVCHNETTOUTAMT>
 </DSPOUTBLOCK>
 <DSPCLBLOCK>
  <DSPVCHCLQTY></DSPVCHCLQTY>
  <DSPVCHCLAMT></DSPVCHCLAMT>
 </DSPCLBLOCK>
 <DSPVCHDATE>31-Mar-26</DSPVCHDATE>
 <DSPVCHITEMACCOUNT>Apex Office Solutions</DSPVCHITEMACCOUNT>
 <DSPVCHTYPE>Purc</DSPVCHTYPE>
 <DSPINBLOCK>
  <DSPVCHINQTY>20 NOS</DSPVCHINQTY>
  <DSPVCHINAMT>-200000.00</DSPVCHINAMT>
 </DSPINBLOCK>
 <DSPOUTBLOCK>
  <DSPVCHOUTQTY></DSPVCHOUTQTY>
  <DSPVCHNETTOUTAMT></DSPVCHNETTOUTAMT>
 </DSPOUTBLOCK>
 <DSPCLBLOCK>
  <DSPVCHCLQTY>67 NOS</DSPVCHCLQTY>
  <DSPVCHCLAMT>-3064264.71</DSPVCHCLAMT>
 </DSPCLBLOCK>
</ENVELOPE>"""


def test_build_item_monthly_summary_request():
    req = build_item_monthly_summary_request(
        stock_item_name="SmartMind AI-  Old Version",
        godown_name="Main Location",
        company_name="ABC Pvt Ltd",
    )
    assert "<ID>Item Monthly Summary</ID>" in req
    assert "<STOCKITEMNAME>SmartMind AI-  Old Version</STOCKITEMNAME>" in req
    assert "<GODOWNNAME>Main Location</GODOWNNAME>" in req
    assert "<SVCURRENTCOMPANY>ABC Pvt Ltd</SVCURRENTCOMPANY>" in req


def test_build_stock_vouchers_request():
    req = build_stock_vouchers_request(
        stock_item_name="SmartMind AI-  Old Version",
        godown_name="Main Location",
    )
    assert "<ID>Godown Vouchers</ID>" in req
    assert "<STOCKITEMNAME>SmartMind AI-  Old Version</STOCKITEMNAME>" in req
    assert "<GODOWNNAME>Main Location</GODOWNNAME>" in req


def test_parse_item_monthly_summary():
    rows = parse_item_monthly_summary(SAMPLE_ITEM_MONTHLY_XML, start_year=2025)
    assert len(rows) == 2
    april = rows[0]
    assert april["month"] == "2025-04"
    assert april["inward_quantity"] == 13.0
    assert april["inward_value"] == 1210000.0
    assert april["outward_quantity"] == 1.0
    assert april["outward_value"] == 100000.0
    assert april["closing_quantity"] == 27.0
    assert april["closing_value"] == 2613214.29

    march = rows[1]
    assert march["month"] == "2026-03"
    assert march["inward_quantity"] == 40.0
    assert march["inward_value"] == 400000.0
    assert march["closing_quantity"] == 67.0
    assert march["closing_value"] == 3064264.71


def test_parse_tally_vouchers_report():
    rows = parse_tally_vouchers_report(SAMPLE_VOUCHERS_XML)
    assert len(rows) == 2
    v1 = rows[0]
    assert v1["date"] == "2025-04-01"
    assert v1["particulars"] == "SmartMind AI"
    assert v1["voucher_type"] == "Stock Journal"
    assert v1["outward_quantity"] == 1.0
    assert v1["outward_value"] == 100000.0

    v2 = rows[1]
    assert v2["date"] == "2026-03-31"
    assert v2["voucher_type"] == "Purchase"
    assert v2["inward_quantity"] == 20.0
    assert v2["closing_quantity"] == 67.0
    assert v2["closing_value"] == 3064264.71


@pytest.mark.asyncio
async def test_fetch_godown_item_monthly_direct_tally():
    with patch("app.tally.service.client.send_xml", new_callable=AsyncMock) as mock_send:
        mock_send.return_value = SAMPLE_ITEM_MONTHLY_XML

        with patch("app.tally.service._load_item_master", new_callable=AsyncMock) as mock_master:
            mock_master.return_value = {
                "name": "SmartMind AI-  Old Version",
                "base_units": "NOS",
                "opening_quantity": 15.0,
                "opening_value": 1500000.0,
                "closing_quantity": 67.0,
                "closing_value": 3064264.71,
            }

            result = await fetch_godown_item_monthly(
                godown_name="Main Location",
                stock_item_name="SmartMind AI-  Old Version",
                from_date=date(2025, 4, 1),
                to_date=date(2026, 3, 31),
            )

            assert result["godown"] == "Main Location"
            assert result["approximate"] is False
            assert result["unit"] == "NOS"
            assert len(result["rows"]) == 2
            assert result["rows"][0]["closing_quantity"] == 27.0
            assert result["rows"][1]["closing_quantity"] == 67.0
