from collections import OrderedDict
from datetime import date

from app.tally.parsers.common import (
    parse_xml,

    _text,
    _first_text,
    format_tally_date,
)
from app.tally.parsers.inventory_registers import (
    _quantity_and_unit,
    _is_yes,
)
from app.tally.parsers.inventory_summary import normalize_master_name
from app.tally.parsers.ledger import (
    _inventory_entry_nodes,
    _ledger_entry_nodes,
    _parse_signed_tally_amount,
    _same_ledger_name,
    _voucher_base_type,
)

# Tally's own wording when a voucher has several particulars.
AS_PER_DETAILS = "(as per details)"


def _ledger_entries(voucher):
    entries = []

    for node in _ledger_entry_nodes(voucher):
        name = _first_text(node, "LEDGERNAME", "LEDGER")

        if not name:
            continue

        debit, credit = _parse_signed_tally_amount(
            _first_text(node, "AMOUNT"),
            _first_text(node, "ISDEEMEDPOSITIVE"),
        )

        entries.append(
            {
                "ledger_name": name,
                "debit": debit,
                "credit": credit,
                "side": "Dr" if debit else "Cr",
            }
        )

    return entries


def _stock_entries(voucher):
    """Stock lines: (item, quantity, unit, inward?)."""
    entries = []

    # Tally exports the same stock lines under alternate tag names
    # (ALLINVENTORYENTRIES / INVENTORYENTRIESIN / ...OUT); count them once.
    nodes = voucher.findall("./ALLINVENTORYENTRIES.LIST")
    if not nodes:
        nodes = voucher.findall("./INVENTORYENTRIES.LIST")
    if not nodes:
        nodes = (
            voucher.findall("./INVENTORYENTRIESIN.LIST")
            + voucher.findall("./INVENTORYENTRIESOUT.LIST")
        )
    if not nodes:
        nodes = _inventory_entry_nodes(voucher)

    for node in nodes:
        item = _first_text(node, "STOCKITEMNAME", "STOCKITEM")

        if not item:
            continue

        quantity, unit = _quantity_and_unit(
            _text(node, "ACTUALQTY") or _text(node, "BILLEDQTY")
        )

        deemed = _text(node, "ISDEEMEDPOSITIVE").strip().casefold()

        entries.append(
            {
                "item": item,
                "quantity": quantity,
                "unit": unit,
                # Yes = stock comes in, No = stock goes out.
                "inward": None if deemed not in ("yes", "no") else deemed == "yes",
            }
        )

    return entries


def _detail_lines(ledger_entries, stock_entries):
    """
    The voucher's own lines, for the Detailed view (Tally's Alt+F5):
    every ledger leg with its Dr / Cr amount, every stock line with its
    quantity and direction.
    """
    lines = []

    for e in ledger_entries:
        lines.append(
            {
                "kind": "ledger",
                "name": e["ledger_name"],
                "debit": e["debit"],
                "credit": e["credit"],
            }
        )

    for e in stock_entries:
        qty = f"{e['quantity']:g} {e['unit']}".strip() if e["quantity"] else ""
        lines.append(
            {
                "kind": "stock",
                "name": e["item"],
                "quantity": qty,
                "inward": e["inward"],
            }
        )

    return lines


def _quantity_text(stock_entries, inward, signed=False):
    """'20 NOS' / '5 Kgs, 3 NOS' for one direction; '' when none."""
    totals = OrderedDict()

    for entry in stock_entries:
        if entry["inward"] is not inward:
            continue

        totals[entry["unit"]] = totals.get(entry["unit"], 0.0) + entry["quantity"]

    parts = []

    for unit, quantity in totals.items():
        number = f"{quantity:g}"
        text = f"{number} {unit}".strip()
        parts.append(f"(-){text}" if signed else text)

    return ", ".join(parts)


def _stock_columns(stock_entries, voucher_type):
    """
    (Inwards, Outwards) text as Tally's Day Book shows them. A rejection
    reverses a movement, so it lands in the opposite column as a
    negative quantity (Rejections Out: (-)5 under Inwards). A voucher
    moving stock both ways (Stock Journal) lists what came in.
    """
    if "rejection" in str(voucher_type or "").casefold():
        return (
            _quantity_text(stock_entries, False, signed=True),
            _quantity_text(stock_entries, True, signed=True),
        )

    inwards = _quantity_text(stock_entries, True)
    outwards = _quantity_text(stock_entries, False)

    if inwards and outwards:
        outwards = ""

    return inwards, outwards


def _particulars_from_entries(entries, base_type, party_name):
    """
    (particulars text, drill ledger name, debit, credit) for a voucher
    that has ledger entries.
    """

    if not entries:
        return "", "", 0.0, 0.0

    chosen = []

    if base_type in {"sales", "purchase", "credit_note", "debit_note", "other"}:
        chosen = [
            e for e in entries
            if party_name and _same_ledger_name(e["ledger_name"], party_name)
        ][:1]

        if not chosen and base_type == "other":
            # Orders: only the party line is listed, never the ledger
            # (e.g. Software) the order would post to.
            chosen = entries[:1]

        if not chosen:
            # No party recorded: the party is the largest line on the
            # side Tally books it (Dr for sales / debit note, else Cr).
            side = "Dr" if base_type in {"sales", "debit_note"} else "Cr"
            on_side = [e for e in entries if e["side"] == side]
            if on_side:
                chosen = [max(on_side, key=lambda e: e["debit"] or e["credit"])]

    else:
        # Payment shows what was paid TO (Dr lines); Receipt and Contra
        # show the credited lines; Journal and the rest the Dr lines.
        side = "Cr" if base_type in {"receipt", "contra"} else "Dr"
        chosen = [e for e in entries if e["side"] == side]

    if not chosen:
        chosen = entries[:1]

    debit = round(sum(e["debit"] for e in chosen), 2)
    credit = round(sum(e["credit"] for e in chosen), 2)

    if len(chosen) > 1:
        return AS_PER_DETAILS, chosen[0]["ledger_name"], debit, credit

    return chosen[0]["ledger_name"], chosen[0]["ledger_name"], debit, credit


def parse_day_book(xml_text: str) -> list[dict]:
    """One dict per voucher, in the order Tally sent them."""
    root = parse_xml(xml_text)

    rows = []
    seen = set()

    # A collection wraps each voucher once; nested VOUCHER elements
    # (e.g. inside a bill allocation) are not vouchers of their own.
    vouchers = [v for v in root.iter("VOUCHER") if v.get("VCHTYPE")]
    if not vouchers:
        vouchers = root.findall(".//VOUCHER")

    for voucher in vouchers:
        if _is_yes(_text(voucher, "ISDELETED")):
            continue

        voucher_date = format_tally_date(_text(voucher, "DATE"))
        voucher_type = _text(voucher, "VOUCHERTYPENAME")
        voucher_number = _text(voucher, "VOUCHERNUMBER")
        guid = _text(voucher, "GUID")

        key = (guid, voucher_date, voucher_type, voucher_number)

        if key in seen:
            continue

        seen.add(key)

        base_type = _voucher_base_type(voucher_type)

        party_name = normalize_master_name(
            _first_text(voucher, "PARTYLEDGERNAME", "PARTYNAME")
        )

        ledger_entries = _ledger_entries(voucher)
        stock_entries = _stock_entries(voucher)

        has_quantity = any(e["quantity"] for e in stock_entries)

        if base_type == "other" and stock_entries and has_quantity:
            # Stock voucher (Delivery / Receipt Note, Material In / Out,
            # Rejections, Stock Journal, Physical Stock): the stock item
            # is the particular and the quantity moves in the Inwards /
            # Outwards columns. No amount is posted.
            items = list(OrderedDict.fromkeys(e["item"] for e in stock_entries))
            particulars = items[0] if len(items) == 1 else AS_PER_DETAILS
            drill_ledger = ""
            debit = credit = 0.0
            drill = "inventory"
            inwards, outwards = _stock_columns(stock_entries, voucher_type)

        elif ledger_entries:
            particulars, drill_ledger, debit, credit = _particulars_from_entries(
                ledger_entries, base_type, party_name
            )
            drill = "accounting"
            inwards = ""
            outwards = ""

        elif stock_entries:
            items = list(OrderedDict.fromkeys(e["item"] for e in stock_entries))
            particulars = party_name or (items[0] if len(items) == 1 else AS_PER_DETAILS)
            drill_ledger = ""
            debit = credit = 0.0
            drill = "inventory"
            inwards, outwards = _stock_columns(stock_entries, voucher_type)

        else:
            particulars = party_name or ""
            drill_ledger = party_name or ""
            debit = credit = 0.0
            drill = "accounting"
            inwards = outwards = ""

        is_cancelled = _is_yes(_text(voucher, "ISCANCELLED"))

        if is_cancelled:
            # A cancelled voucher stays in the Day Book but carries no
            # amount or quantity, as in Tally.
            debit = credit = 0.0
            inwards = outwards = ""

        rows.append(
            {
                "date": voucher_date,
                "guid": guid,
                "voucher_type": voucher_type,
                "voucher_number": voucher_number,
                "particulars": particulars,
                "ledger_name": drill_ledger,
                "debit": debit,
                "credit": credit,
                "inwards_qty": inwards,
                "outwards_qty": outwards,
                "narration": _text(voucher, "NARRATION"),
                "reference": _text(voucher, "REFERENCE"),
                "is_cancelled": is_cancelled,
                "is_optional": _is_yes(_text(voucher, "ISOPTIONAL")),
                "is_postdated": _is_yes(_text(voucher, "ISPOSTDATED")),
                "has_ledger": bool(ledger_entries),
                "has_stock": bool(stock_entries),
                "lines": [] if is_cancelled else _detail_lines(ledger_entries, stock_entries),
                # Which existing voucher page opens this row.
                "drill": drill,
            }
        )

    return rows


def parse_voucher_type_ranks(xml_text: str) -> dict:
    """
    {voucher type name (casefolded): position}, from Tally's own list of
    voucher types. Tally's Day Book lists each day's vouchers by this
    position (Payment, Receipt, ... Sales, Purchase, Delivery Note ...),
    then by voucher number.
    """
    try:
        root = parse_xml(xml_text)
    except Exception:
        return {}

    ranks = {}

    for node in root.iter("VOUCHERTYPE"):
        name = (node.get("NAME") or _text(node, "NAME")).strip()
        master = _text(node, "MASTERID").strip()

        if name and master.isdigit():
            ranks[name.casefold()] = int(master)

    return ranks


def _number_key(number: str):
    text = str(number or "").strip()
    digits = "".join(ch for ch in text if ch.isdigit())
    return (0, int(digits), text) if digits else (1, 0, text.casefold())


def apply_type_order(vouchers: list[dict], ranks: dict) -> list[dict]:
    """
    Order the Day Book as Tally does: by date, then by the voucher type's
    position in Tally's voucher-type list, then by voucher number. The
    collection's own order breaks any remaining tie. Without ranks the
    vouchers are returned as they came.
    """
    if not ranks:
        return vouchers

    last = max(ranks.values()) + 1

    indexed = list(enumerate(vouchers))
    indexed.sort(
        key=lambda t: (
            t[1].get("date") or "",
            ranks.get((t[1].get("voucher_type") or "").strip().casefold(), last),
            _number_key(t[1].get("voucher_number")),
            t[0],
        )
    )

    return [v for _, v in indexed]


def build_day_book(vouchers: list[dict]) -> dict:
    """
    Every voucher of the period, oldest day first (the order within a day
    stays the order Tally sent). This is the unfiltered, cacheable data;
    `filter_day_book` applies the view the user asked for.
    """
    ordered = sorted(vouchers, key=lambda v: v.get("date") or "")

    return {"rows": ordered, "count": len(ordered)}


# Tally's Day Book views: the regular list, plus the exception lists
# (Ctrl+J) for optional, cancelled and post-dated vouchers.
VIEWS = ("regular", "optional", "cancelled", "postdated", "all")

# Tally's "Basis of Values > Type of Voucher Entries" (Ctrl+B).
BASES = ("all", "accounting", "inventory")


def _in_view(row: dict, view: str) -> bool:
    if view == "all":
        return True
    if view == "optional":
        return bool(row.get("is_optional"))
    if view == "cancelled":
        return bool(row.get("is_cancelled"))
    if view == "postdated":
        return bool(row.get("is_postdated"))
    # Regular: optional vouchers are not real postings, so Tally keeps
    # them in their own exception list.
    return not row.get("is_optional")


def _in_basis(row: dict, basis: str) -> bool:
    if basis == "accounting":
        return bool(row.get("has_ledger"))
    if basis == "inventory":
        return bool(row.get("has_stock"))
    return True


def _matches_search(row: dict, needle: str) -> bool:
    haystack = [
        row.get("particulars"),
        row.get("voucher_type"),
        row.get("voucher_number"),
        row.get("narration"),
        row.get("reference"),
    ]
    haystack += [line.get("name") for line in row.get("lines", [])]

    return any(needle in str(text or "").casefold() for text in haystack)


def filter_day_book(
    data: dict,
    voucher_type: str | None = None,
    view: str = "regular",
    basis: str = "all",
    search: str | None = None,
) -> dict:
    """
    The Day Book as Tally shows it for the chosen view, voucher type
    (F4), basis (Ctrl+B) and search (Ctrl+F), with its Grand Total.
    Cancelled vouchers carry no amount, so they add nothing to the total.
    """
    rows = data.get("rows", [])

    # Exception counts always describe the whole period, so the page can
    # tell the user which exception lists have something in them.
    exceptions = {
        "optional": sum(1 for r in rows if r.get("is_optional")),
        "cancelled": sum(1 for r in rows if r.get("is_cancelled")),
        "postdated": sum(1 for r in rows if r.get("is_postdated")),
    }

    scoped = [r for r in rows if _in_view(r, view) and _in_basis(r, basis)]

    # The voucher-type list (F4) offers the types present in this view.
    type_counts = OrderedDict()
    for r in scoped:
        name = r.get("voucher_type") or ""
        type_counts[name] = type_counts.get(name, 0) + 1

    voucher_types = [
        {"name": name, "count": count}
        for name, count in sorted(type_counts.items(), key=lambda kv: kv[0].casefold())
    ]

    shown = scoped

    if voucher_type:
        wanted = voucher_type.strip().casefold()
        shown = [r for r in shown if (r.get("voucher_type") or "").strip().casefold() == wanted]

    needle = (search or "").strip().casefold()
    if needle:
        shown = [r for r in shown if _matches_search(r, needle)]

    counted = [r for r in shown if not r.get("is_cancelled")]

    return {
        "rows": shown,
        "count": len(shown),
        "total_debit": round(sum(r["debit"] for r in counted), 2),
        "total_credit": round(sum(r["credit"] for r in counted), 2),
        "voucher_types": voucher_types,
        "exceptions": exceptions,
    }


def pick_default_day(
    today: date,
    fy_start: date | None = None,
    fy_end: date | None = None,
    latest_voucher: date | None = None,
) -> date:
    """
    The one day the Day Book opens on, as in Tally: the current date,
    held inside the company's financial year (Tally shows the last day
    of the books when the system date is past them). When Tally does not
    give the financial year, the last day that has vouchers stands in
    for the end of the books.
    """
    if fy_start and fy_end:
        return min(max(today, fy_start), fy_end)

    if latest_voucher and today > latest_voucher:
        return latest_voucher

    return today
