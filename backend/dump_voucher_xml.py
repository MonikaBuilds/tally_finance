"""
Print the raw XML Tally returns for one inventory voucher - the exact
request the Inventory Voucher page makes.

Run from the backend folder:

    python dump_voucher_xml.py "Rejections Out" 1 2025-04-01

(voucher type, voucher number, voucher date as YYYY-MM-DD)
"""

import asyncio
import sys
from datetime import date

from app.tally.service import client
from app.tally.xml_builders.inventory import build_inventory_voucher_detail_request


async def main(voucher_type: str, voucher_number: str, voucher_date: str | None):
    request = build_inventory_voucher_detail_request(
        voucher_type,
        voucher_number,
        date.fromisoformat(voucher_date) if voucher_date else None,
    )
    print(await client.send_xml(request))


if __name__ == "__main__":
    if len(sys.argv) < 3:
        sys.exit(__doc__)

    asyncio.run(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else None))
