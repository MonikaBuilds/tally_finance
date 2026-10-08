"""
Stock Group / Stock Category / Godown summary logic.

Everything here works on rows that were ALREADY fetched from Tally
(stock items, group/category/godown masters, voucher inventory
entries). Nothing is hardcoded: names, quantities, rates and values all
come from the Tally responses passed in.

Why this module exists
----------------------
Tally's "List of Stock Groups / Categories / Godowns" always shows a
reserved root called "Primary" (shown as "♦ Primary" in the UI). The
root is NOT a master object, so a plain master collection never
contains it - a company that only has the root therefore looked empty.
Tally also stores the root as the PARENT of top-level objects using a
control character ("&#4; Primary"), so comparing PARENT against the
text "Primary" never matched either. `normalize_master_name` and the
`ROOT_NAME` handling below fix both problems in one place.
"""

import re

from app.tally.parsers.common import (
    parse_xml,
    to_float,
    _text,
    _first_text,
)

# Tally's reserved root name for stock groups, categories and godowns.
ROOT_NAME = "Primary"

# Shown by Tally for "no category" / "no godown" on an entry.
NOT_APPLICABLE = "Not Applicable"

# Voucher types that never move stock, so they must not be counted when
# working out how much stock sits in a godown.
NON_STOCK_VOUCHER_TYPES = {
    "sales order",
    "purchase order",
    "physical stock",
}

_CONTROL_CHARS = re.compile(r"[\x00-\x1f\x7f]")


# ============================================================
# NAME HELPERS
# ============================================================

def normalize_master_name(value) -> str:
    """
    Clean a master name / PARENT value returned by Tally.

    "&#4; Primary", "\\x04 Primary" and "♦ Primary" all become
    "Primary"; ordinary names only lose surrounding whitespace.
    """
    if value is None:
        return ""

    text = _CONTROL_CHARS.sub("", str(value))
    text = text.replace("\u2666", "")

    return re.sub(r"\s+", " ", text).strip()


def name_key(value) -> str:
    return normalize_master_name(value).casefold()


def is_root_name(value) -> bool:
    return name_key(value) in ("", ROOT_NAME.casefold())


def is_not_applicable(value) -> bool:
    return name_key(value) in ("", NOT_APPLICABLE.casefold())


def node_of(value, *, na_is_root: bool) -> str:
    """
    Map a PARENT / CATEGORY / GODOWN value to the tree node it hangs
    off. Root-like values (and, when `na_is_root`, "Not Applicable")
    map to the root.
    """
    text = normalize_master_name(value)

    if is_root_name(text):
        return ROOT_NAME

    if na_is_root and is_not_applicable(text):
        return ROOT_NAME

    return text


def with_root_row(rows: list[dict], name_field: str) -> list[dict]:
    """
    Prepend Tally's implicit "Primary" root to a master list, unless
    Tally already returned it. Root rows carry `is_primary=True`.
    """
    result = [
        {
            name_field: ROOT_NAME,
            "parent": "",
            "is_primary": True,
        }
    ]

    for row in rows:
        if is_root_name(row.get(name_field)):
            continue

        result.append({**row, "is_primary": False})

    return result


# ============================================================
# OPENING BALANCES PER GODOWN (stock item master)
# ============================================================

def parse_item_godown_openings(xml_text: str) -> list[dict]:
    """
    Read each stock item's per-godown opening allocations
    (BATCHALLOCATIONS.LIST) from a Stock Item collection response.
    """
    root = parse_xml(xml_text)

    result = []

    nodes = root.findall(".//STOCKITEM") + root.findall(".//STOCKITEM.LIST")

    for node in nodes:
        item_name = (
            node.attrib.get("NAME")
            or _first_text(node, "NAME", "STOCKITEMNAME")
        )
        item_name = (item_name or "").strip()

        if not item_name:
            continue

        for alloc in node.findall("./BATCHALLOCATIONS.LIST"):
            quantity = _quantity(_text(alloc, "OPENINGBALANCE"))
            value = _quantity(_text(alloc, "OPENINGVALUE"))

            if not quantity and not value:
                continue

            result.append(
                {
                    "stock_item": item_name,
                    "godown": _text(alloc, "GODOWNNAME"),
                    "quantity": quantity,
                    "value": value,
                }
            )

    return result


def _quantity(value) -> float:
    """First signed number in a Tally quantity/amount string."""
    if value is None:
        return 0.0

    match = re.search(r"[-+]?(?:\d[\d,]*(?:\.\d*)?|\.\d+)", str(value))

    if not match:
        return 0.0

    return to_float(match.group(0))


# ============================================================
# DEFAULT GODOWN
# ============================================================

def pick_default_godown(godown_masters: list[dict]) -> str:
    """
    Entries with no godown (or "Not Applicable") sit in the company's
    default location. Resolve that name from the godown masters:
    the only non-root godown, else the one Tally calls "Main Location".
    """
    names = [
        normalize_master_name(g.get("name") or g.get("godown"))
        for g in godown_masters
    ]
    names = [n for n in names if n and not is_root_name(n)]

    if len(names) == 1:
        return names[0]

    for n in names:
        if n.casefold() == "main location":
            return n

    return names[0] if names else ""


def resolve_godown(value, default_godown: str) -> str:
    text = normalize_master_name(value)

    if is_not_applicable(text) or is_root_name(text):
        return default_godown

    return text


# ============================================================
# GODOWN-WISE BALANCES
# ============================================================

def build_godown_balances(
    *,
    items: list[dict],
    godown_masters: list[dict],
    opening_allocations: list[dict],
    movement_rows: list[dict],
) -> list[dict]:
    """
    One row per (godown, stock item).

    Item totals (quantity / rate / value) are Tally's own closing
    figures from the Stock Item collection.

    * If all of an item's stock is in ONE godown (its opening
      allocations and voucher entries all resolve to the same godown)
      that godown receives Tally's figures unchanged - this matches
      Tally exactly, including adjustments such as pending sale bills
      that can't be re-derived from vouchers.
    * If an item is spread over several godowns, each godown's quantity
      is its opening allocation plus the signed voucher movement in
      that godown, valued at Tally's item closing rate. Those rows are
      flagged `approximate=True`.
    """
    default_godown = pick_default_godown(godown_masters)

    touched: dict[str, dict[str, float]] = {}
    opening_qty: dict[str, dict[str, float]] = {}

    for alloc in opening_allocations:
        item = alloc["stock_item"]
        godown = resolve_godown(alloc.get("godown"), default_godown)

        touched.setdefault(item, {}).setdefault(godown, 0.0)
        touched[item][godown] += alloc.get("quantity") or 0.0

        opening_qty.setdefault(item, {}).setdefault(godown, 0.0)
        opening_qty[item][godown] += alloc.get("quantity") or 0.0

    for row in movement_rows:
        if (row.get("voucher_type") or "").strip().casefold() in NON_STOCK_VOUCHER_TYPES:
            continue

        if row.get("is_cancelled") or row.get("is_optional"):
            continue

        item = row.get("stock_item")

        if not item:
            continue

        godown = resolve_godown(row.get("godown"), default_godown)
        quantity = abs(row.get("quantity") or 0.0)

        if row.get("is_deemed_positive") is False:
            quantity = -quantity

        touched.setdefault(item, {}).setdefault(godown, 0.0)
        touched[item][godown] += quantity

    balances = []

    for item in items:
        name = item.get("name")
        godowns = touched.get(name, {})

        base = {
            "stock_item": name,
            "stock_group": item.get("parent"),
            "unit": item.get("base_units"),
        }

        if len(godowns) <= 1:
            godown = next(iter(godowns), default_godown)

            balances.append(
                {
                    **base,
                    "godown": godown,
                    "opening_quantity": item.get("opening_quantity"),
                    "opening_value": item.get("opening_value"),
                    "closing_quantity": item.get("closing_quantity"),
                    "closing_rate": item.get("closing_rate"),
                    "closing_value": item.get("closing_value"),
                    "approximate": False,
                }
            )
            continue

        rate = item.get("closing_rate") or 0.0

        for godown, quantity in godowns.items():
            opening = opening_qty.get(name, {}).get(godown, 0.0)

            balances.append(
                {
                    **base,
                    "godown": godown,
                    "opening_quantity": opening,
                    "opening_value": opening * (item.get("opening_rate") or rate),
                    "closing_quantity": quantity,
                    "closing_rate": rate,
                    "closing_value": quantity * rate,
                    "approximate": True,
                }
            )

    return balances


# ============================================================
# HIERARCHY SUMMARY (groups / categories / godowns)
# ============================================================

def _aggregate(rows: list[dict]) -> dict:
    units = {r.get("unit") for r in rows if r.get("unit")}
    comparable = len(units) <= 1

    def total(key):
        return sum((r.get(key) or 0.0) for r in rows)

    closing_quantity = total("closing_quantity")
    closing_value = total("closing_value")

    return {
        "unit": next(iter(units)) if len(units) == 1 else "",
        "opening_quantity": total("opening_quantity") if comparable else None,
        "opening_value": total("opening_value"),
        "closing_quantity": closing_quantity if comparable else None,
        "closing_rate": (
            closing_value / closing_quantity
            if comparable and closing_quantity
            else 0.0
        ),
        "closing_value": closing_value,
        "approximate": any(r.get("approximate") for r in rows),
    }


def _is_zero(row: dict) -> bool:
    return not (row.get("closing_quantity") or 0) and not (
        row.get("closing_value") or 0
    )


def build_hierarchy_summary(
    *,
    selected: str | None,
    masters: list[dict],
    name_field: str,
    leaf_rows: list[dict],
    node_field: str,
    na_is_root: bool,
    include_zero: bool = False,
    kind_label: str = "group",
) -> dict | None:
    """
    Tally's "<Group|Category|Godown> Summary" screen for one node.

    Rows are the node's child masters (each rolled up over everything
    below it) followed by the leaf rows (stock items, or godown/item
    balances) that sit directly on the node.

    Returns None when `selected` is neither the root nor a known
    master, so callers can answer 404 instead of an empty report.
    """
    selected_node = node_of(selected, na_is_root=False)

    children_of: dict[str, list[str]] = {}
    known = {ROOT_NAME.casefold()}

    for master in masters:
        name = normalize_master_name(master.get(name_field))

        if not name or is_root_name(name):
            continue

        known.add(name.casefold())
        parent = node_of(master.get("parent"), na_is_root=False)
        children_of.setdefault(parent.casefold(), []).append(name)

    if selected_node.casefold() not in known:
        return None

    def subtree(node: str) -> set[str]:
        seen = {node.casefold()}
        stack = [node]

        while stack:
            current = stack.pop()

            for child in children_of.get(current.casefold(), []):
                if child.casefold() not in seen:
                    seen.add(child.casefold())
                    stack.append(child)

        return seen

    def leaf_node(row: dict) -> str:
        return node_of(row.get(node_field), na_is_root=na_is_root)

    rows = []

    for child in sorted(children_of.get(selected_node.casefold(), []), key=str.casefold):
        below = subtree(child)
        members = [r for r in leaf_rows if leaf_node(r).casefold() in below]

        rows.append(
            {
                "kind": kind_label,
                "name": child,
                "parent": selected_node,
                **_aggregate(members),
            }
        )

    direct = [r for r in leaf_rows if leaf_node(r).casefold() == selected_node.casefold()]

    for row in sorted(direct, key=lambda r: (r.get("stock_item") or "").casefold()):
        rows.append(
            {
                "kind": "item",
                "name": row.get("stock_item"),
                "parent": selected_node,
                "stock_group": row.get("stock_group"),
                "unit": row.get("unit"),
                "opening_quantity": row.get("opening_quantity"),
                "opening_value": row.get("opening_value"),
                "closing_quantity": row.get("closing_quantity"),
                "closing_rate": row.get("closing_rate"),
                "closing_value": row.get("closing_value"),
                "approximate": bool(row.get("approximate")),
            }
        )

    if not include_zero:
        rows = [r for r in rows if not _is_zero(r)]

    below_selected = subtree(selected_node)
    members = [r for r in leaf_rows if leaf_node(r).casefold() in below_selected]

    return {
        "selected": selected_node,
        "rows": rows,
        "totals": _aggregate(members),
    }


# ============================================================
# MONTHLY MOVEMENT (Stock Item Monthly Summary)
# ============================================================

# Tally reports a return as a NEGATIVE entry on the opposite side
# instead of as ordinary movement: a Rejections Out / Debit Note takes
# stock out of the godown but shows as negative INWARDS, and a
# Rejections In / Credit Note brings it back but shows as negative
# OUTWARDS (e.g. "Rejections Out (-)5 NOS" under Inwards).
_NEGATIVE_INWARD_TYPES = {"rejections out", "debit note"}
_NEGATIVE_OUTWARD_TYPES = {"rejections in", "credit note"}


def movement_effect(row: dict) -> dict | None:
    """
    Split one stock-movement row into Tally's Inwards / Outwards
    columns. Returns None for rows that do not move stock (orders,
    physical stock, cancelled or optional vouchers).
    """
    voucher_type = (row.get("voucher_type") or "").strip().casefold()

    if voucher_type in NON_STOCK_VOUCHER_TYPES:
        return None

    if row.get("is_cancelled") or row.get("is_optional"):
        return None

    quantity = abs(row.get("quantity") or 0.0)
    value = abs(row.get("amount") if row.get("amount") is not None else row.get("value") or 0.0)

    if voucher_type in _NEGATIVE_INWARD_TYPES:
        side, sign = "in", -1
    elif voucher_type in _NEGATIVE_OUTWARD_TYPES:
        side, sign = "out", -1
    else:
        deemed = row.get("is_deemed_positive")

        if deemed is None:
            deemed = (row.get("quantity") or 0.0) >= 0

        side, sign = ("in" if deemed else "out"), 1

    return {
        "side": side,
        "quantity": sign * quantity,
        "value": sign * value,
    }


def month_starts(from_date, to_date):
    """First day of every month from from_date to to_date inclusive."""
    months = []
    year, month = from_date.year, from_date.month

    while (year, month) <= (to_date.year, to_date.month):
        months.append((year, month))
        month += 1

        if month == 13:
            year, month = year + 1, 1

    return months
