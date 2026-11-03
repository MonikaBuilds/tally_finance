from collections import OrderedDict

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

    for node in _inventory_entry_nodes(voucher):
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


def _quantity_text(stock_entries, inward):
    """'20 NOS' / '5 Kgs, 3 NOS' for one direction; '' when none."""
    totals = OrderedDict()

    for entry in stock_entries:
        if entry["inward"] is not inward:
            continue

        totals[entry["unit"]] = totals.get(entry["unit"], 0.0) + entry["quantity"]

    parts = []

    for unit, quantity in totals.items():
        number = f"{quantity:g}"
        parts.append(f"{number} {unit}".strip())

    return ", ".join(parts)


def _particulars_from_entries(entries, base_type, party_name):
    """
    (particulars text, drill ledger name, debit, credit) for a voucher
    that has ledger entries.
    """

    if not entries:
        return "", "", 0.0, 0.0

    chosen = []

    if base_type in {"sales", "purchase", "credit_note", "debit_note"}:
        chosen = [
            e for e in entries
            if party_name and _same_ledger_name(e["ledger_name"], party_name)
        ][:1]

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

    for voucher in root.findall(".//VOUCHER"):
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

        if ledger_entries:
            particulars, drill_ledger, debit, credit = _particulars_from_entries(
                ledger_entries, base_type, party_name
            )
            drill = "accounting"
            inwards = ""
            outwards = ""

        elif stock_entries:
            # Stock-only voucher: the stock item is the particular and
            # the quantity moves in the Inwards / Outwards columns.
            items = list(OrderedDict.fromkeys(e["item"] for e in stock_entries))
            particulars = items[0] if len(items) == 1 else AS_PER_DETAILS
            drill_ledger = ""
            debit = credit = 0.0
            drill = "inventory"
            inwards = _quantity_text(stock_entries, True)
            outwards = _quantity_text(stock_entries, False)

        else:
            particulars = party_name or ""
            drill_ledger = party_name or ""
            debit = credit = 0.0
            drill = "accounting"
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
                "is_cancelled": _is_yes(_text(voucher, "ISCANCELLED")),
                "is_optional": _is_yes(_text(voucher, "ISOPTIONAL")),
                # Which existing voucher page opens this row.
                "drill": drill,
            }
        )

    return rows


def build_day_book(vouchers: list[dict]) -> dict:
    """
    Day Book report: vouchers oldest day first (the order within a day
    stays the order Tally sent) plus the Grand Total of the Debit /
    Credit columns. Cancelled vouchers carry no amount in Tally.
    """
    ordered = sorted(vouchers, key=lambda v: v.get("date") or "")

    counted = [v for v in ordered if not v["is_cancelled"]]

    return {
        "rows": ordered,
        "count": len(ordered),
        "total_debit": round(sum(v["debit"] for v in counted), 2),
        "total_credit": round(sum(v["credit"] for v in counted), 2),
    }
