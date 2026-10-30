"""
Turns each report's data (exactly what the page's JSON endpoint returns /
caches) into an export spec for ``app.export.exporter``.

Every function here is pure - data in, spec dict out - so the layout of a
report can be tested without Tally. Figures are never recomputed except
where the page itself computes them (noted inline), so a PDF/Excel export
always shows what the screen shows.
"""

import re
from datetime import date

from app.export.exporter import fmt_date, fmt_qty, to_date

NBSP4 = "\u00a0\u00a0\u00a0\u00a0"
_MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
           "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]


# ----------------------------------------------------------------------
# small helpers
# ----------------------------------------------------------------------

def col(key, label, kind="text", blank_zero=False):
    column = {"key": key, "label": label, "type": kind}
    if blank_zero:
        column["blank_zero"] = True
    return column


def strip_tally_prefix(name) -> str:
    return re.sub(r"^(add:|less:)\s*", "", name or "", flags=re.I).strip()


def month_label(key) -> str:
    """'2025-04' -> 'Apr-2025' (same as the app's formatMonthKey)."""
    match = re.match(r"^(\d{4})-(\d{2})$", str(key or ""))
    if not match:
        return str(key or "")
    year, month = int(match.group(1)), int(match.group(2))
    if not 1 <= month <= 12:
        return str(key)
    return f"{_MONTHS[month - 1]}-{year}"


def period_label(from_date=None, to_date=None, as_on=None):
    def one(d):
        parsed = to_date_value(d)
        return fmt_date(parsed) if parsed else str(d)

    if as_on:
        return f"as on {one(as_on)}"
    if from_date and to_date:
        return f"{one(from_date)} to {one(to_date)}"
    if to_date:
        return f"as on {one(to_date)}"
    return None


def to_date_value(value):
    return value if isinstance(value, date) else to_date(value)


def _num(value, default=0.0):
    try:
        if value is None or value == "":
            return default
        return float(value)
    except (TypeError, ValueError):
        return default


def spec(title, company, sections, period=None, meta=None, notes=None):
    return {
        "title": title,
        "company_name": company,
        "period": period,
        "meta": meta or [],
        "sections": sections,
        "notes": notes or [],
    }


# ----------------------------------------------------------------------
# Financial statements
# ----------------------------------------------------------------------

def profit_loss_spec(report, company, period):
    report = report if isinstance(report, dict) else {}
    left = report.get("left", []) or []
    right = report.get("right", []) or []
    rows = []

    for i in range(max(len(left), len(right))):
        l = left[i] if i < len(left) else None
        r = right[i] if i < len(right) else None
        styles = {}
        if l and l.get("is_group"):
            styles.update(left_name="bold", left_amount="bold")
        if r and r.get("is_group"):
            styles.update(right_name="bold", right_amount="bold")
        rows.append({
            "left_name": strip_tally_prefix(l.get("name")) if l else "",
            "left_amount": l.get("amount") if l else None,
            "right_name": strip_tally_prefix(r.get("name")) if r else "",
            "right_amount": r.get("amount") if r else None,
            "_cell_styles": styles,
        })

    total_left = report.get("total_left")
    total_right = report.get("total_right")
    if total_left is None:
        total_left = sum(_num(x.get("amount")) for x in left)
    if total_right is None:
        total_right = sum(_num(x.get("amount")) for x in right)

    columns = [
        col("left_name", "Particulars"), col("left_amount", "Amount", "amount"),
        col("right_name", "Particulars"), col("right_amount", "Amount", "amount"),
    ]
    totals = [{"left_name": "Total", "left_amount": total_left,
               "right_name": "Total", "right_amount": total_right}]
    return spec("Profit & Loss", company,
                [{"columns": columns, "rows": rows, "totals": totals}], period=period)


def _flatten_bs(lines):
    flat = []
    for line in lines or []:
        flat.append((line.get("name"), line.get("amount"), False))
        for child in line.get("children", []) or []:
            flat.append((child.get("name"), child.get("amount"), True))
    return flat


def balance_sheet_spec(report, company, period):
    left = _flatten_bs(report.get("liabilities"))
    right = _flatten_bs(report.get("assets"))
    rows = []

    for i in range(max(len(left), len(right))):
        l = left[i] if i < len(left) else ("", None, False)
        r = right[i] if i < len(right) else ("", None, False)
        styles = {}
        for side, item in (("left", l), ("right", r)):
            if item[0]:
                styles[f"{side}_name"] = "italic" if item[2] else "bold"
                styles[f"{side}_amount"] = "italic" if item[2] else "bold"
        rows.append({
            "left_name": (NBSP4 + l[0]) if l[2] else l[0],
            "left_amount": l[1],
            "right_name": (NBSP4 + r[0]) if r[2] else r[0],
            "right_amount": r[1],
            "_cell_styles": styles,
        })

    columns = [
        col("left_name", "Liabilities"), col("left_amount", "Amount", "amount", True),
        col("right_name", "Assets"), col("right_amount", "Amount", "amount", True),
    ]
    totals = [{"left_name": "Total", "left_amount": report.get("total_liabilities", 0),
               "right_name": "Total", "right_amount": report.get("total_assets", 0)}]

    meta = []
    difference = _num(report.get("difference"))
    if round(difference, 2) != 0:
        meta.append(("Difference in opening balances", f"{difference:,.2f}"))

    return spec("Balance Sheet", company,
                [{"columns": columns, "rows": rows, "totals": totals}],
                period=period, meta=meta)


def trial_balance_spec(rows, company, period):
    # Tally's footer adds the magnitude of every row, not the signed value.
    total_debit = sum(abs(_num(r.get("debit"))) for r in rows)
    total_credit = sum(abs(_num(r.get("credit"))) for r in rows)
    columns = [col("name", "Ledger"), col("debit", "Debit", "amount", True),
               col("credit", "Credit", "amount", True)]
    return spec("Trial Balance", company, [{
        "columns": columns,
        "rows": rows,
        "totals": [{"name": "Total", "debit": total_debit, "credit": total_credit}],
        "filterable": True,
    }], period=period)


def group_summary_spec(data, group, company, period):
    rows = []
    for r in data.get("report", []):
        row = {**r}
        debit = _num(row.get("debit"))
        credit = _num(row.get("credit"))
        diff = debit - credit
        if abs(diff) >= 0.005:
            row["closing_balance"] = f"{abs(diff):,.2f} {'Dr' if diff > 0 else 'Cr'}"
        else:
            if debit > 0:
                row["closing_balance"] = f"{debit:,.2f} Dr"
            elif credit > 0:
                row["closing_balance"] = f"{credit:,.2f} Cr"
            else:
                row["closing_balance"] = "-"
        rows.append(row)

    total_debit = data.get("total_debit", 0)
    total_credit = data.get("total_credit", 0)
    total_diff = _num(total_debit) - _num(total_credit)
    total_closing = f"{abs(total_diff):,.2f} {'Dr' if total_diff > 0 else 'Cr'}" if abs(total_diff) >= 0.005 else "-"

    columns = [
        col("name", "Particulars"),
        col("debit", "Debit", "amount", True),
        col("credit", "Credit", "amount", True),
        col("closing_balance", "Closing Balance", "balance"),
    ]
    return spec(f"Group Summary: {group}", company, [{
        "columns": columns,
        "rows": rows,
        "totals": [{"name": "Total",
                    "debit": total_debit,
                    "credit": total_credit,
                    "closing_balance": total_closing}],
        "filterable": True,
    }], period=period, meta=[("Group", group)])


# ----------------------------------------------------------------------
# Ledger
# ----------------------------------------------------------------------

def ledger_spec(report, ledger_name, company, period, view="monthly"):
    """view: "monthly" (Monthly Summary), "detailed" (vouchers) or "both"."""
    opening = _num(report.get("opening_balance"))
    entries = report.get("entries", []) or []

    opening_row = {
        "date": None, "particulars": "Opening Balance",
        "voucher_type": "", "voucher_number": "",
        "debit": opening if opening > 0 else 0,
        "credit": abs(opening) if opening < 0 else 0,
        "running_balance": opening, "_style": "bold",
    }
    total_debit = report.get("total_debit")
    total_credit = report.get("total_credit")
    if total_debit is None:
        total_debit = sum(_num(e.get("debit")) for e in entries)
    if total_credit is None:
        total_credit = sum(_num(e.get("credit")) for e in entries)

    detail_columns = [
        col("date", "Date", "date"), col("particulars", "Particulars"),
        col("voucher_type", "Vch Type"), col("voucher_number", "Vch No."),
        col("debit", "Debit", "amount", True), col("credit", "Credit", "amount", True),
        col("running_balance", "Balance", "balance"),
    ]
    sections = []
    if view in ("detailed", "both"):
        sections.append({
        "sheet": "Vouchers", "heading": "Ledger Vouchers",
        "columns": detail_columns,
        "rows": [opening_row] + entries,
        "totals": [{"particulars": "Total", "debit": total_debit,
                    "credit": total_credit,
                    "running_balance": report.get("closing_balance")}],
        "filterable": True,
        })

    summary = report.get("monthly_summary")
    summary = summary if isinstance(summary, dict) else {}
    if view in ("monthly", "both"):
        month_rows = [{
            "month": "Opening Balance",
            "debit": opening if opening > 0 else 0,
            "credit": abs(opening) if opening < 0 else 0,
            "closing_balance": opening, "_style": "bold",
        }]
        for key in sorted(summary):
            bucket = summary[key] or {}
            month_rows.append({
                "month": bucket.get("month") or month_label(key),
                "debit": bucket.get("debit"),
                "credit": bucket.get("credit"),
                "closing_balance": bucket.get("closing_balance"),
            })
        sections.append({
            "sheet": "Monthly Summary", "heading": "Monthly Summary",
            "columns": [col("month", "Particulars"),
                        col("debit", "Debit", "amount", True),
                        col("credit", "Credit", "amount", True),
                        col("closing_balance", "Closing Balance", "balance")],
            "rows": month_rows,
            "totals": [{"month": "Total", "debit": total_debit, "credit": total_credit,
                        "closing_balance": report.get("closing_balance")}],
        })

    meta = [
        ("Ledger", report.get("ledger_name") or ledger_name),
        ("Opening Balance", _balance_text(opening)),
        ("Closing Balance", _balance_text(report.get("closing_balance"))),
        ("Entries", report.get("entry_count", len(entries))),
    ]
    title = {
        "monthly": f"Ledger Monthly Summary: {ledger_name}",
        "detailed": f"Ledger Vouchers: {ledger_name}",
    }.get(view, f"Ledger: {ledger_name}")
    return spec(title, company, sections, period=period, meta=meta)


def _balance_text(value):
    if value is None:
        return None
    number = _num(value)
    if round(number, 2) == 0:
        return "0.00"
    from app.export.exporter import fmt_amount
    return f"{fmt_amount(abs(number))} {'Cr' if number < 0 else 'Dr'}"


# ----------------------------------------------------------------------
# Bills
# ----------------------------------------------------------------------

def bills_spec(title, bills, total_label, total, company, with_type=False):
    columns = []
    if with_type:
        columns.append(col("type_label", "Type"))
    columns += [
        col("party", "Party"), col("bill_reference", "Bill Reference"),
        col("bill_date", "Bill Date", "date"), col("due_date", "Due Date", "date"),
        col("overdue_days", "Overdue Days", "int"),
        col("original_voucher_number", "Voucher No."),
        col("outstanding_amount", "Outstanding", "amount"),
    ]
    rows = []
    for bill in bills or []:
        row = dict(bill)
        row["type_label"] = str(bill.get("type") or "").capitalize()
        rows.append(row)

    if total is None:
        total = sum(_num(b.get("outstanding_amount")) for b in rows)

    first_key = columns[0]["key"]
    totals = [{first_key: total_label, "outstanding_amount": total}]
    return spec(title, company, [{
        "columns": columns, "rows": rows, "totals": totals, "filterable": True,
    }], meta=[("Total Outstanding", _fmt(total)), ("Bills", len(rows))])


def _fmt(value):
    from app.export.exporter import fmt_amount
    return fmt_amount(value)


# ----------------------------------------------------------------------
# Stock
# ----------------------------------------------------------------------

def stock_summary_spec(rows, title, company, period, view="full"):
    cols = [col("stock_item", "Stock Item"), col("stock_group", "Stock Group"),
            col("unit", "Unit")]
    opening = [col("opening_quantity", "Opening Qty", "qty"),
               col("opening_value", "Opening Value", "amount")]
    closing = [col("closing_quantity", "Closing Qty", "qty"),
               col("closing_rate", "Closing Rate", "amount"),
               col("closing_value", "Closing Value", "amount")]

    if view == "opening":
        cols += opening
    elif view == "closing":
        cols += closing
    else:
        cols += opening + closing

    totals_row = {"stock_item": "Total"}
    if view in ("opening", "full"):
        totals_row["opening_value"] = sum(_num(r.get("opening_value")) for r in rows)
    if view in ("closing", "full"):
        totals_row["closing_value"] = sum(_num(r.get("closing_value")) for r in rows)

    return spec(title, company, [{
        "columns": cols, "rows": rows, "totals": [totals_row], "filterable": True,
    }], period=period)


def trial_balance_opening_stock_spec(rows, company, period):
    """rows: already computed exactly as TrialBalanceOpeningStock.jsx does."""
    units = {r.get("unit") for r in rows}
    totals = {"stock_item": "Total", "value": sum(_num(r["value"]) for r in rows)}
    if len(units) == 1:
        totals["quantity"] = sum(_num(r["quantity"]) for r in rows)
    columns = [col("stock_item", "Particulars"), col("unit", "Unit"),
               col("quantity", "Quantity", "qty"), col("rate", "Rate", "amount"),
               col("value", "Value", "amount")]
    return spec("Opening Stock Summary", company, [{
        "columns": columns, "rows": rows, "totals": [totals], "filterable": True,
    }], period=period)


def purchase_bills_pending_spec(data, company, period):
    columns = [
        col("date", "Date", "date"), col("tracking_number", "Tracking Number"),
        col("stock_item", "Name of Item"), col("party", "From"),
        col("initial_quantity", "Initial Quantity", "qty"),
        col("pending_quantity", "Pending Quantity", "qty"),
        col("rate", "Rate", "amount"), col("value", "Value", "amount"),
    ]
    return spec("Purchase Bills Pending", company, [{
        "heading": "Goods Recd. but Bills not Recd.",
        "columns": columns, "rows": data.get("report", []),
        "totals": [{"date": "Total", "value": data.get("total_value", 0)}],
        "filterable": True,
    }], period=period)


def master_list_spec(title, columns, rows, company, name_key):
    """Stock group / category / godown lists. Tally's implicit 'Primary'
    root is shown in bold, like the page's diamond marker."""
    prepared = []
    for row in rows:
        row = dict(row)
        if row.get("is_primary"):
            row["_style"] = "bold"
        if "is_internal" in row:
            row["is_internal"] = "" if row.get("is_primary") else (
                "Yes" if row.get("is_internal") else "No")
        prepared.append(row)
    return spec(title, company, [{"columns": columns, "rows": prepared, "filterable": True}])


def summary_drill_spec(title, selected, response, company, period):
    """Stock Group / Category / Godown Summary tree."""
    rows = []
    for r in response.get("report", []):
        is_item = r.get("kind") == "item"
        rows.append({
            "name": r.get("name") if is_item else f"{r.get('name')}  >",
            "closing_quantity": r.get("closing_quantity"),
            "unit": r.get("unit"),
            "closing_rate": r.get("closing_rate") or None,
            "closing_value": r.get("closing_value"),
            "_style": "" if is_item else "bold",
        })
    totals = response.get("totals") or {}
    columns = [col("name", "Particulars"), col("closing_quantity", "Closing Quantity", "qty"),
               col("unit", "Unit"), col("closing_rate", "Rate", "amount"),
               col("closing_value", "Value", "amount")]
    total_row = {"name": "Grand Total", "closing_quantity": totals.get("closing_quantity"),
                 "unit": totals.get("unit"), "closing_value": totals.get("closing_value")}
    return spec(f"{title}: {selected}", company, [{
        "columns": columns, "rows": rows, "totals": [total_row],
    }], period=period)


def stock_item_monthly_spec(response, item, godown, company, period):
    unit = response.get("unit") or ""
    suffix = f" ({unit})" if unit else ""
    months = response.get("report", []) or []
    opening = response.get("opening") or {}

    def total(key):
        return sum(_num(m.get(key)) for m in months)

    rows = [{"month": "Opening Balance", "closing_quantity": opening.get("quantity"),
             "closing_value": opening.get("value"), "_style": "bold"}]
    for m in months:
        rows.append({**m, "month": month_label(m.get("month"))})

    last = months[-1] if months else {}
    totals = [{
        "month": "Grand Total",
        "inward_quantity": total("inward_quantity"), "inward_value": total("inward_value"),
        "outward_quantity": total("outward_quantity"), "outward_value": total("outward_value"),
        "closing_quantity": last.get("closing_quantity"),
        "closing_value": last.get("closing_value"),
    }]
    columns = [
        col("month", "Particulars"),
        col("inward_quantity", f"Inwards Qty{suffix}", "qty", True),
        col("inward_value", "Inwards Value", "amount", True),
        col("outward_quantity", f"Outwards Qty{suffix}", "qty", True),
        col("outward_value", "Outwards Value", "amount", True),
        col("closing_quantity", f"Closing Qty{suffix}", "qty", True),
        col("closing_value", "Closing Value", "amount", True),
    ]
    title = (f"Godown Monthly Summary: {godown}" if godown else "Stock Item Monthly Summary")
    meta = [("Stock Item", item)]
    if godown:
        meta.append(("Godown", godown))
    notes = []
    if response.get("approximate"):
        notes.append("This item is held in more than one godown, so this godown's closing "
                     "figures are worked out from its opening allocation and vouchers at "
                     "Tally's closing rate.")
    return spec(title, company, [{"columns": columns, "rows": rows, "totals": totals}],
                period=period, meta=meta, notes=notes)


def stock_item_vouchers_spec(response, item, godown, company, period):
    unit = response.get("unit") or ""
    suffix = f" ({unit})" if unit else ""
    opening = response.get("opening") or {}
    rows = [{
        "date": response.get("from"), "particulars": "Opening Balance",
        "inward_quantity": opening.get("quantity"), "inward_value": opening.get("value"),
        "closing_quantity": opening.get("quantity"), "closing_value": opening.get("value"),
        "_style": "bold",
    }]
    for line in response.get("report", []) or []:
        if line.get("kind") == "pending":
            rows.append({**line, "inward_value": None, "outward_value": None,
                         "_style": "bold"})
            for child in line.get("children", []) or []:
                detail = "   ".join(
                    x for x in (child.get("tracking_number"),
                                fmt_qty(child.get("quantity"))
                                if child.get("quantity") is not None else "") if x)
                rows.append({"date": child.get("date"), "particulars": child.get("party"),
                             "voucher_type": detail, "_style": "italic", "_indent": 1})
        else:
            rows.append(dict(line))

    totals = response.get("totals") or {}
    total_row = {**totals, "date": None, "particulars": "Totals"}

    columns = [
        col("date", "Date", "date"), col("particulars", "Particulars"),
        col("voucher_type", "Vch Type"), col("voucher_number", "Vch No."),
        col("inward_quantity", f"Inwards Qty{suffix}", "qty", True),
        col("inward_value", "Inwards Value", "amount", True),
        col("outward_quantity", f"Outwards Qty{suffix}", "qty", True),
        col("outward_value", "Outwards Value", "amount", True),
        col("closing_quantity", f"Closing Qty{suffix}", "qty", True),
        col("closing_value", "Closing Value", "amount", True),
    ]
    meta = [("Stock Item", item)]
    if godown:
        meta.append(("Godown", godown))
    title = f"Godown Vouchers: {godown}" if godown else "Stock Item Vouchers"
    return spec(title, company, [{"columns": columns, "rows": rows, "totals": [total_row]}],
                period=period, meta=meta)


def stock_item_bills_pending_spec(result, item, company, period):
    unit = ""
    rows = result.get("report") or result.get("rows") or []
    details = result.get("details") or []
    out = []
    for bill in rows:
        out.append({
            **bill,
            "rate": bill.get("rate") or None,
            "value": bill.get("value") if bill.get("rate") else None,
            "_style": "bold",
        })
        for note in details:
            if (note.get("tracking_number") or "") == (bill.get("tracking_number") or ""):
                out.append({
                    "date": note.get("date"),
                    "tracking_number": f"{note.get('voucher_type') or ''} {note.get('voucher_number') or ''}".strip(),
                    "initial_quantity": abs(_num(note.get("quantity"))),
                    "rate": note.get("rate") or None,
                    "_style": "italic", "_indent": 1,
                })
    columns = [
        col("date", "Date", "date"), col("tracking_number", "Tracking Number"),
        col("party", "Name of Party"),
        col("initial_quantity", "Initial Quantity", "qty"),
        col("pending_quantity", "Pending Quantity", "qty"),
        col("rate", "Rate (Disc %)", "amount"), col("value", "Value", "amount"),
    ]
    totals = [{
        "date": "Total",
        "initial_quantity": sum(_num(r.get("initial_quantity")) for r in rows),
        "pending_quantity": sum(_num(r.get("pending_quantity")) for r in rows),
    }]
    return spec("Sales Bills Pending", company, [{
        "heading": "Bills Made but Goods not Delivered",
        "columns": columns, "rows": out, "totals": totals,
    }], period=period, meta=[("Stock Item", item)])


# ----------------------------------------------------------------------
# Registers
# ----------------------------------------------------------------------

def register_months_spec(title, result, company, period):
    columns = [col("month", "Particulars"), col("total_vouchers", "Total Vouchers", "int"),
               col("cancelled_vouchers", "(cancelled)", "int", True)]
    totals = [{"month": "Grand Total", "total_vouchers": result.get("grand_total", 0),
               "cancelled_vouchers": result.get("grand_total_cancelled", 0)}]
    return spec(title, company, [{"columns": columns, "rows": result.get("rows", result.get("report", [])),
                                  "totals": totals}], period=period)


def register_vouchers_spec(response, company, period):
    is_order = response.get("kind") == "order"
    rows = []
    for r in response.get("report", []) or []:
        particulars = str(r.get("particulars") or "")
        if r.get("is_cancelled"):
            particulars += " (cancelled)"
        if r.get("is_optional"):
            particulars += " (optional)"
        rows.append({**r, "particulars": particulars})

    columns = [col("date", "Date", "date"), col("particulars", "Particulars"),
               col("voucher_type", "Vch Type"), col("voucher_number", "Vch No.")]
    totals_src = response.get("totals") or {}
    if is_order:
        columns += [col("order_ref_no", "Order Ref No"),
                    col("order_amount", "Order Amount", "amount")]
        total_row = {"date": "Total", "order_amount": totals_src.get("order_amount")}
    else:
        columns += [col("inward_quantity", "Inwards Qty", "qty", True),
                    col("outward_quantity", "Outwards Qty", "qty", True),
                    col("unit", "Unit")]
        total_row = {"date": "Total",
                     "inward_quantity": totals_src.get("inward_quantity"),
                     "outward_quantity": totals_src.get("outward_quantity")}
    title = f"List of All {response.get('voucher_type') or ''} Vouchers".replace("  ", " ")
    return spec(title, company, [{"columns": columns, "rows": rows, "totals": [total_row],
                                  "filterable": True}], period=period,
                meta=[("Register", response.get("report_name"))])


# ----------------------------------------------------------------------
# Vouchers
# ----------------------------------------------------------------------

_WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]


def _date_with_weekday(value):
    parsed = to_date_value(value)
    if not parsed:
        return str(value or "")
    return f"{fmt_date(parsed)} ({_WEEKDAYS[parsed.weekday()]})"


def voucher_spec(voucher, company):
    entries = voucher.get("entries", []) or []
    items = voucher.get("items", []) or []
    layout = voucher.get("layout") or "single_entry"
    is_invoice = layout == "invoice" or bool(voucher.get("is_invoice"))

    if voucher.get("base_type") in ("purchase", "debit_note") and is_invoice:
        reference_label = "Supplier Invoice No."
    elif is_invoice:
        reference_label = "Reference No."
    else:
        reference_label = "Reference"

    top = next((e for e in entries if e.get("role") in ("account", "party")), None)
    meta = [
        ("Voucher Type", voucher.get("voucher_type")),
        ("Voucher No.", voucher.get("voucher_number")),
        ("Date", _date_with_weekday(voucher.get("date"))),
    ]
    if voucher.get("reference_number"):
        meta.append((reference_label, voucher["reference_number"]))
        if voucher.get("reference_date"):
            meta.append(("Invoice Date" if is_invoice else "Reference Date",
                         fmt_date(voucher["reference_date"])))
    if top:
        meta.append(("Party A/c name" if is_invoice else "Account", top.get("ledger_name")))
    if voucher.get("is_cancelled"):
        meta.append(("Status", "Cancelled"))
    if voucher.get("narration"):
        meta.append(("Narration", voucher["narration"]))

    sections = []
    if is_invoice and items:
        sections.append({
            "heading": "Items",
            "columns": [col("name", "Name of Item"), col("quantity", "Quantity"),
                        col("rate", "Rate", "amount"), col("unit", "per"),
                        col("amount", "Amount", "amount")],
            "rows": items,
        })

    show_rate = any(e.get("rate") is not None for e in entries)
    columns = [col("ledger_name", "Particulars"), col("side", "Dr / Cr"),
               col("debit", "Debit", "amount", True), col("credit", "Credit", "amount", True)]
    if show_rate:
        columns.insert(2, col("rate", "Rate", "percent"))

    rows = []
    for e in entries:
        debit, credit = _num(e.get("debit")), _num(e.get("credit"))
        rows.append({**e, "side": e.get("side") or ("Dr" if debit else "Cr"),
                     "debit": debit, "credit": credit,
                     "_style": "bold" if e is top else ""})
        for bill in e.get("bill_allocations") or []:
            side = bill.get("side") or ""
            amount = _num(bill.get("amount"))
            rows.append({
                "ledger_name": f"{bill.get('bill_type') or 'Ref'}  {bill.get('name') or ''}",
                "side": side,
                "debit": amount if side == "Dr" else 0,
                "credit": amount if side == "Cr" else 0,
                "_style": "muted", "_indent": 1,
            })

    sections.append({
        "heading": "Particulars", "columns": columns, "rows": rows,
        "totals": [{"ledger_name": "Total", "debit": voucher.get("total_debit"),
                    "credit": voucher.get("total_credit")}],
    })
    title = f"{voucher.get('voucher_type') or 'Voucher'} Voucher"
    return spec(title, company, sections, meta=meta)


def inventory_voucher_spec(voucher, company):
    voucher = voucher or {}
    entries = voucher.get("entries", []) or []
    transfer = bool(voucher.get("is_transfer"))

    meta = [
        ("Voucher Type", voucher.get("voucher_type")),
        ("Voucher No.", voucher.get("voucher_number")),
        ("Date", _date_with_weekday(voucher.get("date"))),
        ("Party A/c name", voucher.get("party")),
        ("Reference No.", voucher.get("reference")),
        ("Reference Date", fmt_date(voucher.get("reference_date"))
         if voucher.get("reference_date") else None),
    ]
    if voucher.get("is_cancelled"):
        meta.append(("Status", "Cancelled"))
    if voucher.get("is_optional"):
        meta.append(("Status", "Optional"))
    for detail in voucher.get("details") or []:
        meta.append((detail.get("label"), detail.get("value")))
    if voucher.get("narration"):
        meta.append(("Narration", voucher["narration"]))

    def qty_text(entry):
        return entry.get("billed_quantity") or entry.get("actual_quantity") or ""

    rows = []
    for e in entries:
        name = e.get("stock_item") or ""
        if e.get("tracking_number"):
            name += f"\nTracking No.: {e['tracking_number']}"
        rows.append({
            "role": str(e.get("role") or "").replace("_", " ").title(),
            "stock_item": name,
            "batch": "" if str(e.get("batch") or "").strip().lower() == "primary batch"
            else e.get("batch"),
            "actual_quantity": e.get("actual_quantity") or "",
            "billed_quantity": e.get("billed_quantity") or "",
            "quantity": qty_text(e),
            "rate": abs(_num(e.get("rate_value"))) if e.get("rate_value") is not None else None,
            "unit": e.get("unit") or "",
            "amount": e.get("amount_value") if e.get("amount_value") else None,
        })

    different = any(
        e.get("billed_quantity") and e.get("actual_quantity")
        and e.get("billed_quantity") != e.get("actual_quantity") for e in entries)
    columns = []
    if transfer:
        columns.append(col("role", "Entry"))
    columns.append(col("stock_item", "Name of Item"))
    if any(r["batch"] for r in rows):
        columns.append(col("batch", "Batch/Lot No."))
    if different:
        columns += [col("actual_quantity", "Actual Qty"), col("billed_quantity", "Billed Qty")]
    else:
        columns.append(col("quantity", "Quantity"))
    columns += [col("rate", "Rate", "amount"), col("unit", "per"), col("amount", "Amount", "amount")]

    totals = []
    all_total = (voucher.get("totals") or {}).get("all")
    if all_total:
        qty = all_total.get("quantity")
        unit = all_total.get("unit") or ""
        totals.append({
            "stock_item": "Total",
            "quantity": f"{fmt_qty(qty)} {unit}".strip() if qty is not None else "",
            "amount": all_total.get("amount") or None,
        })

    sections = [{"heading": "Inventory Entries", "columns": columns, "rows": rows,
                 "totals": totals}]

    ledgers = [l for l in (voucher.get("ledger_entries") or []) if not l.get("is_party")]
    if ledgers:
        sections.append({
            "heading": f"{voucher.get('ledger_label') or ''} Ledger".strip(),
            "columns": [col("ledger", "Ledger"), col("balance_text", "Current Balance")],
            "rows": [{"ledger": l.get("ledger"),
                      "balance_text": _balance_dict_text(l.get("balance"))} for l in ledgers],
        })
    title = f"{voucher.get('voucher_type') or 'Inventory'} Voucher"
    return spec(title, company, sections, meta=[m for m in meta if m[1] not in (None, "")])


def _balance_dict_text(balance):
    if isinstance(balance, dict):
        amount = balance.get("amount", balance.get("value"))
        kind = balance.get("type") or balance.get("side") or ""
        return f"{_fmt(amount)} {kind}".strip() if amount is not None else ""
    return "" if balance is None else str(balance)


# ----------------------------------------------------------------------
# Plain lists
# ----------------------------------------------------------------------

def ledger_list_spec(ledgers, company):
    columns = [col("name", "Ledger"), col("parent", "Group")]
    return spec("List of Ledgers", company, [{
        "columns": columns,
        "rows": sorted(ledgers, key=lambda l: ((l.get("parent") or ""), (l.get("name") or ""))),
        "filterable": True,
    }], meta=[("Ledgers", len(ledgers))])


def bill_allocations_spec(bills, company):
    columns = [col("date", "Date", "date"), col("party_ledger_name", "Party Ledger"),
               col("party_name", "Party"), col("voucher_type", "Voucher Type"),
               col("voucher_number", "Voucher No."), col("reference", "Reference"),
               col("narration", "Narration")]
    return spec("Purchase Bill", company, [{"columns": columns, "rows": bills,
                                            "filterable": True}])


# ----------------------------------------------------------------------
# Dashboard
# ----------------------------------------------------------------------

def dashboard_spec(summary, monthly, company, period):
    summary = summary or {}
    sections = []

    key_rows = []
    for label, key in (
        ("Total sales", "total_sales"), ("Total purchases", "total_purchases"),
        ("Net profit", "net_profit"), ("Net loss", "net_loss"),
        ("Receivables", "receivables"), ("Payables", "payables"),
        ("Cash in hand", "cash_in_hand"), ("Bank balance", "bank_balance"),
        ("GST payable", "gst_payable"), ("TDS payable", "tds_payable"),
    ):
        value = summary.get(key)
        source = (summary.get("metric_sources") or {}).get(key) or {}
        key_rows.append({
            "metric": label, "value": value,
            "note": "" if value is not None else (source.get("message") or "Not available from Tally"),
        })
    sections.append({
        "sheet": "Overview", "heading": "Key Figures",
        "columns": [col("metric", "Metric"), col("value", "Value", "amount"),
                    col("note", "Note")],
        "rows": key_rows,
    })

    accounts = summary.get("cash_bank_accounts") or []
    if accounts:
        sections.append({
            "sheet": "Overview", "heading": "Cash & Bank",
            "columns": [col("name", "Account"), col("category", "Type"),
                        col("balance", "Closing Balance", "balance")],
            "rows": sorted(accounts, key=lambda a: -abs(_num(a.get("balance")))),
        })

    for title, key in (("Sales Breakdown", "sales_breakdown"),
                       ("Expense Breakdown", "expense_breakdown")):
        rows = summary.get(key) or []
        if rows:
            sections.append({
                "sheet": "Overview", "heading": title,
                "columns": [col("label", "Particulars"), col("value", "Amount", "amount")],
                "rows": rows,
            })

    series = ((monthly or {}).get("income_vs_expense")) or []
    if series:
        sections.append({
            "sheet": "Monthly Trend", "heading": "Sales vs Purchases by Month",
            "columns": [col("month", "Month"), col("income", "Sales", "amount"),
                        col("expense", "Purchases", "amount"), col("status", "Status")],
            "rows": series,
        })

    for name, label, party in (("receivables", "Receivables", "Customer"),
                               ("payables", "Payables", "Supplier")):
        ageing = summary.get(f"{name}_ageing")
        if ageing:
            sections.append({
                "sheet": label, "heading": f"{label} Ageing",
                "columns": [col("label", "Age"), col("count", "Bills", "int"),
                            col("amount", "Amount", "amount")],
                "rows": ageing,
                "totals": [{"label": "Total",
                            "count": sum(int(b.get("count") or 0) for b in ageing),
                            "amount": sum(_num(b.get("amount")) for b in ageing)}],
            })
        top = summary.get(f"top_{name}")
        if top:
            sections.append({
                "sheet": label, "heading": f"Top {label}",
                "columns": [col("party", party), col("reference", "Reference"),
                            col("due_date", "Due Date", "date"),
                            col("days_overdue", "Days Overdue", "int"),
                            col("amount", "Amount", "amount")],
                "rows": top, "filterable": True,
            })

    meta = [("Fetched at", summary.get("fetched_at"))]
    return spec("Dashboard Summary", company, sections, period=period, meta=meta)
