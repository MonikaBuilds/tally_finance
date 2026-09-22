import asyncio
from datetime import date
from xml.sax.saxutils import escape

from app.tally.client import TallyClient
from app.tally.xml_builder import format_tally_date

# This script is a manual test to fetch ledger vouchers from Tally for a specific ledger and date range
async def main():
    company_name = "ABC Pvt Ltd"
    ledger_name = "Apex Office Solutions"
    from_date = date(2025, 4, 1)
    to_date = date(2025, 4, 30)

    request = f"""
    <ENVELOPE>
        <HEADER>
            <VERSION>1</VERSION>
            <TALLYREQUEST>Export</TALLYREQUEST>
            <TYPE>Data</TYPE>
            <ID>Ledger Vouchers</ID>
        </HEADER>

        <BODY>
            <DESC>
                <STATICVARIABLES>
                    <SVCURRENTCOMPANY>{escape(company_name)}</SVCURRENTCOMPANY>
                    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                    <SVFROMDATE>{format_tally_date(from_date)}</SVFROMDATE>
                    <SVTODATE>{format_tally_date(to_date)}</SVTODATE>
                    <LEDGERNAME>{escape(ledger_name)}</LEDGERNAME>
                </STATICVARIABLES>
            </DESC>
        </BODY>
    </ENVELOPE>
    """

    client = TallyClient()
    response = await client.send_xml(request)

    with open(
        "tally_native_ledger_vouchers_raw.xml",
        "w",
        encoding="utf-8",
    ) as file:
        file.write(response)

    print("Response saved:", len(response), "characters")
    print(response[:1000])


if __name__ == "__main__":
    asyncio.run(main())