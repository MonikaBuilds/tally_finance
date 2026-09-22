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

def parse_stock_summary(xml_text: str):
    """
    Parse Tally stock-summary information.

    The parser supports both STOCKITEM and STOCKITEM.LIST because
    different Tally report structures can expose stock rows
    differently.
    """

    root = parse_xml(xml_text)

    rows = []
    seen = set()

    nodes = []

    # Collect stock nodes from both supported structures.
    for node in root.findall(
        ".//STOCKITEM"
    ):
        nodes.append(node)

    for node in root.findall(
        ".//STOCKITEM.LIST"
    ):
        nodes.append(node)

    for node in nodes:

        name = _first_text(
            node,
            "NAME",
            "STOCKITEMNAME",
        )

        if not name:
            continue

        # Avoid returning the same stock item more than once.
        key = name.casefold()

        if key in seen:
            continue

        seen.add(key)

        opening_balance = _stock_quantity_value(
            _text(
                node,
                "OPENINGBALANCE",
            )
        )

        closing_balance = _stock_quantity_value(
            _text(
                node,
                "CLOSINGBALANCE",
            )
        )

        opening_value = _stock_numeric_value(
            _text(
                node,
                "OPENINGVALUE",
            )
        )

        closing_value = _stock_numeric_value(
            _text(
                node,
                "CLOSINGVALUE",
            )
        )

        rate = _stock_numeric_value(
            _text(
                node,
                "RATE",
            )
        )

        rows.append(
            {
                "name": name,
                "parent": _text(
                    node,
                    "PARENT",
                ),
                "base_units": _text(
                    node,
                    "BASEUNITS",
                ),
                "opening_quantity": opening_balance,
                "opening_value": opening_value,
                "closing_quantity": closing_balance,
                "closing_value": closing_value,
                "rate": rate,
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
                "parent": _text(
                    node,
                    "PARENT",
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
                "parent": _text(
                    node,
                    "PARENT",
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

    for node in root.findall(
        ".//GODOWN"
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
                "parent": _text(
                    node,
                    "PARENT",
                ),
                "is_internal": _text(
                    node,
                    "ISINTERNAL",
                ),
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
                }
            )

    return {
        "success": True,
        "rows": rows,
        "count": len(rows),
    }


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