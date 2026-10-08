"""
Inventory parsers for Tally XML responses.

This module contains parsing logic related to:
- Stock item list
- Stock summary
- Stock groups
- Stock categories
- Godowns
- Stock movement
- Inventory register
- Inventory register summary
- Stock valuation
- Negative stock

The purpose of this module is to keep inventory-related parsing
separate from financial and ledger parsing.

Important:
This refactor preserves the behaviour of the original parser.py.
We are only organizing the code into smaller modules at this stage.
"""

import re

from app.tally.parsers.common import (
    parse_xml,
    to_float,
    _text,
    _first_text,
    format_tally_date,
)

from app.tally.parsers.inventory_summary import (
    normalize_master_name,
    resolve_godown,
)

# Inventory transactions are stored inside voucher XML.
# The existing ledger module already contains the helper that safely
# finds ALLINVENTORYENTRIES.LIST / INVENTORYENTRIES.LIST nodes.
from app.tally.parsers.ledger import _inventory_entry_nodes


# ============================================================
# STOCK ITEM LIST
# ============================================================

def parse_stock_item_list(xml_text: str) -> list[dict]:
    """
    Parse stock-item master information returned by Tally.

    Values such as quantities, rates and stock values are kept as
    text in this function, matching the behaviour of the old parser.
    """

    root = parse_xml(xml_text)

    stock_items = []

    # Every inventory master item is normally returned inside
    # a STOCKITEM element.
    for item in root.findall(".//STOCKITEM"):

        # Depending on the Tally response, NAME can be an XML
        # attribute or a child element.
        name = (
            item.get("NAME")
            or item.findtext("NAME")
            or ""
        ).strip()

        if not name:
            continue

        parent = (
            item.findtext("PARENT")
            or ""
        ).strip()

        # Units can appear as BASEUNITS or BASEUNIT depending on
        # the response being parsed.
        base_unit = (
            item.findtext("BASEUNITS")
            or item.findtext("BASEUNIT")
            or ""
        ).strip()

        # Keep these values exactly as text at this stage.
        # Example quantity values may contain units such as "10 Nos".
        opening_balance = (
            item.findtext("OPENINGBALANCE")
            or ""
        ).strip()

        closing_balance = (
            item.findtext("CLOSINGBALANCE")
            or ""
        ).strip()

        opening_rate = (
            item.findtext("OPENINGRATE")
            or ""
        ).strip()

        closing_rate = (
            item.findtext("CLOSINGRATE")
            or ""
        ).strip()

        opening_value = (
            item.findtext("OPENINGVALUE")
            or ""
        ).strip()

        closing_value = (
            item.findtext("CLOSINGVALUE")
            or ""
        ).strip()

        stock_items.append(
            {
                "name": name,
                "parent": parent,
                "base_unit": base_unit,
                "opening_balance": opening_balance,
                "opening_rate": opening_rate,
                "opening_value": opening_value,
                "closing_balance": closing_balance,
                "closing_rate": closing_rate,
                "closing_value": closing_value,
            }
        )

    return stock_items


# ============================================================
# INVENTORY VALUE HELPERS
# ============================================================

def _stock_quantity_value(value):
    """
    Extract the numeric part of a Tally quantity.

    Examples:
        "100 Nos"  -> 100.0
        "25.50 Kg" -> 25.5
        "-10 Nos"  -> -10.0

    This keeps the behaviour of the existing parser.
    """

    if value is None:
        return 0.0

    text = str(value).strip()

    # Find the first signed numeric value in the quantity string.
    match = re.search(
        r"[-+]?(?:\d+(?:\.\d*)?|\.\d+)",
        text,
    )

    if not match:
        return 0.0

    return to_float(
        match.group(0)
    )


def _stock_numeric_value(value):
    """
    Extract a numeric stock value or rate.

    The existing parser uses the same numeric extraction logic
    for quantity, rate and value fields.
    """

    return _stock_quantity_value(
        value
    )


# ============================================================
# STOCK SUMMARY
# ============================================================
def _stock_summary_text(node, *tags, default=""):
    """
    Read a Stock Summary field from Tally.

    Tally may return NAME as an XML attribute while other
    requested fields are returned as child elements.
    """

    if node is None:
        return default

    for tag in tags:
        attribute_value = node.attrib.get(tag)

        if attribute_value is not None:
            attribute_value = str(attribute_value).strip()

            if attribute_value:
                return attribute_value

        child = node.find(tag)

        if child is not None and child.text is not None:
            child_value = child.text.strip()

            if child_value:
                return child_value

    return default
def _value_with_quantity_sign(value: float, quantity: float) -> float:
    if quantity < 0:
        return -abs(value)

    return abs(value)


def parse_stock_summary(xml_text: str):
    """
    Parse the Stock Summary collection returned by Tally.

    All report values come directly from the Tally XML response.
    No stock item names, quantities, rates, values, groups,
    units, or dates are hardcoded here.
    """

    root = parse_xml(xml_text)

    rows = []
    seen = set()

    nodes = []

    for node in root.findall(".//STOCKITEM"):
        nodes.append(node)

    for node in root.findall(".//STOCKITEM.LIST"):
        nodes.append(node)

    for node in nodes:

        name = _stock_summary_text(
            node,
            "NAME",
            "STOCKITEMNAME",
        )

        if not name:
            continue

        key = name.casefold()

        if key in seen:
            continue

        seen.add(key)

        # Top-level items have PARENT "&#4; Primary" in Tally.
        parent = normalize_master_name(
            _stock_summary_text(
                node,
                "PARENT",
            )
        )

        category = normalize_master_name(
            _stock_summary_text(
                node,
                "CATEGORY",
            )
        )

        base_units = _stock_summary_text(
            node,
            "BASEUNITS",
            "BASEUNIT",
        )

        opening_balance_raw = _stock_summary_text(
            node,
            "OPENINGBALANCE",
        )

        opening_rate_raw = _stock_summary_text(
            node,
            "OPENINGRATE",
        )

        opening_value_raw = _stock_summary_text(
            node,
            "OPENINGVALUE",
        )

        closing_balance_raw = _stock_summary_text(
            node,
            "CLOSINGBALANCE",
        )

        closing_rate_raw = _stock_summary_text(
            node,
            "CLOSINGRATE",
        )

        closing_value_raw = _stock_summary_text(
            node,
            "CLOSINGVALUE",
        )

        opening_quantity = _stock_quantity_value(
            opening_balance_raw
        )

        opening_rate = _stock_numeric_value(
            opening_rate_raw
        )

        opening_value = _stock_numeric_value(
            opening_value_raw
        )

        closing_quantity = _stock_quantity_value(
            closing_balance_raw
        )

        closing_rate = _stock_numeric_value(
            closing_rate_raw
        )

        closing_value = _stock_numeric_value(
            closing_value_raw
        )

        # Tally's XML carries stock values with the accounting (Dr/Cr)
        # sign, so a positive stock can arrive as a NEGATIVE value.
        # Tally's own screens show the value with the sign of the
        # quantity (3 NOS -> 24,81,681.82), so do the same, and keep
        # rates positive.
        opening_value = _value_with_quantity_sign(
            opening_value, opening_quantity
        )
        closing_value = _value_with_quantity_sign(
            closing_value, closing_quantity
        )
        opening_rate = abs(opening_rate)
        closing_rate = abs(closing_rate)

        rows.append(
            {
                "name": name,
                "parent": parent,
                "category": category,
                "base_units": base_units,
                "opening_quantity": opening_quantity,
                "opening_rate": opening_rate,
                "opening_value": opening_value,
                "closing_quantity": closing_quantity,
                "closing_rate": closing_rate,
                "closing_value": closing_value,
            }
        )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }
# ============================================================
# STOCK GROUPS
# ============================================================

def parse_stock_groups(xml_text: str):
    """
    Parse stock groups returned by Tally.
    """

    root = parse_xml(xml_text)

    rows = []
    seen = set()

    for node in root.findall(
        ".//STOCKGROUP"
    ):

        name = _first_text(
            node,
            "NAME",
        )

        if not name:
            continue

        key = name.casefold()

        if key in seen:
            continue

        seen.add(key)

        rows.append(
            {
                "name": name,
                "parent": normalize_master_name(
                    _text(
                        node,
                        "PARENT",
                    )
                ),
                "is_addable": _text(
                    node,
                    "ISADDABLE",
                ),
                "base_units": _text(
                    node,
                    "BASEUNITS",
                ),
            }
        )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# STOCK CATEGORIES
# ============================================================

def parse_stock_categories(xml_text: str):
    """
    Parse stock categories returned by Tally.
    """

    root = parse_xml(xml_text)

    rows = []
    seen = set()

    for node in root.findall(
        ".//STOCKCATEGORY"
    ):

        name = _first_text(
            node,
            "NAME",
        )

        if not name:
            continue

        key = name.casefold()

        if key in seen:
            continue

        seen.add(key)

        rows.append(
            {
                "name": name,
                "parent": normalize_master_name(
                    _text(
                        node,
                        "PARENT",
                    )
                ),
            }
        )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# GODOWNS
# ============================================================

def parse_godowns(xml_text: str):
    """
    Parse godown / storage-location information returned by Tally.
    """

    root = parse_xml(xml_text)

    rows = []
    seen = set()

    for node in root.findall(".//GODOWN"):
        # Tally can return master fields either as child elements or
        # as attributes on the GODOWN element.
        name = (
            _first_text(node, "NAME")
            or node.get("NAME")
            or ""
        ).strip()

        if not name:
            continue

        key = name.casefold()

        if key in seen:
            continue

        seen.add(key)

        parent = normalize_master_name(
            _text(node, "PARENT")
            or node.get("PARENT")
            or ""
        )

        is_internal = (
            _text(node, "ISINTERNAL")
            or node.get("ISINTERNAL")
            or ""
        ).strip()

        rows.append(
            {
                "name": name,
                "parent": parent,
                "is_internal": is_internal,
            }
        )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# STOCK MOVEMENT
# ============================================================

def parse_stock_movement(xml_text: str):
    """
    Parse stock movement from voucher data returned by Tally.

    One voucher can contain multiple inventory entries, so each
    stock item is returned as its own movement row.
    """

    root = parse_xml(xml_text)

    rows = []
    seen = set()

    vouchers = root.findall(
        ".//VOUCHER"
    )

    for voucher in vouchers:

        voucher_date = format_tally_date(
            _text(
                voucher,
                "DATE",
            )
        )

        voucher_type = _text(
            voucher,
            "VOUCHERTYPENAME",
        )

        voucher_number = _text(
            voucher,
            "VOUCHERNUMBER",
        )

        guid = _text(
            voucher,
            "GUID",
        )

        reference = _text(
            voucher,
            "REFERENCE",
        )

        party = _first_text(
            voucher,
            "PARTYLEDGERNAME",
            "PARTYNAME",
        )

        narration = _text(
            voucher,
            "NARRATION",
        )

        # Cancelled / optional vouchers do not affect stock in Tally.
        is_cancelled = (
            _text(voucher, "ISCANCELLED").strip().casefold() == "yes"
        )
        is_optional = (
            _text(voucher, "ISOPTIONAL").strip().casefold() == "yes"
        )

        inventory_entries = _inventory_entry_nodes(
            voucher
        )

        for entry in inventory_entries:

            stock_item = _first_text(
                entry,
                "STOCKITEMNAME",
                "STOCKITEM",
            )

            if not stock_item:
                continue

            quantity = _stock_quantity_value(
                _text(
                    entry,
                    "ACTUALQTY",
                )
                or _text(
                    entry,
                    "BILLEDQTY",
                )
                or _text(
                    entry,
                    "QTY",
                )
            )

            rate = _stock_numeric_value(
                _text(
                    entry,
                    "RATE",
                )
            )

            amount = _stock_numeric_value(
                _text(
                    entry,
                    "AMOUNT",
                )
            )

            godown = _first_text(
                entry,
                "GODOWNNAME",
                "GODOWN",
            )

            batch = _first_text(
                entry,
                "BATCHNAME",
                "BATCH",
            )

            # Present on Receipt Note / Purchase entries that use
            # Tally's Tracking Number (Order/Bill pending) feature -
            # already present in the raw XML via ALLINVENTORYENTRIES.*,
            # just not previously extracted.
            tracking_number = _first_text(
                entry,
                "TRACKINGNUMBER",
            )

            # ACTUALQTY is always unsigned in Tally; the direction of
            # the movement is carried by ISDEEMEDPOSITIVE
            # (Yes = stock coming in, No = stock going out).
            deemed = _text(entry, "ISDEEMEDPOSITIVE").strip().casefold()
            is_deemed_positive = (
                True if deemed == "yes"
                else False if deemed == "no"
                else None
            )

            # Build a key from existing Tally fields so duplicate
            # entries are not returned twice.
            key = (
                guid,
                voucher_date,
                voucher_type,
                voucher_number,
                stock_item,
                quantity,
                amount,
                tracking_number,
            )

            if key in seen:
                continue

            seen.add(key)

            rows.append(
                {
                    "date": voucher_date,
                    "guid": guid,
                    "voucher_type": voucher_type,
                    "voucher_number": voucher_number,
                    "reference": reference,
                    "party": party,
                    "stock_item": stock_item,
                    "quantity": quantity,
                    "rate": rate,
                    "amount": amount,
                    "godown": godown,
                    "batch": batch,
                    "narration": narration,
                    "tracking_number": tracking_number,
                    "is_deemed_positive": is_deemed_positive,
                    "is_cancelled": is_cancelled,
                    "is_optional": is_optional,
                }
            )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# STOCK MOVEMENT - LOCATION (GODOWN) FILTER
# ============================================================

def filter_stock_movement_by_godown(
    rows: list[dict],
    godown_name: str,
    default_godown: str | None = None,
) -> list[dict]:
    """
    Keep only stock-movement rows that happened at the given
    location (godown).

    Tally does not expose a simple object-level TDL filter for
    "godown of an inventory entry", so this filtering is applied
    in Python against rows already parsed by parse_stock_movement,
    instead of adding filtering logic to the XML request itself.
    """

    if not godown_name:
        return rows

    target = normalize_master_name(godown_name).casefold()

    # Entries saved without a godown (or with "Not Applicable") sit in
    # the company's default location, so they belong to that godown.
    return [
        row
        for row in rows
        if resolve_godown(row.get("godown"), default_godown or "").casefold()
        == target
    ]


# ============================================================
# INVENTORY REGISTER
# ============================================================

def parse_inventory_register(xml_text: str):
    """
    Parse inventory-register rows from Tally voucher data.
    """

    root = parse_xml(xml_text)

    rows = []
    seen = set()

    for voucher in root.findall(
        ".//VOUCHER"
    ):

        voucher_date = format_tally_date(
            _text(
                voucher,
                "DATE",
            )
        )

        guid = _text(
            voucher,
            "GUID",
        )

        voucher_type = _text(
            voucher,
            "VOUCHERTYPENAME",
        )

        voucher_number = _text(
            voucher,
            "VOUCHERNUMBER",
        )

        party = _first_text(
            voucher,
            "PARTYLEDGERNAME",
            "PARTYNAME",
        )

        narration = _text(
            voucher,
            "NARRATION",
        )

        for entry in _inventory_entry_nodes(
            voucher
        ):

            stock_item = _first_text(
                entry,
                "STOCKITEMNAME",
                "STOCKITEM",
            )

            if not stock_item:
                continue

            quantity = _stock_quantity_value(
                _text(
                    entry,
                    "ACTUALQTY",
                )
                or _text(
                    entry,
                    "BILLEDQTY",
                )
                or _text(
                    entry,
                    "QTY",
                )
            )

            rate = _stock_numeric_value(
                _text(
                    entry,
                    "RATE",
                )
            )

            amount = _stock_numeric_value(
                _text(
                    entry,
                    "AMOUNT",
                )
            )

            key = (
                guid,
                voucher_date,
                voucher_type,
                voucher_number,
                stock_item,
                quantity,
                amount,
            )

            if key in seen:
                continue

            seen.add(key)

            rows.append(
                {
                    "date": voucher_date,
                    "guid": guid,
                    "voucher_type": voucher_type,
                    "voucher_number": voucher_number,
                    "party": party,
                    "stock_item": stock_item,
                    "quantity": quantity,
                    "rate": rate,
                    "amount": amount,
                    "narration": narration,
                }
            )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# INVENTORY REGISTER SUMMARY
# ============================================================

def parse_inventory_register_summary(xml_text: str):
    """
    Return inventory-register rows together with the number
    of unique vouchers represented by those rows.
    """

    detail = parse_inventory_register(
        xml_text
    )

    rows = detail.get(
        "rows",
        [],
    )

    voucher_keys = set()

    for row in rows:

        voucher_keys.add(
            (
                row.get("guid"),
                row.get("date"),
                row.get("voucher_type"),
                row.get("voucher_number"),
            )
        )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
        "voucher_count": len(voucher_keys),
    }


# ============================================================
# STOCK VALUATION
# ============================================================

def parse_stock_valuation(xml_text: str):
    """
    Build the existing stock-valuation response from stock-summary
    information.

    This preserves the behaviour of the original parser.
    """

    summary = parse_stock_summary(
        xml_text
    )

    rows = []

    for row in summary.get(
        "rows",
        [],
    ):

        rows.append(
            {
                "name": row.get(
                    "name"
                ),

                "quantity": row.get(
                    "closing_quantity",
                    0,
                ),

                "rate": row.get(
                    "rate",
                    0,
                ),

                "value": row.get(
                    "closing_value",
                    0,
                ),

                "base_units": row.get(
                    "base_units",
                    "",
                ),
            }
        )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


# ============================================================
# NEGATIVE STOCK
# ============================================================

def parse_negative_stock(xml_text: str):
    """
    Return stock-summary rows whose closing quantity is negative.

    This keeps the filtering behaviour already present in parser.py.
    """

    summary = parse_stock_summary(
        xml_text
    )

    rows = []

    for row in summary.get(
        "rows",
        [],
    ):

        quantity = float(
            row.get(
                "closing_quantity",
                0,
            )
            or 0
        )

        if quantity < 0:
            rows.append(row)

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }

# ============================================================
# INVENTORY VOUCHER DETAIL
# ============================================================

def _collect_leaf_fields(node, prefix=""):
    """Collect every leaf XML value without inventing any fields."""
    fields = {}

    for child in list(node):
        tag = child.tag.split("}", 1)[-1]
        key = f"{prefix}.{tag}" if prefix else tag

        nested = list(child)
        text = (child.text or "").strip()

        if nested:
            fields.update(_collect_leaf_fields(child, key))
        elif text:
            fields[key] = text

    return fields


def parse_inventory_voucher_detail(
    xml_text: str,
    voucher_type: str | None = None,
    voucher_number: str | None = None,
    voucher_date: str | None = None,
):
    """
    Parse one Tally inventory voucher, preserving the inventory fields
    returned by Tally. No inventory values are hardcoded.
    """

    root = parse_xml(xml_text)
    vouchers = root.findall(".//VOUCHER")

    for voucher in vouchers:
        current_type = _text(voucher, "VOUCHERTYPENAME")
        current_number = _text(voucher, "VOUCHERNUMBER")
        current_date = format_tally_date(_text(voucher, "DATE"))

        if voucher_type and current_type.casefold() != voucher_type.strip().casefold():
            continue

        if voucher_number and current_number.strip() != voucher_number.strip():
            continue

        if voucher_date and current_date and current_date != voucher_date:
            continue

        entries = []

        # Accounting side of the voucher (e.g. the sales / purchase
        # ledger of an order). Read straight from the Tally response.
        ledger_entries = []
        seen_ledgers = set()

        for path in (
            "./ALLLEDGERENTRIES.LIST",
            "./LEDGERENTRIES.LIST",
        ):
            for ledger in voucher.findall(path):
                ledger_name = normalize_master_name(
                    _text(ledger, "LEDGERNAME")
                )

                if not ledger_name:
                    continue

                ledger_key = (ledger_name, _text(ledger, "AMOUNT"))

                if ledger_key in seen_ledgers:
                    continue

                seen_ledgers.add(ledger_key)

                ledger_entries.append(
                    {
                        "ledger": ledger_name,
                        "amount": _text(ledger, "AMOUNT"),
                        "is_party": (
                            _text(ledger, "ISPARTYLEDGER").casefold() == "yes"
                        ),
                    }
                )

        voucher_fields = _collect_leaf_fields(voucher)

        # Godown named on the voucher itself (Material In / Out show a
        # Source / Destination Godown). Whatever Tally calls it, any
        # voucher-level GODOWN field is passed through.
        voucher_godowns = {
            key: normalize_master_name(value)
            for key, value in voucher_fields.items()
            if "GODOWN" in key.upper() and "." not in key
        }

        for entry in _inventory_entry_nodes(voucher):
            entry_fields = _collect_leaf_fields(entry)

            entries.append(
                {
                    "stock_item": _first_text(
                        entry, "STOCKITEMNAME", "STOCKITEM"
                    ),
                    "godown": _first_text(
                        entry, "GODOWNNAME", "GODOWN"
                    ),
                    "batch": _first_text(
                        entry, "BATCHNAME", "BATCH"
                    ),
                    "actual_quantity": _first_text(
                        entry, "ACTUALQTY"
                    ),
                    "billed_quantity": _first_text(
                        entry, "BILLEDQTY"
                    ),
                    "rate": _first_text(entry, "RATE"),
                    "amount": _first_text(entry, "AMOUNT"),
                    "tracking_number": _first_text(
                        entry, "TRACKINGNUMBER"
                    ),
                    "order_due_date": _first_text(
                        entry, "ORDERDUEDATE", "DUEDATE"
                    ),
                    "fields": entry_fields,
                }
            )

        return {
            "success": True,
            "voucher": {
                "date": current_date,
                "guid": _text(voucher, "GUID"),
                "voucher_type": current_type,
                "voucher_number": current_number,
                "reference": _text(voucher, "REFERENCE"),
                "reference_date": format_tally_date(
                    _text(voucher, "REFERENCEDATE")
                ),
                "party": _first_text(
                    voucher, "PARTYLEDGERNAME", "PARTYNAME"
                ),
                "narration": _text(voucher, "NARRATION"),
                "is_deleted": _text(voucher, "ISDELETED"),
                "is_cancelled": _text(voucher, "ISCANCELLED"),
                "inventory_entries": entries,
                "inventory_entry_count": len(entries),
                "ledger_entries": ledger_entries,
                "voucher_godowns": voucher_godowns,
                "is_order": current_type.strip().casefold()
                in ("sales order", "purchase order"),
                "fields": voucher_fields,
            },
        }

    return {
        "success": True,
        "voucher": None,
    }
