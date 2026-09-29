"""Map Tally report data into the dashboard response."""

from app.tally.parsers.common import to_optional_float


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


def map_dashboard_summary(reports, start, end, company):
    sources = {}

    def metric(key, row, report, *, period=True, reason=None):
        """Store a dashboard value along with its Tally source details."""
        value = row.get("amount") if row else None

        sources[key] = {
            "report": report,
            "label": row.get("name") if row else None,
            "field": row.get("field") if row else None,
            "raw": row.get("raw") if row else None,
            "from_date": start.isoformat() if period else None,
            "to_date": end.isoformat(),
            "status": "available" if value is not None else "unavailable",
            "message": None if value is not None else (reason or UNAVAILABLE),
        }

        return value

    # Main Profit & Loss values
    pl = reports.get("profit_loss", [])

    data = {
        "total_sales": metric(
            "total_sales",
            exact_row(pl, "Sales Accounts"),
            "Profit and Loss",
        ),
        "total_purchases": metric(
            "total_purchases",
            purchase_row(pl),
            "Profit and Loss",
        ),
    }

    # Tally's native P&L is also used for Profit/Loss totals.
    native_pl = reports.get("profit_loss_totals", {})

    period_matches = (
        native_pl.get("from_date") == start.isoformat()
        and native_pl.get("to_date") == end.isoformat()
        and any(
            company in row
            for row in native_pl.get("rows", [])
        )
    )

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
                        "amount": to_optional_float(nonempty[1]),
                        "raw": nonempty[1],
                        "field": "HTML result row",
                    })

        reason = (
            None
            if period_matches
            else (
                "Tally returned a different or unverified P&L period; "
                "its net result is not used for the selected dates."
            )
        )

        data[key] = metric(
            key,
            matches[0] if len(matches) == 1 else None,
            "Profit and Loss (native HTML)",
            reason=reason,
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

        reason = (
            None
            if matches_date
            else (
                "Tally returned a different or unverified outstanding "
                "as-of date; select its returned period to view these balances."
            )
        )

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

    # Keep the sales chart tied to the selected P&L period.
    # Ledger closing balances are not used as sales revenue here.
    # Show sales breakdown only when Tally provides
    # Sales Accounts for the selected period.
    sales_items = []

    sales_row = exact_row(pl, "Sales Accounts")

    if sales_row is not None and sales_row.get("amount") is not None:
        sales_items.append({
            "label": sales_row["name"],
            "value": sales_row["amount"],
            "type": "Sales Revenue",
        })

    data["sales_breakdown"] = sales_items or None

    data["expense_breakdown"] = breakdown(
        ("Direct Expenses", "Indirect Expenses")
    )

    data.update({
        "revenue": data["total_sales"],
        "expenses": data["total_purchases"],
        "pending_invoices": None,
        "sales_growth_pct": None,
        "purchases_growth_pct": None,
        "profit_growth_pct": None,
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