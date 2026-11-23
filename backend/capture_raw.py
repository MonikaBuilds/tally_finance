"""
One-off capture of raw Tally responses, used to settle three parser
questions that cannot be answered from the code alone:

  * whether the Balance Sheet sends liabilities as positive or negative
    (decides BS_CREDIT_IS_POSITIVE in parsers/financial.py)
  * whether the Trial Balance really sends contra balances as "(-)..."
    (decides preserve_sign in _parse_dspacc_rows)
  * how far the bill amount node sits from BILLFIXED
    (decides the five-sibling scan in parse_outstanding_report)

Run from the backend folder, with Tally open and its XML server on:

    .\\venv\\Scripts\\python.exe capture_raw.py

The files it writes are ignored by .gitignore (backend/*_raw.xml).
Change COMPANY below if your loaded Tally company has another name.
"""

import asyncio
from datetime import date

from app.tally.client import TallyClient
from app.tally.xml_builders.financial import (
    build_balance_sheet_request,
    build_bills_receivable_request,
    build_trial_balance_request,
)

COMPANY = "ABC Pvt Ltd"
AS_ON = date.today()


async def capture(client, filename, request):
    try:
        response = await client.send_xml(request)
    except Exception as exc:
        print(f"{filename}: FAILED ({type(exc).__name__}: {exc})")
        return False

    with open(filename, "w", encoding="utf-8") as handle:
        handle.write(response)

    print(f"{filename}: {len(response)} characters")
    return True


async def main():
    client = TallyClient()

    jobs = [
        (
            "bills_receivable_raw.xml",
            build_bills_receivable_request(company_name=COMPANY),
        ),
        (
            "balance_sheet_raw.xml",
            build_balance_sheet_request(
                company_name=COMPANY,
                to_date=AS_ON,
            ),
        ),
        (
            "trial_balance_raw.xml",
            build_trial_balance_request(
                company_name=COMPANY,
                to_date=AS_ON,
            ),
        ),
    ]

    captured = 0
    for filename, request in jobs:
        if await capture(client, filename, request):
            captured += 1

    print()
    print(f"{captured} of {len(jobs)} captured.")
    if captured < len(jobs):
        print("Check that Tally is open, the company is loaded, and")
        print("F1 > Settings > Connectivity > Client/Server is on port 9000.")


if __name__ == "__main__":
    asyncio.run(main())
