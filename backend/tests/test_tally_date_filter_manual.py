import asyncio
from datetime import date
from urllib import response

from app.tally.service import client
from app.tally.parser import parse_xml
from app.tally.xml_builder import (
    build_company_variable,
    format_tally_date,
)


async def main():
    company_name = "ABC Pvt Ltd"
    from_date = date(2025, 4, 1)
    to_date = date(2025, 4, 30)

    company_xml = build_company_variable(company_name)
    from_value = format_tally_date(from_date)
    to_value = format_tally_date(to_date)

    request_xml = f"""
    <ENVELOPE>
        <HEADER>
            <VERSION>1</VERSION>
            <TALLYREQUEST>Export</TALLYREQUEST>
            <TYPE>Collection</TYPE>
            <ID>Test Voucher Date Collection</ID>
        </HEADER>

        <BODY>
            <DESC>

                <STATICVARIABLES>
                    <SVEXPORTFORMAT>$$SysName:XML</SVEXPORTFORMAT>
                    {company_xml}
                    <SVFROMDATE>{from_value}</SVFROMDATE>
                    <SVTODATE>{to_value}</SVTODATE>
                </STATICVARIABLES>

                <TDL>
                    <TDLMESSAGE>

                        <COLLECTION NAME="Test Voucher Date Collection">
                            <TYPE>Voucher</TYPE>

                            <FETCH>
                                DATE,
                                VOUCHERTYPENAME,
                                VOUCHERNUMBER,
                                PARTYLEDGERNAME
                            </FETCH>

                            <FILTER>TestVoucherDateFilter</FILTER>
                            </COLLECTION>

                            <SYSTEM TYPE="Formulae"
                                    NAME="TestVoucherDateFilter">
                                $Date &gt;= $$SystemPeriodFrom
                                AND
                                $Date &lt;= $$SystemPeriodTo
                            </SYSTEM>

                    </TDLMESSAGE>
                </TDL>

            </DESC>
        </BODY>
    </ENVELOPE>
    """

    response = await client.send_xml(request_xml)

    root = parse_xml(response)

    vouchers = root.findall(".//VOUCHER")

    dates = sorted(
        {
            (voucher.findtext("DATE") or "").strip()
            for voucher in vouchers
            if (voucher.findtext("DATE") or "").strip()
        }
    )

    print("Voucher count:", len(vouchers))
    print("Dates returned directly by Tally:", dates)
    print("\nRAW TALLY RESPONSE:")
    print(response)

asyncio.run(main())