"""
Run this from inside backend/, with your venv active, e.g.:

    cd backend
    python inspect_material_in.py

It fetches the same raw XML your app's /reports/ledger endpoint uses,
then prints only the Material In voucher block so you can see its
ledger entries directly, without opening TallyPrime.
"""

import asyncio
import re

from app.tally.client import TallyClient
from app.tally.xml_builder import build_ledger_report_request


async def main():
    client = TallyClient()

    xml_response = await client.send_xml(
        build_ledger_report_request(
            ledger_name="Apex Office Solutions",
            company_name=None,
            from_date=None,
            to_date=None
        )
    )

    vouchers = re.findall(
        r"<VOUCHER[^>]*>.*?</VOUCHER>",
        xml_response,
        flags=re.DOTALL
    )

    found = False
    for voucher in vouchers:
        if "Material In" in voucher:
            found = True
            print("FOUND MATERIAL IN VOUCHER:\n")
            print(voucher)
            print("\n\nLEDGER ENTRY LINES:\n")
            for entry in re.findall(
                r"<(?:ALL)?LEDGERENTRIES\.LIST>.*?</(?:ALL)?LEDGERENTRIES\.LIST>",
                voucher,
                flags=re.DOTALL
            ):
                print(entry)
                print("---")

    if not found:
        print("No voucher containing 'Material In' was found in the raw response.")
        print("Total vouchers returned:", len(vouchers))


if __name__ == "__main__":
    asyncio.run(main())