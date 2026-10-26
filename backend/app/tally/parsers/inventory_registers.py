"""
Inventory Books registers: Sales / Purchase Orders Book, Delivery Note,
Receipt Note, Rejections In / Out, Stock Journal, Physical Stock,
Material Out / In.

Tally's flow for each register is
    Register (one row per month, voucher counts)
      -> List of All <X> Vouchers (one row per voucher in the month)
      -> Voucher Alteration screen.
This module turns raw voucher XML into the first two levels. Every name,
date, quantity and amount comes from the Tally response.
"""

import calendar
import re
from datetime import date

from app.tally.parsers.common import (
    parse_xml,
    to_float,
    _text,
    _first_text,
    format_tally_date,
)
from app.tally.parsers.ledger import _inventory_entry_nodes
from app.tally.parsers.inventory_summary import normalize_master_name

MONTH_NAMES = [
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
]

# Registers whose voucher list is headed by the stock item (Tally shows
# the item name under Particulars) instead of the party.
ITEM_PARTICULARS = {"stock-journal", "physical-stock", "material-out", "material-in"}

# Order books show Order Ref No / Order Amount instead of quantities.
ORDER_REGISTERS = {"sales-orders", "purchase-orders"}


def _quantity_and_unit(text: str) -> tuple[float, str]:
    """' 15 NOS' -> (15.0, 'NOS'); '12.5 Kgs' -> (12.5, 'Kgs')."""
    text = (text or "").strip()

    match = re.match(r"^\s*([-+]?[\d,]*\.?\d+)\s*(.*)$", text)

    if not match:
        return 0.0, ""

    return abs(to_float(match.group(1))), match.group(2).strip()


def _is_yes(value: str) -> bool:
    return (value or "").strip().casefold() == "yes"


def parse_register_vouchers(xml_text: str) -> list[dict]:
    """One dict per voucher (not per stock entry), in response order."""
    root = parse_xml(xml_text)

    vouchers = []
    seen = set()

    for node in root.findall(".//VOUCHER"):
        voucher_date = format_tally_date(_text(node, "DATE"))
        voucher_type = _text(node, "VOUCHERTYPENAME")
        voucher_number = _text(node, "VOUCHERNUMBER")
        guid = _text(node, "GUID")

        key = (guid, voucher_date, voucher_type, voucher_number)

        if key in seen:
            continue

        seen.add(key)

        entries = []

        for entry in _inventory_entry_nodes(node):
            item = _first_text(entry, "STOCKITEMNAME", "STOCKITEM")

            if not item:
                continue

            quantity, unit = _quantity_and_unit(
                _text(entry, "ACTUALQTY") or _text(entry, "BILLEDQTY")
            )

            deemed = _text(entry, "ISDEEMEDPOSITIVE").strip().casefold()

            entries.append(
                {
                    "stock_item": item,
                    "quantity": quantity,
                    "unit": unit,
                    "amount": abs(to_float(_text(entry, "AMOUNT"))),
                    # Yes = stock comes in, No = stock goes out.
                    "inward": None if deemed not in ("yes", "no") else deemed == "yes",
                }
            )

        vouchers.append(
            {
                "date": voucher_date,
                "guid": guid,
                "voucher_type": voucher_type,
                "voucher_number": voucher_number,
                "reference": _text(node, "REFERENCE"),
                "party": normalize_master_name(
                    _first_text(node, "PARTYLEDGERNAME", "PARTYNAME")
                ),
                "narration": _text(node, "NARRATION"),
                "is_cancelled": _is_yes(_text(node, "ISCANCELLED")),
                "is_optional": _is_yes(_text(node, "ISOPTIONAL")),
                "entries": entries,
            }
        )

    return vouchers


def clip_vouchers(vouchers: list[dict], from_date: date | None, to_date: date | None):
    """Tally returns whole collections, so the period is applied here."""
    result = vouchers

    if from_date:
        result = [v for v in result if (v["date"] or "") >= from_date.isoformat()]

    if to_date:
        result = [v for v in result if (v["date"] or "") <= to_date.isoformat()]

    return result


def build_register_months(vouchers: list[dict], from_date: date, to_date: date) -> dict:
    """
    Register screen: every month of the period with its voucher count
    and how many of those are cancelled (Tally's "Total Vouchers
    (cancelled)"), plus the grand totals.
    """
    rows = []
    year, month = from_date.year, from_date.month

    while (year, month) <= (to_date.year, to_date.month):
        first = date(year, month, 1)
        last = date(year, month, calendar.monthrange(year, month)[1])
        prefix = f"{year:04d}-{month:02d}"

        in_month = [v for v in vouchers if (v["date"] or "").startswith(prefix)]

        rows.append(
            {
                "month": MONTH_NAMES[month - 1],
                "month_key": prefix,
                "from": max(first, from_date).isoformat(),
                "to": min(last, to_date).isoformat(),
                "total_vouchers": len(in_month),
                "cancelled_vouchers": sum(1 for v in in_month if v["is_cancelled"]),
            }
        )

        month += 1

        if month == 13:
            year, month = year + 1, 1

    return {
        "rows": rows,
        "grand_total": sum(r["total_vouchers"] for r in rows),
        "grand_total_cancelled": sum(r["cancelled_vouchers"] for r in rows),
    }


def build_voucher_register(register_key: str, vouchers: list[dict]) -> dict:
    """
    "List of All <X> Vouchers": one row per voucher, oldest first.

    Order books carry Order Ref No and Order Amount; every other
    register carries Inwards / Outwards quantity. Particulars is the
    stock item for Material In/Out, Stock Journal and Physical Stock,
    and the party for the rest.
    """
    is_order = register_key in ORDER_REGISTERS
    rows = []

    for v in sorted(vouchers, key=lambda x: (x["date"] or "", x["voucher_number"])):
        entries = v["entries"]
        items = list(dict.fromkeys(e["stock_item"] for e in entries))

        if register_key in ITEM_PARTICULARS and items:
            particulars = ", ".join(items)
        else:
            particulars = v["party"] or ", ".join(items)

        units = {e["unit"] for e in entries if e["unit"]}
        unit = next(iter(units)) if len(units) == 1 else ""

        def side(inward: bool) -> float:
            return sum(
                e["quantity"]
                for e in entries
                if (e["inward"] if e["inward"] is not None else False) == inward
            )

        row = {
            "date": v["date"],
            "particulars": particulars,
            "voucher_type": v["voucher_type"],
            "voucher_number": v["voucher_number"],
            "is_cancelled": v["is_cancelled"],
            "is_optional": v["is_optional"],
        }

        if is_order:
            row["order_ref_no"] = v["reference"]
            row["order_amount"] = sum(e["amount"] for e in entries)
        else:
            row["inward_quantity"] = side(True)
            row["outward_quantity"] = side(False)
            row["unit"] = unit

        rows.append(row)

    totals = (
        {"order_amount": sum(r["order_amount"] for r in rows)}
        if is_order
        else {
            "inward_quantity": sum(r["inward_quantity"] for r in rows),
            "outward_quantity": sum(r["outward_quantity"] for r in rows),
        }
    )

    return {"kind": "order" if is_order else "movement", "rows": rows, "totals": totals}
