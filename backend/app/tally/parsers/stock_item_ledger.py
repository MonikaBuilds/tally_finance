"""
Stock Item Monthly Summary / Stock Item Vouchers logic.

Everything here works on rows that were ALREADY fetched from Tally
(the item's master opening balance and its voucher inventory entries).
Nothing is hardcoded: names, quantities, rates and values all come from
the rows passed in.

Why this module exists
----------------------
Tally prints every month of the Stock Item Monthly Summary (and every
line of Stock Item Vouchers) from one running balance:

    Opening Balance
    + Inwards   - Outwards
    = Closing Balance

* Returns are NEGATIVE entries on the opposite side
  (Rejections Out = negative Inwards, Rejections In = negative Outwards).
* Delivery Notes / Receipt Notes (and the returns booked against them)
  are not listed as vouchers; Tally rolls them into one
  "(Sale Bills Pending)" / "(Purchase Bills Pending)" line dated at the
  end of the period, and counts them in Outwards / Inwards.
* The closing VALUE follows the item's costing method. For the default
  Average Cost method Tally values closing stock at
      closing quantity x (total inward value / total inward quantity)
  where "inward" includes the opening balance. That is the rule used
  here, so the figures match Tally's screens.

Asking Tally for a balance "as on" each month end is unreliable (it can
answer with the current balance for every date), so the running balance
is built once, from the opening balance and the vouchers.
"""

from datetime import date

from app.tally.parsers.inventory_summary import (
    month_starts,
    movement_effect,
)

# Voucher types that Tally rolls into "Bills Pending" instead of
# listing them one by one. Matching is by name fragment because
# companies often create their own voucher types under these names.
_SALE_PENDING = "delivery note"
_SALE_RETURN = "rejections in"
_PURCHASE_PENDING = "receipt note"
_PURCHASE_RETURN = "rejections out"

SALE_PENDING_LABEL = "Sale Bills Pending"
PURCHASE_PENDING_LABEL = "Purchase Bills Pending"


def _round(value) -> float:
    return round(float(value or 0.0), 2)


def _vtype(row: dict) -> str:
    return (row.get("voucher_type") or "").strip().casefold()


def _tracking(row: dict) -> str:
    return (row.get("tracking_number") or "").strip().casefold()


# ============================================================
# CLASSIFYING VOUCHER ROWS
# ============================================================

def _pending_side(row: dict, vtypes: set[str], has_tracking: dict) -> str | None:
    """
    "sale" / "purchase" when the row belongs to Tally's Bills Pending
    roll-up, otherwise None (an ordinary voucher line).
    """
    vt = _vtype(row)
    tracked = bool(_tracking(row))

    if _SALE_PENDING in vt:
        return "sale"

    if _PURCHASE_PENDING in vt:
        return "purchase"

    # A return only joins the pending roll-up when it is booked against
    # a delivery / receipt note (a tracking number, or such notes exist
    # for the item). A stand-alone return is an ordinary voucher.
    if _SALE_RETURN in vt and (tracked or has_tracking["sale"]):
        return "sale"

    if _PURCHASE_RETURN in vt and (tracked or has_tracking["purchase"]):
        return "purchase"

    return None


def prepare_events(rows: list[dict]) -> list[dict]:
    """
    Turn raw stock-movement rows (one item) into dated events with
    Tally's Inwards / Outwards effect.

    Each event: date, side ("in"/"out"), quantity, value (signed, so a
    return is negative), pending ("sale"/"purchase"/None), the source
    row and its original position (to keep Tally's voucher order).
    """
    vtypes = {_vtype(r) for r in rows}
    has_notes = {
        "sale": any(_SALE_PENDING in v for v in vtypes),
        "purchase": any(_PURCHASE_PENDING in v for v in vtypes),
    }

    events = []

    for index, row in enumerate(rows):
        effect = movement_effect(row)

        if effect is None or not row.get("date"):
            continue

        events.append(
            {
                "date": row["date"],
                "side": effect["side"],
                "quantity": effect["quantity"],
                "value": effect["value"],
                "pending": _pending_side(row, vtypes, has_notes),
                "billing": False,
                "row": row,
                "index": index,
            }
        )

    # Goods billed against a delivery / receipt note (same tracking
    # number) are no longer "pending": the bill moves the stock, so the
    # pending line is reduced by the billed quantity.
    tracked = {"sale": set(), "purchase": set()}

    for event in events:
        if event["pending"] and _tracking(event["row"]):
            if _SALE_PENDING in _vtype(event["row"]):
                tracked["sale"].add(_tracking(event["row"]))
            elif _PURCHASE_PENDING in _vtype(event["row"]):
                tracked["purchase"].add(_tracking(event["row"]))

    for event in events:
        if event["pending"] or not _tracking(event["row"]):
            continue

        side = "sale" if event["side"] == "out" else "purchase"

        if _tracking(event["row"]) in tracked[side]:
            event["billing"] = side

    events.sort(key=lambda e: (e["date"], e["index"]))

    return events


def _pending_contribution(event: dict) -> tuple[str, str, float, float] | None:
    """(pending side, in/out column, quantity, value) of an event."""
    if event["pending"]:
        return event["pending"], event["side"], event["quantity"], event["value"]

    if event["billing"]:
        # The bill reduces what is pending on the same column.
        return event["billing"], event["side"], -event["quantity"], -event["value"]

    return None


# ============================================================
# RUNNING BALANCE
# ============================================================

class _Balance:
    """Quantity plus the totals needed to value it at average cost."""

    def __init__(self, quantity: float, value: float):
        self.quantity = quantity
        self.inward_quantity = quantity
        self.inward_value = value
        self.opening_value = value

    def rate(self) -> float:
        if not self.inward_quantity:
            return 0.0
        return self.inward_value / self.inward_quantity

    def value(self, quantity: float | None = None) -> float:
        quantity = self.quantity if quantity is None else quantity

        if not quantity:
            return 0.0

        return quantity * self.rate()

    def apply(self, side: str, quantity: float, value: float) -> None:
        if side == "in":
            self.quantity += quantity
            self.inward_quantity += quantity
            self.inward_value += value
        else:
            self.quantity -= quantity


def _opening_state(events, opening_quantity, opening_value, from_iso):
    """Balance at the start of the period, and the events inside it."""
    balance = _Balance(opening_quantity or 0.0, opening_value or 0.0)
    before = [e for e in events if e["date"] < from_iso]

    for event in before:
        balance.apply(event["side"], event["quantity"], event["value"])

    inside = [e for e in events if e["date"] >= from_iso]

    # With nothing before the period the opening value is exactly
    # Tally's own opening value; otherwise it is the valued balance.
    shown = (
        balance.opening_value
        if not before
        else _round(balance.value())
    )

    return balance, inside, shown


# ============================================================
# STOCK ITEM MONTHLY SUMMARY
# ============================================================

def build_monthly_summary(
    rows: list[dict],
    *,
    opening_quantity: float,
    opening_value: float,
    from_date: date,
    to_date: date,
) -> dict:
    """
    Month-by-month Inwards / Outwards / Closing, like Tally's
    "Stock Item Monthly Summary".
    """
    events = prepare_events(rows)
    balance, inside, shown_opening_value = _opening_state(
        events, opening_quantity, opening_value, from_date.isoformat()
    )

    opening_qty = balance.quantity
    months = month_starts(from_date, to_date)

    buckets = {
        key: {
            "inward_quantity": 0.0,
            "inward_value": 0.0,
            "outward_quantity": 0.0,
            "outward_value": 0.0,
            "pending_bills_quantity": 0.0,
        }
        for key in months
    }

    closings = {}
    pending_events = list(inside)
    cursor = 0
    last_iso = to_date.isoformat()

    for key in months:
        year, month = key
        month_end = _month_end_iso(year, month)

        while cursor < len(pending_events) and pending_events[cursor]["date"] <= min(month_end, last_iso):
            event = pending_events[cursor]
            cursor += 1

            if event["date"] > last_iso:
                break

            bucket = buckets[key]

            if event["billing"]:
                # Billed goods were already counted when the delivery /
                # receipt note was booked: the bill only clears the
                # pending line, so the stock does not move twice.
                bucket["pending_bills_quantity"] -= event["quantity"] * (
                    1 if event["side"] == "out" else -1
                )
                continue

            column = "inward" if event["side"] == "in" else "outward"
            bucket[f"{column}_quantity"] += event["quantity"]
            bucket[f"{column}_value"] += event["value"]

            if event["pending"]:
                bucket["pending_bills_quantity"] += event["quantity"] * (
                    1 if event["side"] == "out" else -1
                )

            balance.apply(event["side"], event["quantity"], event["value"])

        closings[key] = (balance.quantity, _round(balance.value()))

    result_rows = []

    for key in months:
        year, month = key
        first = date(year, month, 1)
        last = date.fromisoformat(_month_end_iso(year, month))
        bucket = buckets[key]
        closing_quantity, closing_value = closings[key]

        result_rows.append(
            {
                "month": f"{year:04d}-{month:02d}",
                "from": max(first, from_date).isoformat(),
                "to": min(last, to_date).isoformat(),
                "inward_quantity": bucket["inward_quantity"],
                "inward_value": _round(bucket["inward_value"]),
                "outward_quantity": bucket["outward_quantity"],
                "outward_value": _round(bucket["outward_value"]),
                "pending_bills_quantity": bucket["pending_bills_quantity"],
                "closing_quantity": closing_quantity,
                "closing_value": closing_value,
            }
        )

    return {
        "opening": {"quantity": opening_qty, "value": shown_opening_value},
        "rows": result_rows,
        "closing": {
            "quantity": balance.quantity,
            "value": _round(balance.value()),
        },
    }


def _month_end_iso(year: int, month: int) -> str:
    import calendar

    return date(year, month, calendar.monthrange(year, month)[1]).isoformat()


# ============================================================
# STOCK ITEM VOUCHERS
# ============================================================

def _particulars(row: dict, voucher_rows: list[dict], item_key: str) -> str:
    """
    The party for a sales / purchase style voucher; for a stock journal
    (no party) the other item(s) in the same voucher, like Tally.
    """
    party = (row.get("party") or "").strip()

    if party:
        return party

    others = []

    for other in voucher_rows:
        name = (other.get("stock_item") or "").strip()

        if name and name.casefold() != item_key and name not in others:
            others.append(name)

    return ", ".join(others)


def build_voucher_ledger(
    rows: list[dict],
    *,
    all_rows: list[dict] | None = None,
    stock_item_name: str,
    opening_quantity: float,
    opening_value: float,
    from_date: date,
    to_date: date,
) -> dict:
    """
    Tally's "Stock Item Vouchers": Opening Balance, one line per
    voucher, the Bills Pending roll-up at the end of the period and the
    Inwards / Outwards / Closing totals.

    rows      - this item's movement rows (whole history Tally returned)
    all_rows  - every row of those vouchers (to name a stock journal's
                counterpart item); defaults to rows
    """
    item_key = stock_item_name.strip().casefold()
    by_voucher: dict[str, list[dict]] = {}

    for row in all_rows if all_rows is not None else rows:
        by_voucher.setdefault(row.get("guid") or id(row), []).append(row)

    events = prepare_events(rows)
    balance, inside, shown_opening_value = _opening_state(
        events, opening_quantity, opening_value, from_date.isoformat()
    )

    opening_qty = balance.quantity
    last_iso = to_date.isoformat()
    inside = [e for e in inside if e["date"] <= last_iso]

    # Net effect of the pending roll-up on the closing quantity, per
    # side. Tally values closing stock with these included, even on the
    # voucher lines that come before the Bills Pending line.
    pending = {"sale": [], "purchase": []}

    for event in inside:
        contribution = _pending_contribution(event)

        if contribution:
            pending[contribution[0]].append((event, contribution))

    def closing_effect(side: str) -> float:
        total = 0.0

        for _event, (_side, column, quantity, _value) in pending[side]:
            total += -quantity if column == "out" else quantity

        return total

    remaining = {side: closing_effect(side) for side in pending}

    lines = []
    in_qty = out_qty = 0.0
    in_val = out_val = 0.0

    visible = [e for e in inside if not e["pending"]]

    for position, event in enumerate(visible):
        row = event["row"]
        column = "inward" if event["side"] == "in" else "outward"

        balance.apply(event["side"], event["quantity"], event["value"])

        # Pending documents are not listed, but they still count in the
        # balance; keep them out of the visible running quantity.
        line = {
            "kind": "voucher",
            "date": event["date"],
            "particulars": _particulars(
                row,
                by_voucher.get(row.get("guid") or id(row), []),
                item_key,
            ),
            "voucher_type": row.get("voucher_type"),
            "voucher_number": row.get("voucher_number"),
            "reference": row.get("reference"),
            "godown": row.get("godown"),
            "inward_quantity": None,
            "inward_value": None,
            "outward_quantity": None,
            "outward_value": None,
            "closing_quantity": None,
            "closing_value": None,
        }
        line[f"{column}_quantity"] = event["quantity"]
        line[f"{column}_value"] = _round(event["value"])

        if event["side"] == "in":
            in_qty += event["quantity"]
            in_val += event["value"]
        else:
            out_qty += event["quantity"]
            out_val += event["value"]

        # Tally shows the closing balance on the last line of each day.
        is_last_of_day = (
            position + 1 >= len(visible)
            or visible[position + 1]["date"] != event["date"]
        )

        if is_last_of_day:
            line["closing_quantity"] = balance.quantity
            line["closing_value"] = _round(
                balance.value(
                    balance.quantity + sum(remaining.values())
                )
            )

        lines.append(line)

    # Roll the pending documents into the running balance (and the
    # Inwards / Outwards totals) now that the voucher lines are done.
    for side, label in (
        ("sale", SALE_PENDING_LABEL),
        ("purchase", PURCHASE_PENDING_LABEL),
    ):
        items = pending[side]

        if not items:
            continue

        column = "out" if side == "sale" else "in"
        quantity = value = 0.0
        children = {}

        for event, (_s, col, qty, val) in items:
            signed = qty if col == column else -qty
            quantity += signed
            value += val if col == column else -val

            row = event["row"]
            key = _tracking(row) or "-"

            child = children.setdefault(
                key,
                {
                    "date": event["date"],
                    "party": row.get("party"),
                    "tracking_number": row.get("tracking_number")
                    or row.get("voucher_number"),
                    "quantity": 0.0,
                    "_primary": False,
                },
            )

            primary = side == "sale" and _SALE_PENDING in _vtype(row) or (
                side == "purchase" and _PURCHASE_PENDING in _vtype(row)
            )

            if primary and not child["_primary"]:
                child.update(
                    date=event["date"],
                    party=row.get("party"),
                    tracking_number=row.get("tracking_number")
                    or row.get("voucher_number"),
                    _primary=True,
                )

            child["quantity"] += signed

        remaining[side] = 0.0

        # Nothing left pending (everything was billed or returned):
        # Tally prints no line.
        if abs(quantity) < 1e-9 and abs(value) < 1e-9:
            continue

        # The net pending quantity moves the balance once.
        balance.apply(column, quantity, value)

        line = {
            "kind": "pending",
            "date": last_iso,
            "particulars": f"({label})",
            "voucher_type": None,
            "voucher_number": None,
            "inward_quantity": quantity if column == "in" else None,
            "inward_value": _round(value) if column == "in" else None,
            "outward_quantity": quantity if column == "out" else None,
            "outward_value": _round(value) if column == "out" else None,
            "closing_quantity": balance.quantity,
            "closing_value": _round(
                balance.value(balance.quantity + sum(remaining.values()))
            ),
            "pending_side": side,
            "children": [
                {k: v for k, v in c.items() if not k.startswith("_")}
                for c in children.values()
                if abs(c["quantity"]) > 1e-9
            ],
        }

        if column == "in":
            in_qty += quantity
            in_val += value
        else:
            out_qty += quantity
            out_val += value

        lines.append(line)

    # Closing stays on the last line only; earlier pending lines keep
    # the value they were printed with.
    final_quantity = balance.quantity
    final_value = _round(balance.value())

    return {
        "opening": {"quantity": opening_qty, "value": shown_opening_value},
        "rows": lines,
        # Tally counts the opening balance as Inwards in the totals.
        "totals": {
            "inward_quantity": opening_qty + in_qty,
            "inward_value": _round(shown_opening_value + in_val),
            "outward_quantity": out_qty,
            "outward_value": _round(out_val),
            "closing_quantity": final_quantity,
            "closing_value": final_value,
        },
    }


def default_period(rows: list[dict], today: date | None = None) -> tuple[date, date]:
    """
    Financial year (1 Apr - 31 Mar) of the latest stock voucher, or of
    today for an item with no vouchers.
    """
    dates = [r["date"] for r in rows if r.get("date")]
    latest = date.fromisoformat(max(dates)) if dates else (today or date.today())
    start_year = latest.year if latest.month >= 4 else latest.year - 1

    return date(start_year, 4, 1), date(start_year + 1, 3, 31)
