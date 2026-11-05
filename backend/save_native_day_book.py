import asyncio
from datetime import date

from app.tally.client import TallyClient
from app.tally.parsers.common import parse_xml
from app.tally.xml_builders.ledger import build_native_day_book_request

# Saves Tally's own Day Book response for ONE day (1-Apr-2025) and prints
# what is in it. Run from the backend folder:  python save_native_day_book.py
COMPANY = "ABC Pvt Ltd"
DAY = date(2025, 4, 1)


async def main():
    request = build_native_day_book_request(COMPANY, DAY, DAY)
    response = await TallyClient().send_xml(request)

    with open("tally_native_day_book_raw.xml", "w", encoding="utf-8") as f:
        f.write(response)
    print("Saved tally_native_day_book_raw.xml,", len(response), "characters\n")

    root = parse_xml(response)
    vouchers = list(root.iter("VOUCHER"))
    print("VOUCHER elements:", len(vouchers))
    for v in vouchers:
        g = lambda t: (v.findtext(t) or "").strip()
        print(
            " attrs=", dict(v.attrib),
            "| DATE=", g("DATE"),
            "| TYPE=", g("VOUCHERTYPENAME"),
            "| NO=", g("VOUCHERNUMBER"),
            "| PARTY=", g("PARTYLEDGERNAME"),
            "| GUID=", g("GUID")[-12:],
        )
    if vouchers:
        print("\nTags directly inside the first VOUCHER:")
        print(sorted({c.tag for c in vouchers[0]}))


asyncio.run(main())