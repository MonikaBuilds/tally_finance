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
    NOT_APPLICABLE,
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

            # Sales Order and Purchase Order are order commitments, not physical stock movements
            if (voucher_type or "").strip().casefold() in ("sales order", "purchase order"):
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
            if not godown:
                godown = _first_text(
                    entry.find(".//BATCHALLOCATIONS.LIST"),
                    "GODOWNNAME",
                    "GODOWN",
                )

            batch = _first_text(
                entry,
                "BATCHNAME",
                "BATCH",
            )
            if not batch:
                batch = _first_text(
                    entry.find(".//BATCHALLOCATIONS.LIST"),
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

            # The tracking number is usually stored one level down, on
            # the entry's batch allocation.
            if not tracking_number:
                nested = entry.find(".//TRACKINGNUMBER")

                if nested is not None and nested.text:
                    tracking_number = nested.text.strip()

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


# Tally's own voucher-level fields that the Inventory Voucher screens
# print (delivery / dispatch details). Each is shown only when Tally
# returned a value for it.
_VOUCHER_DETAIL_FIELDS = (
    ("BASICORDERREF", "Order No(s)"),
    ("BASICSHIPDOCUMENTNO", "Dispatch Doc No."),
    ("BASICSHIPPEDBY", "Dispatched through"),
    ("BASICFINALDESTINATION", "Destination"),
    ("BASICDUEDATEOFPYMT", "Terms of Payment"),
)

# The Tally list an entry came from says which side of the voucher it
# is on (stock coming in / going out).
_ENTRY_LIST_SIDE = {
    "INVENTORYENTRIESIN.LIST": "in",
    "INVENTORYENTRIESOUT.LIST": "out",
}

# Voucher types that book against a purchase / sales ledger. Matching
# is by name fragment because companies create their own voucher types
# under these names (same approach as the Bills Pending logic).
_PURCHASE_LEDGER_TYPES = ("receipt note", "rejections out", "purchase")
_SALES_LEDGER_TYPES = ("delivery note", "rejections in", "sales")


def _yes(text) -> bool:
    return str(text or "").strip().casefold() == "yes"


def _split_rate(text: str) -> tuple[str, str]:
    """\"10000.00/NOS\" -> (\"10000.00\", \"NOS\"). Unit is \"\" when absent."""
    rate, _, unit = (text or "").partition("/")
    return rate.strip(), unit.strip()


def _quantity_unit(text: str) -> str:
    """\"12 NOS\" -> \"NOS\" (what follows the number)."""
    parts = (text or "").strip().split(None, 1)
    return parts[1].strip() if len(parts) > 1 else ""


def _entry_side(tag: str, deemed, amount):
    """
    "in" / "out" / None for one inventory entry: the Tally list it came
    from, else ISDEEMEDPOSITIVE (Yes = stock coming in), else the sign
    of the amount (debit = stock in is negative in Tally's XML).
    """
    base = tag.split("}", 1)[-1]

    if base in _ENTRY_LIST_SIDE:
        return _ENTRY_LIST_SIDE[base]

    if deemed:
        return "in" if deemed == "yes" else "out" if deemed == "no" else None

    if amount:
        return "in" if amount < 0 else "out"

    return None


def _tracking(text: str) -> str:
    """Tally's \"Not Applicable\" tracking number means there is none."""
    text = (text or "").strip()
    return "" if text.casefold() == NOT_APPLICABLE.casefold() else text


def _field_label(tag: str) -> str:
    """DESTINATIONGODOWNNAME -> \"Destination Godown\" (Tally's own wording)."""
    base = tag.upper()
    base = base[:-4] if base.endswith("NAME") else base

    return re.sub(r"(?<=[A-Z])(GODOWN)", r" \1", base).title()


def _batch_allocations(entry) -> list[dict]:
    """Every godown / batch allocation of an entry, as Tally lists them."""
    allocations = []

    for node in entry.findall(".//BATCHALLOCATIONS.LIST"):
        allocations.append(
            {
                "godown": normalize_master_name(
                    _first_text(node, "GODOWNNAME", "GODOWN")
                ),
                "batch": _first_text(node, "BATCHNAME", "BATCH"),
                "quantity": _first_text(node, "ACTUALQTY", "BILLEDQTY"),
                "rate": _first_text(node, "RATE"),
                "amount": _first_text(node, "AMOUNT"),
                "tracking_number": _tracking(_first_text(node, "TRACKINGNUMBER")),
                # Any other godown Tally names on the allocation
                # (e.g. the destination godown of a Material Out).
                "godown_fields": {
                    key: value
                    for key, value in _collect_leaf_fields(node).items()
                    if "GODOWN" in key.upper()
                    and key.upper() not in ("GODOWNNAME", "GODOWN")
                },
            }
        )

    return allocations


def _inventory_entry(node) -> dict:
    """One inventory entry as the Inventory Voucher screen prints it."""
    allocations = _batch_allocations(node)
    first = allocations[0] if allocations else {}

    quantity_text = _first_text(node, "ACTUALQTY") or _first_text(node, "BILLEDQTY")
    rate_text, rate_unit = _split_rate(_first_text(node, "RATE"))
    amount_text = _first_text(node, "AMOUNT")

    amount = _optional_number(amount_text)
    quantity = _optional_number(quantity_text)
    rate = _optional_number(rate_text)

    # Tally leaves AMOUNT empty on entries it values itself (e.g. the
    # consumed side of a Stock Journal) and prints quantity x rate.
    amount_value = abs(amount) if amount else None

    if amount_value is None and quantity is not None and rate is not None:
        amount_value = abs(quantity) * abs(rate)

    deemed = _text(node, "ISDEEMEDPOSITIVE").strip().casefold()
    side = _entry_side(node.tag, deemed, amount)

    return {
        "stock_item": _first_text(node, "STOCKITEMNAME", "STOCKITEM"),
        "godown": _first_text(node, "GODOWNNAME", "GODOWN") or first.get("godown", ""),
        "batch": _first_text(node, "BATCHNAME", "BATCH") or first.get("batch", ""),
        "actual_quantity": _first_text(node, "ACTUALQTY"),
        "billed_quantity": _first_text(node, "BILLEDQTY"),
        "rate": _first_text(node, "RATE"),
        "amount": amount_text,
        "tracking_number": _tracking(_first_text(node, "TRACKINGNUMBER"))
        or first.get("tracking_number", ""),
        "order_due_date": _first_text(node, "ORDERDUEDATE", "DUEDATE"),
        # Derived, display-ready values.
        "side": side,
        "unit": rate_unit or _quantity_unit(quantity_text),
        "rate_value": rate,
        "quantity_value": abs(quantity) if quantity is not None else None,
        "amount_value": amount_value,
        "allocations": allocations,
        "fields": _collect_leaf_fields(node),
        "_source": {node.tag},
    }


_MERGE_FIELDS = (
    "godown", "batch", "actual_quantity", "billed_quantity", "rate",
    "amount", "tracking_number", "order_due_date", "unit",
    "rate_value", "quantity_value", "amount_value",
)


def _merge_inventory_entries(nodes) -> list[dict]:
    """
    Tally can hand the same entry back under more than one list (the
    voucher's ALLINVENTORYENTRIES and its IN / OUT lists), one copy
    richer than the other. Entries of the same item, quantity and side
    that come from DIFFERENT lists are one entry: merged, keeping every
    value Tally gave. Two entries from the same list are never merged,
    so a voucher that really lists an item twice keeps both lines.
    """
    entries = [_inventory_entry(node) for node in nodes]

    for position, entry in enumerate(entries):
        entry["_position"] = position

    merged: list[dict] = []

    def key(entry):
        return (
            (entry["stock_item"] or "").casefold(),
            entry["quantity_value"],
        )

    # Entries with a known side first, so one with no side information
    # is matched against them rather than the other way round.
    for entry in sorted(entries, key=lambda e: e["side"] is None):
        target = next(
            (
                m for m in merged
                if key(m) == key(entry)
                and (m["side"] == entry["side"] or entry["side"] is None)
                and not (m["_source"] & entry["_source"])
            ),
            None,
        )

        if target is None:
            merged.append(entry)
            continue

        target["_source"] |= entry["_source"]
        target["_position"] = min(target["_position"], entry["_position"])

        for field in _MERGE_FIELDS:
            if target.get(field) in (None, "") and entry.get(field) not in (None, ""):
                target[field] = entry[field]

        if not target["allocations"]:
            target["allocations"] = entry["allocations"]

        target["fields"] = {**entry["fields"], **target["fields"]}

    # Keep Tally's own order (the position of each entry's first copy).
    merged.sort(key=lambda e: e["_position"])

    for entry in merged:
        entry.pop("_source", None)
        entry.pop("_position", None)

    return merged


def _entries_total(entries: list[dict]) -> dict:
    """Quantity (one unit only) and amount of a group of entries."""
    units = {e["unit"] for e in entries if e["quantity_value"] is not None}
    quantities = [e["quantity_value"] for e in entries if e["quantity_value"] is not None]

    return {
        "quantity": sum(quantities) if quantities and len(units) <= 1 else None,
        "unit": next(iter(units)) if len(units) == 1 else "",
        "amount": sum(e["amount_value"] or 0.0 for e in entries),
    }


def parse_inventory_voucher_detail(
    xml_text: str,
    voucher_type: str | None = None,
    voucher_number: str | None = None,
    voucher_date: str | None = None,
):
    """
    Parse one Tally inventory voucher, preserving the inventory fields
    returned by Tally. No inventory values are hardcoded.

    Besides the raw entries, the result carries what the Inventory
    Voucher Alteration screen prints: which side each entry is on
    (Source / Destination of a Stock Journal), the party and the
    purchase / sales ledger, delivery details, totals and the
    cancelled / optional flags as real booleans.
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

        party = _first_text(voucher, "PARTYLEDGERNAME", "PARTYNAME")

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
                            _yes(_text(ledger, "ISPARTYLEDGER"))
                            or (
                                bool(party)
                                and ledger_name.casefold()
                                == normalize_master_name(party).casefold()
                            )
                        ),
                    }
                )

        voucher_fields = _collect_leaf_fields(voucher)

        merged_entries = _merge_inventory_entries(_inventory_entry_nodes(voucher))

        # Tally also sends entries that name no stock item - the empty
        # side of a Material Out / In, which only records its godown.
        # They are not inventory lines.
        entries = [e for e in merged_entries if e["stock_item"]]
        placeholders = [e for e in merged_entries if not e["stock_item"]]

        sides = {e["side"] for e in entries}
        is_transfer = "in" in sides and "out" in sides

        for entry in entries:
            entry["role"] = (
                None if not is_transfer
                else "destination" if entry["side"] == "in" else "source"
            )

        # Godowns the voucher screen prints in its header (Material Out:
        # Destination Godown). Labels follow Tally's own field names.
        godown_values: dict[str, list[str]] = {}

        def add_godown(label: str, value: str):
            value = normalize_master_name(value)

            if value and value not in godown_values.setdefault(label, []):
                godown_values[label].append(value)

        for key, value in voucher_fields.items():
            if "GODOWN" in key.upper() and "." not in key:
                add_godown(_field_label(key), value)

        for entry in placeholders:
            if entry["godown"]:
                add_godown(
                    "Destination Godown" if entry["side"] == "in" else "Source Godown",
                    entry["godown"],
                )

        if not is_transfer:
            for entry in entries:
                for allocation in entry["allocations"]:
                    for key, value in allocation.get("godown_fields", {}).items():
                        add_godown(_field_label(key.split(".")[-1]), value)

        voucher_godowns = {
            label: ", ".join(values) for label, values in godown_values.items()
        }

        # Party's mailing name and address, when the voucher carries
        # them (Tally then prints Ledger Account / Name and Address).
        address_lines = []

        for tag in ("ADDRESS", "BASICBUYERADDRESS"):
            address_lines = [
                (line.text or "").strip()
                for line in voucher.findall(f"./{tag}.LIST/{tag}")
                if (line.text or "").strip()
            ]

            if address_lines:
                break

        party_details = (
            {
                "name": _first_text(voucher, "PARTYMAILINGNAME", "BASICBUYERNAME")
                or party,
                "address": address_lines,
            }
            if address_lines
            else None
        )

        type_key = current_type.strip().casefold()

        ledger_label = (
            "Purchase" if any(t in type_key for t in _PURCHASE_LEDGER_TYPES)
            else "Sales" if any(t in type_key for t in _SALES_LEDGER_TYPES)
            else ""
        )

        totals = {"all": _entries_total(entries)}

        if is_transfer:
            totals["source"] = _entries_total([e for e in entries if e["role"] == "source"])
            totals["destination"] = _entries_total([e for e in entries if e["role"] == "destination"])

        details = [
            {"label": label, "value": voucher_fields[tag]}
            for tag, label in _VOUCHER_DETAIL_FIELDS
            if voucher_fields.get(tag)
        ]

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
                "party": party,
                "narration": _text(voucher, "NARRATION"),
                "is_deleted": _yes(_text(voucher, "ISDELETED")),
                "is_cancelled": _yes(_text(voucher, "ISCANCELLED")),
                "is_optional": _yes(_text(voucher, "ISOPTIONAL")),
                "inventory_entries": entries,
                "inventory_entry_count": len(entries),
                "ledger_entries": ledger_entries,
                "voucher_godowns": voucher_godowns,
                "party_details": party_details,
                "is_order": type_key in ("sales order", "purchase order"),
                "is_transfer": is_transfer,
                "ledger_label": ledger_label,
                "details": details,
                "totals": totals,
                "fields": voucher_fields,
            },
        }

    return {
        "success": True,
        "voucher": None,
    }


def parse_ledger_balances(xml_text: str) -> dict:
    """
    Closing balance of each ledger in a Tally Ledger collection:
    {name (casefolded): {"amount": float, "side": "Dr" | "Cr"}}.

    Tally's XML carries a debit balance as a negative number and a
    credit balance as a positive one; a balance that already carries a
    Dr / Cr suffix is taken as printed. Ledgers with no balance field
    are left out rather than reported as zero.
    """
    root = parse_xml(xml_text)
    balances = {}

    for ledger in root.findall(".//LEDGER"):
        name = (ledger.get("NAME") or ledger.findtext("NAME") or "").strip()
        raw = (ledger.findtext("CLOSINGBALANCE") or "").strip()

        if not name or not raw:
            continue

        upper = raw.replace(",", "").replace(" ", "").upper()
        digits = upper[:-2] if upper.endswith(("DR", "CR")) else upper
        number = _optional_number(digits)

        if number is None:
            continue

        if upper.endswith("DR"):
            side = "Dr"
        elif upper.endswith("CR"):
            side = "Cr"
        else:
            side = "Dr" if number < 0 else "Cr"

        balances[normalize_master_name(name).casefold()] = {
            "amount": abs(number),
            "side": side,
        }

    return balances


# ============================================================
# ITEM MONTHLY SUMMARY (Tally native report)
# ============================================================

MONTH_MAP = {
    "april": 4, "may": 5, "june": 6, "july": 7,
    "august": 8, "september": 9, "october": 10, "november": 11,
    "december": 12, "january": 1, "february": 2, "march": 3,
}

VCH_TYPE_DISPLAY_MAP = {
    "stk jrnl": "Stock Journal",
    "mat out": "Material Out",
    "mat in": "Material In",
    "rej out": "Rejections Out",
    "rej in": "Rejections In",
    "rcpt note": "Receipt Note",
    "del note": "Delivery Note",
    "purc": "Purchase",
    "sales": "Sales",
    "pymt": "Payment",
    "rcpt": "Receipt",
    "jrnl": "Journal",
}


def _optional_number(text):
    """None when Tally left the field blank, else the signed number."""
    if text is None or not str(text).strip():
        return None

    return _stock_quantity_value(text)


def _tally_amount(text, *, debit: bool):
    """
    An amount the way Tally prints it, sign included.

    Tally's XML carries debit amounts (stock coming in, closing stock)
    with a minus sign and credit amounts (stock going out) as they are,
    so the printed sign is the XML sign reversed for the debit columns.
    A blank field stays None. Returns are therefore negative on the
    printed screen too: "(-)10,50,000.00".
    """
    value = _optional_number(text)

    if value is None:
        return None

    value = -value if debit else value

    return 0.0 if value == 0 else value


def parse_item_monthly_summary(xml_text: str, start_year: int = 2025) -> list[dict]:
    """
    Parse Tally's native Item Monthly Summary XML response.
    Each period node contains exact inward, outward and closing quantities and values.
    """
    root = parse_xml(xml_text)
    rows = []

    periods = root.findall(".//DSPPERIOD")
    stkinfos = root.findall(".//DSPSTKINFO")

    import calendar

    for p_node, s_node in zip(periods, stkinfos):
        p_name = (p_node.text or "").strip().lower()
        month_num = MONTH_MAP.get(p_name)
        if not month_num:
            continue

        year = start_year if month_num >= 4 else start_year + 1
        month_str = f"{year}-{month_num:02d}"

        in_qty = _stock_quantity_value(_text(s_node, ".//DSPINQTY"))
        in_val = _tally_amount(_text(s_node, ".//DSPDRAMTA"), debit=True)
        out_qty = _stock_quantity_value(_text(s_node, ".//DSPOUTQTY"))
        out_val = _tally_amount(_text(s_node, ".//DSPNETTCRAMTA"), debit=False)
        cl_qty = _stock_quantity_value(_text(s_node, ".//DSPCLQTY"))
        cl_val = _tally_amount(_text(s_node, ".//DSPCLAMTA"), debit=True)

        _, last_day = calendar.monthrange(year, month_num)

        rows.append({
            "month": month_str,
            "from": f"{month_str}-01",
            "to": f"{month_str}-{last_day:02d}",
            "inward_quantity": in_qty or 0.0,
            "inward_value": in_val or 0.0,
            "outward_quantity": out_qty or 0.0,
            "outward_value": out_val or 0.0,
            "closing_quantity": cl_qty or 0.0,
            "closing_value": cl_val or 0.0,
            "pending_bills_quantity": 0.0,
        })

    return rows


# ============================================================
# STOCK / GODOWN VOUCHERS (Tally native report)
# ============================================================

def parse_tally_vouchers_report(xml_text: str) -> list[dict]:
    """
    Parse Tally's native Godown Vouchers or Stock Vouchers report XML.
    Returns rows matching Tally's display with Particulars, Vch Type,
    Inwards, Outwards and daily Closing balances.

    The report is read line by line, in document order: every
    DSPVCHDATE starts a new line and the fields that follow belong to
    it. Lines do not all carry every field (the "(Sale Bills Pending)"
    line has no voucher type), so the fields are not paired up by
    position. Amounts keep Tally's sign; fields Tally leaves blank stay
    None.

    A line without a voucher type that follows a Bills Pending line is
    one of the notes that line is made of; it is returned in that
    line's "children" instead of as a voucher of its own.
    """
    root = parse_xml(xml_text)

    lines = []
    current = None

    def clean(node):
        return (node.text or "").strip()

    for node in root.iter():
        tag = node.tag

        if tag == "DSPVCHDATE":
            current = {
                "date": clean(node),
                "account": "",
                "vtype": "",
                "in": None,
                "out": None,
                "cl": None,
            }
            lines.append(current)

        elif current is None:
            continue

        elif tag == "DSPVCHITEMACCOUNT":
            current["account"] = clean(node)

        elif tag == "DSPVCHTYPE":
            current["vtype"] = clean(node)

        elif tag == "DSPINBLOCK":
            current["in"] = node

        elif tag == "DSPOUTBLOCK":
            current["out"] = node

        elif tag == "DSPCLBLOCK":
            current["cl"] = node

    rows = []
    last_date = ""
    last_pending = None

    for line in lines:
        date_raw = line["date"] or last_date
        last_date = date_raw

        account = line["account"]
        is_pending = account.startswith("(") and account.endswith(")")

        in_qty = _optional_number(_text(line["in"], "DSPVCHINQTY"))
        in_val = _tally_amount(_text(line["in"], "DSPVCHINAMT"), debit=True)
        out_qty = _optional_number(_text(line["out"], "DSPVCHOUTQTY"))
        out_val = _tally_amount(_text(line["out"], "DSPVCHNETTOUTAMT"), debit=False)
        cl_qty = _optional_number(_text(line["cl"], "DSPVCHCLQTY"))
        cl_val = _tally_amount(_text(line["cl"], "DSPVCHCLAMT"), debit=True)

        date = format_tally_date(date_raw) if date_raw else None

        if last_pending is not None and not is_pending and not line["vtype"]:
            last_pending["children"].append(
                {
                    "date": date,
                    "party": account,
                    "tracking_number": "",
                    "quantity": out_qty if out_qty is not None else in_qty,
                }
            )
            continue

        full_vt = VCH_TYPE_DISPLAY_MAP.get(line["vtype"].lower(), line["vtype"])

        row = {
            "kind": "pending" if is_pending else "voucher",
            "date": date,
            "particulars": account,
            "voucher_type": full_vt,
            "voucher_number": "",
            "reference": "",
            "guid": "",
            "inward_quantity": in_qty,
            "inward_value": in_val,
            "outward_quantity": out_qty,
            "outward_value": out_val,
            "closing_quantity": cl_qty,
            "closing_value": cl_val,
        }

        if is_pending:
            row["children"] = []
            last_pending = row
        else:
            last_pending = None

        rows.append(row)

    return rows

