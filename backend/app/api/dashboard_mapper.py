"""Map Tally report data into the dashboard response."""

from datetime import date

from app.tally.dashboard import html_amount, previous_period


UNAVAILABLE = (
    "Direct authoritative Tally value not currently available "
    "through the verified request."
)


def exact_row(rows, *names):
    """Return a row only when there is one exact matching label."""
    names = {name.casefold() for name in names}

    matches = [
        row
        for row in rows or []
        if (
            row.get("reserved_name")
            or row.get("name")
            or ""
        ).casefold() in names
    ]

    return matches[0] if len(matches) == 1 else None


def purchase_row(rows):
    """Find the Purchase Accounts row returned by Tally."""
    return (
        exact_row(rows, "Add: Purchase Accounts")
        or exact_row(rows, "Purchase Accounts")
    )


def _day(iso):
    """2025-04-01 -> 1-Apr-2025, for messages."""
    try:
        return date.fromisoformat(iso).strftime("%-d-%b-%Y")
    except (TypeError, ValueError):
        return iso


def verified_period(native_pl, start, end, company):
    """
    Whether Tally's native P&L states the requested company and period.

    Tally silently substitutes a different period when it cannot use
    the requested dates (TallyPrime Educational mode, for example, only
    accepts the 1st, 2nd and 31st), and its XML export does not say so.
    Only the HTML report names the period, so every P&L figure is
    checked against it.
    """
    return (
        native_pl.get("from_date") == start.isoformat()
        and native_pl.get("to_date") == end.isoformat()
        and any(company in row for row in native_pl.get("rows", []))
    )


def period_mismatch_reason(native_pl):
    if native_pl.get("from_date") and native_pl.get("to_date"):
        return (
            f"Tally reported {_day(native_pl['from_date'])} to "
            f"{_day(native_pl['to_date'])} instead of the selected period, "
            "so its figures are not shown for these dates."
        )
    return (
        "Tally did not confirm the period of its Profit & Loss, "
        "so its figures are not shown for these dates."
    )


AGEING_BUCKETS = (
    ("not_due", "Not yet due"),
    ("1_30", "1–30 days"),
    ("31_60", "31–60 days"),
    ("61_90", "61–90 days"),
    ("over_90", "Over 90 days"),
)


def ageing(bills):
    """
    Pending bills grouped by how many days overdue Tally reports them.

    Tally leaves Overdue blank until a bill is past due, so a blank
    counts as not yet due. The bucket amounts are sums of Tally's own
    per-bill pending amounts; the report total stays Tally's footer.
    """
    buckets = [
        {"key": key, "label": label, "amount": 0.0, "count": 0}
        for key, label in AGEING_BUCKETS
    ]

    for bill in bills:
        if bill.get("amount") is None:
            continue

        days = bill.get("days_overdue") or 0
        index = (
            0 if days <= 0
            else 1 if days <= 30
            else 2 if days <= 60
            else 3 if days <= 90
            else 4
        )

        buckets[index]["amount"] += bill["amount"]
        buckets[index]["count"] += 1

    for bucket in buckets:
        bucket["amount"] = round(bucket["amount"], 2)

    return buckets


def _comparison(reports, start, end, company):
    """P&L headline figures for the period just before the selected one."""
    if "previous_profit_loss_totals" not in reports:
        return None

    previous_start, previous_end = previous_period(start, end)

    previous = map_dashboard_summary(
        {
            "profit_loss": reports.get("previous_profit_loss", []),
            "profit_loss_totals": reports["previous_profit_loss_totals"],
        },
        previous_start,
        previous_end,
        company,
    )

    return {
        "from_date": previous_start.isoformat(),
        "to_date": previous_end.isoformat(),
        "period_verified": previous["period_verified"],
        **{
            key: previous[key]
            for key in ("total_sales", "total_purchases", "net_profit", "net_loss")
        },
    }


def map_dashboard_summary(reports, start, end, company):
    sources = {}

    def metric(key, row, report, *, period=True, reason=None, status=None):
        """
        Store a dashboard value along with its Tally source details.

        status "none" marks a line Tally left out of a report whose
        period it confirmed: Tally omits empty lines, so there were no
        such entries - which is different from not knowing.
        """
        value = row.get("amount") if row else None

        sources[key] = {
            "report": report,
            "label": row.get("name") if row else None,
            "field": row.get("field") if row else None,
            "raw": row.get("raw") if row else None,
            "from_date": start.isoformat() if period else None,
            "to_date": end.isoformat(),
            "status": "available" if value is not None else (status or "unavailable"),
            "message": None if value is not None else (reason or UNAVAILABLE),
        }

        return value

    # Tally's native (HTML) P&L names the period it actually used;
    # every P&L figure below is shown only when that is the selected one.
    native_pl = reports.get("profit_loss_totals", {})
    period_matches = verified_period(native_pl, start, end, company)
    pl_reason = None if period_matches else period_mismatch_reason(native_pl)

    # The XML P&L keeps Tally's signs, so values are read from it.
    pl = reports.get("profit_loss", []) if period_matches else []

    def pl_line(key, row, noun):
        # In a confirmed P&L, a line that is absent or has a blank
        # amount had no entries in the period.
        if period_matches and pl and (row is None or row.get("amount") is None):
            return metric(
                key, row, "Profit and Loss", status="none",
                reason=f"No {noun} entries in Tally for this period.",
            )
        return metric(key, row, "Profit and Loss", reason=pl_reason)

    sales_value = pl_line(
        "total_sales",
        exact_row(pl, "Sales Accounts"),
        "sales",
    )

    purchase_value = pl_line(
        "total_purchases",
        purchase_row(pl),
        "purchase",
    )

    data = {
        "total_sales": sales_value,
        "total_purchases": (
            abs(purchase_value)
            if purchase_value is not None
            else None
        ),
    }

    for key, names in [
        ("net_profit", ("Net Profit", "Nett Profit")),
        ("net_loss", ("Net Loss", "Nett Loss")),
    ]:
        matches = []

        if period_matches:
            for cells in native_pl["rows"]:
                nonempty = [cell for cell in cells if cell]

                if len(nonempty) == 2 and nonempty[0] in names:
                    matches.append({
                        "name": nonempty[0],
                        "amount": html_amount(nonempty[1]),
                        "raw": nonempty[1],
                        "field": "HTML result row",
                    })

        data[key] = metric(
            key,
            matches[0] if len(matches) == 1 else None,
            "Profit and Loss (native HTML)",
            reason=pl_reason,
        )

    # If Tally gives a verified Net Loss, Net Profit is zero.
    # The reverse applies when Tally gives a verified Net Profit.
    if period_matches:
        if (
            data.get("net_loss") is not None
            and data["net_loss"] > 0
            and data.get("net_profit") is None
        ):
            data["net_profit"] = 0.0

            sources["net_profit"] = {
                "report": "Profit and Loss (native HTML)",
                "label": "Net Profit",
                "field": "HTML result row (derived from verified Nett Loss)",
                "raw": "0.00",
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "status": "available",
                "message": None,
            }

        elif (
            data.get("net_profit") is not None
            and data["net_profit"] > 0
            and data.get("net_loss") is None
        ):
            data["net_loss"] = 0.0

            sources["net_loss"] = {
                "report": "Profit and Loss (native HTML)",
                "label": "Net Loss",
                "field": "HTML result row (derived from verified Nett Profit)",
                "raw": "0.00",
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "status": "available",
                "message": None,
            }

    # Cash and bank closing balances
    groups = reports.get("groups", [])

    for key, name in [
        ("cash_in_hand", "Cash-in-Hand"),
        ("bank_balance", "Bank Accounts"),
    ]:
        data[key] = metric(
            key,
            exact_row(groups, name),
            "Group closing balances",
            period=False,
        )

    # GST and TDS ledgers
    ledgers = reports.get("ledgers")

    tax_ledgers = [
        ledger
        for ledger in (ledgers or [])
        if ledger.get("name")
        and (
            (ledger.get("parent") or "").strip().casefold()
            in ("duties & taxes", "current liabilities")
            or any(
                keyword in ledger["name"].casefold()
                for keyword in (
                    "gst",
                    "cgst",
                    "sgst",
                    "igst",
                    "utgst",
                    "tds",
                )
            )
        )
    ]

    if tax_ledgers:
        gst_ledgers = []
        tds_ledgers = []

        for ledger in tax_ledgers:
            name_lower = ledger["name"].casefold()
            parent = (ledger.get("parent") or "").strip().casefold()

            if (
                name_lower.startswith("tds")
                or "tds payable" in name_lower
                or "tax deducted at source" in name_lower
                or (
                    "tds" in name_lower
                    and parent in (
                        "duties & taxes",
                        "current liabilities",
                        "provisions",
                    )
                )
            ):
                tds_ledgers.append(ledger)

            elif any(
                keyword in name_lower
                for keyword in ("cgst", "sgst", "igst", "utgst", "gst")
            ):
                gst_ledgers.append(ledger)

        if gst_ledgers:
            output_tax = sum(
                ledger["amount"]
                for ledger in gst_ledgers
                if (
                    ledger.get("amount") is not None
                    and ledger["amount"] > 0
                )
            )

            input_credit = sum(
                abs(ledger["amount"])
                for ledger in gst_ledgers
                if (
                    ledger.get("amount") is not None
                    and ledger["amount"] < 0
                )
            )

            net_gst = max(0.0, output_tax - input_credit)

            data["gst_payable"] = net_gst

            sources["gst_payable"] = {
                "report": "Duties & Taxes Ledgers",
                "label": "Net GST Payable",
                "field": (
                    f"Output GST (Rs. {output_tax:,.2f}) "
                    f"minus ITC (Rs. {input_credit:,.2f})"
                ),
                "raw": f"{net_gst:.2f}",
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "status": "available",
                "message": None,
            }

        else:
            data["gst_payable"] = 0.0

            sources["gst_payable"] = {
                "report": "Duties & Taxes Ledgers",
                "label": "GST Payable",
                "field": "No GST liability recorded in Tally",
                "raw": "0.00",
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "status": "available",
                "message": None,
            }

        if tds_ledgers:
            tds_total = sum(
                ledger["amount"]
                for ledger in tds_ledgers
                if (
                    ledger.get("amount") is not None
                    and ledger["amount"] > 0
                )
            )

            data["tds_payable"] = max(0.0, tds_total)

            sources["tds_payable"] = {
                "report": "Duties & Taxes Ledgers",
                "label": "TDS Payable",
                "field": "TDS ledger credit balances",
                "raw": f'{data["tds_payable"]:.2f}',
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "status": "available",
                "message": None,
            }

        else:
            data["tds_payable"] = 0.0

            sources["tds_payable"] = {
                "report": "Duties & Taxes Ledgers",
                "label": "TDS Payable",
                "field": "No TDS liabilities recorded in Tally",
                "raw": "0.00",
                "from_date": start.isoformat(),
                "to_date": end.isoformat(),
                "status": "available",
                "message": None,
            }

    else:
        for key in ("tds_payable", "gst_payable"):
            data[key] = metric(
                key,
                None,
                "Statutory payable report not verified",
                period=False,
            )

    # Receivables and payables must match the selected as-of date.
    contexts = {}

    for key in ("receivables", "payables"):
        report = reports.get(key, {})
        matches_date = report.get("to_date") == end.isoformat()

        contexts[key] = {
            "from_date": report.get("from_date"),
            "to_date": report.get("to_date"),
            "matches_selected_as_of": matches_date,
        }

        total = (
            {
                "name": "Pending Amount total",
                "amount": report.get("total"),
                "raw": report.get("raw_total"),
                "field": "HTML Pending Amount footer",
            }
            if matches_date
            else None
        )

        if matches_date:
            reason = None
        elif key not in reports:
            reason = "Tally did not return this report. Refresh to try again."
        elif report.get("to_date"):
            reason = (
                f"Tally returned these as on {_day(report['to_date'])}, "
                "not the selected date."
            )
        else:
            reason = "Tally did not confirm the date of these balances."

        report_name = (
            "Bills Receivable (native HTML)"
            if key == "receivables"
            else "Bills Payable (native HTML)"
        )

        data[key] = metric(
            key,
            total,
            report_name,
            period=False,
            reason=reason,
        )

        bills = report.get("bills") if matches_date else None

        data[f"{key}_ageing"] = None if bills is None else ageing(bills)

        data[f"top_{key}"] = (
            None
            if bills is None
            else [
                {
                    **bill,
                    "status": (
                        "Unavailable"
                        if bill["days_overdue"] is None
                        else (
                            "Overdue"
                            if bill["days_overdue"] > 0
                            else "Not overdue"
                        )
                    ),
                }
                for bill in sorted(
                    bills,
                    key=lambda bill: (
                        bill["amount"] is not None,
                        bill["amount"]
                        if bill["amount"] is not None
                        else 0,
                    ),
                    reverse=True,
                )[:5]
            ]
        )

    # Find which ledger accounts belong to Cash or Bank groups.
    group_by_name = {
        row["name"]: row
        for row in groups
    }

    def category(parent):
        visited = set()

        while parent and parent not in visited:
            visited.add(parent)

            group = group_by_name.get(parent, {})
            identity = group.get("reserved_name") or parent

            if identity == "Cash-in-Hand":
                return "Cash"

            if identity in ("Bank Accounts", "Bank OD A/c"):
                return "Bank"

            parent = group.get("parent")

        return None

    accounts = None

    if "ledgers" in reports and "groups" in reports:
        accounts = []

        for ledger in reports["ledgers"]:
            kind = category(ledger.get("parent"))

            if kind:
                accounts.append({
                    "name": ledger["name"],
                    "balance": ledger["amount"],
                    "category": kind,
                    "raw": ledger["raw"],
                })

    data["cash_bank_accounts"] = accounts

    def breakdown(names):
        """Pick breakdown rows directly from the selected P&L."""
        return [
            {
                "label": row["name"],
                "value": row["amount"],
            }
            for name in names
            if (
                (row := exact_row(pl, name)) is not None
                and row["amount"] is not None
            )
        ] or None

    # Inflows are the income lines of the selected P&L itself.
    # Ledger closing balances are not period figures, so they are
    # never used for this chart.
    data["sales_breakdown"] = breakdown(
        ("Sales Accounts", "Direct Incomes", "Indirect Incomes")
    )

    data["expense_breakdown"] = breakdown(
        ("Direct Expenses", "Indirect Expenses")
    )

    data.update({
        "period_verified": period_matches,
        "comparison": _comparison(reports, start, end, company),
        "metric_sources": sources,
        "report_contexts": contexts,
        "tally_report_period": {
            "from_date": native_pl.get("from_date"),
            "to_date": native_pl.get("to_date"),
        },
        "company_name": company,
        "from_date": start.isoformat(),
        "to_date": end.isoformat(),
        "balance_convention": (
            "Tally signed closing balances: negative is debit, "
            "positive is credit. Signs are preserved."
        ),
    })

    return data