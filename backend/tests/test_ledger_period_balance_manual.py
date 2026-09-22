import asyncio
from datetime import date

from app.tally.service import client
from app.tally.parser import parse_ledger_list
from app.tally.xml_builder import format_tally_date


async def main():
    company_name = "ABC Pvt Ltd"
    from_date = date(2025, 4, 1)
    to_date = date(2025, 4, 30)

    request_xml = f"""
    <ENVELOPE>
      <HEADER>
        <VERSION>1</VERSION>
        <TALLYREQUEST>Export</TALLYREQUEST>
        <TYPE>Collection</TYPE>
        <ID>Period Ledger Collection</ID>
      </HEADER>

      <BODY>
        <DESC>

          <STATICVARIABLES>
            <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
            <SVCURRENTCOMPANY>{company_name}</SVCURRENTCOMPANY>
            <SVFROMDATE>{format_tally_date(from_date)}</SVFROMDATE>
            <SVTODATE>{format_tally_date(to_date)}</SVTODATE>
          </STATICVARIABLES>

          <TDL>
            <TDLMESSAGE>

              <COLLECTION NAME="Period Ledger Collection">
                <TYPE>Ledger</TYPE>

                <FETCH>
                  Name,
                  Parent,
                  OpeningBalance,
                  ClosingBalance
                </FETCH>

              </COLLECTION>

            </TDLMESSAGE>
          </TDL>

        </DESC>
      </BODY>
    </ENVELOPE>
    """

    response = await client.send_xml(request_xml)

    ledgers = parse_ledger_list(response)

    apex = [
        ledger
        for ledger in ledgers
        if ledger["name"] == "Apex Office Solutions"
    ]

    print("Period:", from_date, "to", to_date)
    print("Ledger returned by Tally:", apex)


if __name__ == "__main__":
    asyncio.run(main())