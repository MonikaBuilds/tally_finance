from datetime import datetime
import re


def _format_period(from_date: str | None, to_date: str | None) -> str:
    def _display_date(d_str: str) -> str:
        for fmt in ("%Y-%m-%d", "%d-%m-%Y"):
            try:
                return datetime.strptime(d_str, fmt).strftime("%d-%m-%Y")
            except ValueError:
                pass
        return d_str

    if from_date and to_date:
        return f" for the period {_display_date(from_date)} to {_display_date(to_date)}"
    if from_date:
        return f" from {_display_date(from_date)}"
    if to_date:
        return f" up to {_display_date(to_date)}"
    return ""


def format_indian_currency(value) -> str:
    """
    Indian digit grouping (12,34,567). Paise are shown whenever Tally's
    amount has them (5,19,053.47) and omitted only when they are zero,
    so a displayed amount never differs from the Tally figure.
    """
    from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

    try:
        amount = Decimal(str(value if value is not None else 0))
    except (InvalidOperation, ValueError, TypeError):
        amount = Decimal("0")

    amount = amount.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    negative = amount < 0
    amount = abs(amount)

    integer_part, _, paise = f"{amount:.2f}".partition(".")

    if len(integer_part) <= 3:
        formatted = integer_part
    else:
        last_three = integer_part[-3:]
        remaining = integer_part[:-3]
        groups = []
        while len(remaining) > 2:
            groups.insert(0, remaining[-2:])
            remaining = remaining[:-2]
        if remaining:
            groups.insert(0, remaining)
        formatted = ",".join(groups) + "," + last_three

    if paise != "00":
        formatted = f"{formatted}.{paise}"

    prefix = "-₹" if negative else "₹"

    return f"{prefix}{formatted}"


def _quantity_number(value):
    """Numeric part of a Tally quantity: "67 NOS" -> 67, "-3 NOS" -> -3."""
    if not value:
        return None
    match = re.search(r"-?\d+(?:\.\d+)?", str(value).replace(",", ""))
    if not match:
        return None
    try:
        return float(match.group())
    except ValueError:
        return None


def _stock_value_text(value, quantity=None) -> str:
    """
    Present a Tally stock value the way Tally itself shows it.

    Tally's XML export negates inventory values even for ordinary
    positive stock, while the Tally screen and the Profit & Loss
    Closing Stock line show that same figure positive. The sign that
    actually matters is the one on the quantity, which is how the
    inventory parsers already decide it: negative quantity means
    genuinely negative stock, otherwise the value is a positive
    holding.
    """
    if value in (None, ""):
        return "Not available"
    try:
        amount = float(str(value).replace(",", "").strip())
    except ValueError:
        return str(value)

    quantity_number = _quantity_number(quantity)
    if quantity_number is not None and quantity_number < 0:
        return format_indian_currency(-abs(amount))
    return format_indian_currency(abs(amount))


def format_tool_response(
    tool_name: str,
    tool_result: dict
) -> str:
    if not tool_result.get("success"):
        return tool_result.get(
            "message",
            "Unable to retrieve the requested data from Tally."
        )

    if tool_result.get("source") not in {"tally", "cache", "stale_cache"}:
        return (
            "I could not verify this financial information "
            "from Tally."
        )

    data = tool_result.get("data")

    if not isinstance(data, dict):
        return (
            "I could not verify this financial information "
            "from Tally."
        )

    if tool_name == "get_receivables":
        total = data.get(
            "total_receivable",
            0
        )

        count = data.get(
            "count",
            0
        )

        if total is None:
            return (
                f"Tally listed {count} pending bill(s) but did not "
                "return a total for this report, so no total is shown."
            )

        return (
            f"Your total outstanding receivables are "
            f"{format_indian_currency(total)} "
            f"across {count} pending bill(s) "
            "(Tally's Bills Receivable total)."
        )

    if tool_name == "get_payables":
        total = data.get(
            "total_payable",
            0
        )

        count = data.get(
            "count",
            0
        )

        if total is None:
            return (
                f"Tally listed {count} pending bill(s) but did not "
                "return a total for this report, so no total is shown."
            )

        return (
            f"Your total outstanding payables are "
            f"{format_indian_currency(total)} "
            f"across {count} pending bill(s) "
            "(Tally's Bills Payable total)."
        )

    if tool_name == "get_pending_invoices":
        count = data.get(
            "count",
            0
        )

        return (
            f"You currently have {count} "
            f"pending invoice(s) in Tally."
        )

    if tool_name == "get_highest_receivable":
        party = data.get("party")

        amount = data.get(
            "amount",
            0
        )

        if not party:
            return (
                "No outstanding receivable party "
                "was found in Tally."
            )

        return (
            f"{party} has the highest outstanding "
            f"receivable of "
            f"{format_indian_currency(amount)}."
        )

    if tool_name == "get_highest_payable":
        party = data.get("party")

        amount = data.get(
            "amount",
            0
        )

        if not party:
            return (
                "No outstanding payable party "
                "was found in Tally."
            )

        return (
            f"{party} has the highest outstanding "
            f"payable of "
            f"{format_indian_currency(amount)}."
        )

    if tool_name == "get_overdue_receivables":
        total = data.get(
            "total_overdue",
            0
        )

        count = data.get(
            "count",
            0
        )

        return (
            f"You have {count} overdue receivable "
            f"bill(s) totaling "
            f"{format_indian_currency(total)}."
        )

    if tool_name == "get_overdue_payables":
        total = data.get(
            "total_overdue",
            0
        )

        count = data.get(
            "count",
            0
        )

        return (
            f"You have {count} overdue payable "
            f"bill(s) totaling "
            f"{format_indian_currency(total)}."
        )

    if tool_name == "get_overdue_invoices":
        invoices = data.get("invoices") or []

        if not invoices:
            return "No overdue invoices were found in Tally."

        lines = [
            f"You have {len(invoices)} overdue invoice(s) in Tally."
        ]

        for invoice in invoices[:20]:
            party = invoice.get("party") or "Unknown party"
            reference = (
                invoice.get("bill_reference")
                or invoice.get("voucher_number")
                or "no reference"
            )
            amount = invoice.get("outstanding_amount")
            days = invoice.get("overdue_days")

            amount_text = (
                format_indian_currency(abs(amount))
                if isinstance(amount, (int, float))
                else "amount not returned by Tally"
            )
            days_text = f"{days} days overdue" if days is not None else "overdue"

            lines.append(
                f"- {party} | {reference} | {amount_text} | {days_text}"
            )

        if len(invoices) > 20:
            lines.append(f"... and {len(invoices) - 20} more.")

        return "\n".join(lines)

    if tool_name == "get_revenue":
        revenue = data.get(
            "revenue",
            0
        )
        period_str = _format_period(
            data.get("from_date"),
            data.get("to_date"),
        )

        answer = (
            f"Your revenue (Sales Accounts in Tally){period_str} is "
            f"{format_indian_currency(revenue)}."
        )
        direct_incomes = data.get("direct_incomes")
        if direct_incomes:
            answer += (
                f" Direct Incomes are shown separately in Tally: "
                f"{format_indian_currency(abs(direct_incomes))}."
            )
        return answer

    if tool_name == "get_expenses":
        expenses = data.get(
            "expenses",
            0
        )
        period_str = _format_period(
            data.get("from_date"),
            data.get("to_date"),
        )

        lines = [
            f"Your total expenses{period_str} are "
            f"{format_indian_currency(expenses)}."
        ]
        expense_lines = data.get("expense_lines") or []
        if expense_lines:
            lines.append(
                "This total is derived by adding these Tally P&L lines:"
            )
            for line in expense_lines:
                lines.append(
                    f"- {line.get('name')}: "
                    f"{format_indian_currency(abs(line.get('amount') or 0))}"
                )
        return "\n".join(lines)

    if tool_name == "get_net_profit":
        result_type = data.get(
            "result_type"
        )

        amount = data.get(
            "amount",
            0
        )
        period_str = _format_period(
            data.get("from_date"),
            data.get("to_date"),
        )

        if result_type == "loss":
            return (
                f"You currently have a net loss{period_str} of "
                f"{format_indian_currency(amount)}."
            )

        return (
            f"You currently have a net profit{period_str} of "
            f"{format_indian_currency(amount)}."
        )

    if tool_name == "get_profit_loss":
        report = data.get("report") or {}
        left_rows = data.get("left") or report.get("left", [])
        right_rows = data.get("right") or report.get("right", [])
        summary = data.get("summary") or report.get("summary", {})
        total_left = data.get("total_left") if data.get("total_left") is not None else report.get("total_left")
        total_right = data.get("total_right") if data.get("total_right") is not None else report.get("total_right")
        from_date = data.get("from_date")
        to_date = data.get("to_date")

        lines = ["Profit & Loss Statement (from Tally)"]
        if from_date and to_date:
            lines.append(f"Period: {from_date} to {to_date}")
        elif to_date:
            lines.append(f"As of: {to_date}")

        named_incomes = [r for r in right_rows if r.get("name") and not r.get("is_subtotal")]
        if named_incomes:
            lines.append("\n--- Income & Revenue ---")
            for item in named_incomes:
                lines.append(f"• {item['name']}: {format_indian_currency(item.get('amount', 0.0))}")

        named_expenses = [r for r in left_rows if r.get("name") and not r.get("is_subtotal")]
        if named_expenses:
            lines.append("\n--- Expenses & Cost of Sales ---")
            for item in named_expenses:
                lines.append(f"• {item['name']}: {format_indian_currency(item.get('amount', 0.0))}")

        gross_res = summary.get("gross_result")
        net_res = summary.get("net_result")

        lines.append("\n--- Summary ---")
        if gross_res is not None:
            if isinstance(gross_res, dict):
                gross_amt = gross_res.get("amount", 0.0)
                gross_type = gross_res.get("type", "profit")
                lines.append(f"Gross {gross_type.capitalize()}: {format_indian_currency(gross_amt)}")
            else:
                lines.append(f"Gross Profit / Loss: {format_indian_currency(gross_res)}")

        if net_res is not None:
            if isinstance(net_res, dict):
                net_amt = net_res.get("amount", 0.0)
                net_type = net_res.get("type", "profit")
                lines.append(f"Net {net_type.capitalize()}: {format_indian_currency(net_amt)}")
            else:
                lines.append(f"Net Profit / Loss: {format_indian_currency(net_res)}")

        if total_left is not None and total_right is not None:
            lines.append(f"Total Debits: {format_indian_currency(total_left)} | Total Credits: {format_indian_currency(total_right)}")

        return "\n".join(lines)

    if tool_name == "get_trial_balance":
        report = data.get("report") or {}
        rows = data.get("rows") or report.get("rows", [])
        to_date = data.get("to_date")

        if not rows:
            return "The Trial Balance contains no entries in Tally for the specified period."

        lines = ["Trial Balance (from Tally)"]
        if to_date:
            lines.append(f"As of: {to_date}")

        lines.append("\nParticulars | Debit | Credit")
        lines.append("-" * 45)

        total_dr = 0.0
        total_cr = 0.0

        for r in rows:
            name = r.get("name", "")
            dr = r.get("debit", 0.0) or 0.0
            cr = r.get("credit", 0.0) or 0.0
            total_dr += dr
            total_cr += cr

            dr_str = format_indian_currency(dr) if dr else "-"
            cr_str = format_indian_currency(cr) if cr else "-"
            lines.append(f"• {name}: Debit {dr_str} | Credit {cr_str}")

        lines.append("-" * 45)
        lines.append(f"Total Debit: {format_indian_currency(total_dr)} | Total Credit: {format_indian_currency(total_cr)}")
        return "\n".join(lines)

    if tool_name == "get_balance_sheet":
        report = data.get("report") or {}
        rows = data.get("rows") or report.get("rows", [])
        to_date = data.get("to_date")

        if not rows:
            return "The Balance Sheet contains no entries in Tally for the specified period."

        lines = ["Balance Sheet (from Tally)"]
        if to_date:
            lines.append(f"As of: {to_date}")

        lines.append("\n--- Particulars & Balances ---")
        for r in rows:
            name = r.get("name", "")
            amt = r.get("amount")
            amt_str = format_indian_currency(amt) if amt is not None else "-"
            lines.append(f"• {name}: {amt_str}")

        return "\n".join(lines)

    if tool_name == "get_party_outstanding_summary":
        party = data.get(
            "party",
            "The requested party"
        )

        total_receivable = data.get(
            "total_receivable",
            0
        )

        total_payable = data.get(
            "total_payable",
            0
        )

        receivable_count = data.get(
            "receivable_count",
            0
        )

        payable_count = data.get(
            "payable_count",
            0
        )

        if (
            total_receivable > 0
            and total_payable > 0
        ):
            return (
                f"{party} has an outstanding receivable of "
                f"{format_indian_currency(total_receivable)} "
                f"across {receivable_count} bill(s), and an "
                f"outstanding payable of "
                f"{format_indian_currency(total_payable)} "
                f"across {payable_count} bill(s)."
            )

        if total_receivable > 0:
            return (
                f"{party} has an outstanding receivable of "
                f"{format_indian_currency(total_receivable)} "
                f"across {receivable_count} bill(s), with no "
                f"outstanding payable."
            )

        if total_payable > 0:
            return (
                f"{party} has an outstanding payable of "
                f"{format_indian_currency(total_payable)} "
                f"across {payable_count} bill(s), with no "
                f"outstanding receivable."
            )

        return (
            f"No outstanding receivable or payable "
            f"was found for {party}."
        )

    if tool_name == "get_outstanding_summary":
        total_receivable = data.get(
            "total_receivable",
            0
        )

        receivable_count = data.get(
            "receivable_count",
            0
        )

        total_payable = data.get(
            "total_payable",
            0
        )

        payable_count = data.get(
            "payable_count",
            0
        )

        return (
            f"Your total outstanding receivables are "
            f"{format_indian_currency(total_receivable)} "
            f"across {receivable_count} bill(s), while your "
            f"total outstanding payables are "
            f"{format_indian_currency(total_payable)} "
            f"across {payable_count} bill(s)."
        )

    if tool_name == "get_top_receivables":
        bills = data.get(
            "bills",
            []
        )

        if not bills:
            return (
                "No outstanding receivables "
                "were found in Tally."
            )

        lines = []

        for index, bill in enumerate(
            bills,
            start=1
        ):
            party = bill.get(
                "party",
                "Unknown party"
            )

            amount = bill.get(
                "outstanding_amount",
                0
            )

            reference = bill.get(
                "bill_reference"
            )

            line = (
                f"{index}. {party} - "
                f"{format_indian_currency(amount)}"
            )

            if reference:
                line += (
                    f" (Bill: {reference})"
                )

            lines.append(line)

        return (
            "Top outstanding receivables:\n"
            + "\n".join(lines)
        )

    if tool_name == "get_top_payables":
        bills = data.get(
            "bills",
            []
        )

        if not bills:
            return (
                "No outstanding payables "
                "were found in Tally."
            )

        lines = []

        for index, bill in enumerate(
            bills,
            start=1
        ):
            party = bill.get(
                "party",
                "Unknown party"
            )

            amount = bill.get(
                "outstanding_amount",
                0
            )

            reference = bill.get(
                "bill_reference"
            )

            line = (
                f"{index}. {party} - "
                f"{format_indian_currency(amount)}"
            )

            if reference:
                line += (
                    f" (Bill: {reference})"
                )

            lines.append(line)

        return (
            "Top outstanding payables:\n"
            + "\n".join(lines)
        )

    if tool_name in {
        "get_aged_receivables",
        "get_aged_payables"
    }:
        minimum_days = data.get(
            "minimum_days"
        )

        count = data.get(
            "count",
            0
        )

        total = data.get(
            "total_overdue",
            0
        )

        buckets = data.get(
            "buckets",
            {}
        )

        bills = data.get(
            "bills",
            []
        )

        item_type = (
            "receivables"
            if tool_name == "get_aged_receivables"
            else "payables"
        )

        if minimum_days:
            heading = (
                f"Outstanding {item_type} overdue "
                f"at least {minimum_days} days:"
            )
        else:
            heading = (
                f"{item_type.capitalize()} aging summary:"
            )

        lines = [
            heading,
            (
                f"Total overdue: "
                f"{format_indian_currency(total)}"
            ),
            f"Pending bills: {count}",
        ]

        if not minimum_days:
            bucket_labels = [
                (
                    "1_30",
                    "1-30 days"
                ),
                (
                    "31_60",
                    "31-60 days"
                ),
                (
                    "61_90",
                    "61-90 days"
                ),
                (
                    "91_plus",
                    "91+ days"
                ),
            ]

            lines.append("")
            lines.append(
                "Aging buckets:"
            )

            for key, label in bucket_labels:
                bucket = buckets.get(
                    key,
                    {}
                )

                lines.append(
                    f"{label}: "
                    f"{format_indian_currency(bucket.get('amount', 0))} "
                    f"({bucket.get('count', 0)} bills)"
                )

        if bills:
            lines.append("")
            lines.append(
                "Bills:"
            )

            for index, bill in enumerate(
                bills,
                start=1
            ):
                party = bill.get(
                    "party",
                    "Unknown party"
                )

                amount = bill.get(
                    "outstanding_amount",
                    0
                )

                overdue_days = bill.get(
                    "overdue_days",
                    0
                )

                reference = bill.get(
                    "bill_reference"
                )

                line = (
                    f"{index}. {party} - "
                    f"{format_indian_currency(amount)} - "
                    f"{overdue_days} days overdue"
                )

                if reference:
                    line += (
                        f" (Bill: {reference})"
                    )

                lines.append(line)

        return "\n".join(lines)

    if tool_name == "get_period_comparison":
        metric = data.get(
            "metric",
            "financial metric"
        )

        first_period = data.get(
            "first_period",
            {}
        )

        second_period = data.get(
            "second_period",
            {}
        )

        first_value = first_period.get(
            "value",
            0
        )

        second_value = second_period.get(
            "value",
            0
        )

        first_from_date = first_period.get(
            "from_date"
        )

        first_to_date = first_period.get(
            "to_date"
        )

        second_from_date = second_period.get(
            "from_date"
        )

        second_to_date = second_period.get(
            "to_date"
        )

        difference = data.get(
            "difference",
            0
        )

        percentage_change = data.get(
            "percentage_change"
        )

        metric_labels = {
            "revenue": "Revenue",
            "expenses": "Expenses",
            "net_profit": "Net profit"
        }

        metric_label = metric_labels.get(
            metric,
            metric.replace(
                "_",
                " "
            ).title()
        )

        lines = [
            f"{metric_label} comparison:",
            (
                f"{first_from_date} to "
                f"{first_to_date}: "
                f"{format_indian_currency(first_value)}"
            ),
            (
                f"{second_from_date} to "
                f"{second_to_date}: "
                f"{format_indian_currency(second_value)}"
            )
        ]

        if difference > 0:
            direction = "higher"
        elif difference < 0:
            direction = "lower"
        else:
            direction = "unchanged"

        if direction == "unchanged":
            lines.append(
                f"{metric_label} remained unchanged."
            )

        else:
            difference_text = (
                format_indian_currency(
                    abs(difference)
                )
            )

            if percentage_change is not None:
                lines.append(
                    f"{metric_label} is "
                    f"{difference_text} {direction} "
                    f"({abs(percentage_change):.2f}%)."
                )

            else:
                lines.append(
                    f"{metric_label} is "
                    f"{difference_text} {direction}."
                )

        return "\n".join(lines)
    
    if tool_name == "get_financial_summary":
        revenue = data.get("revenue")
        expenses = data.get("expenses")
        net_profit = data.get("net_profit")
        receivables = data.get("receivables")
        payables = data.get("payables")
        pending_invoices = data.get("pending_invoices", 0)

        def _money(value):
            if value is None:
                return "not returned by Tally"
            return format_indian_currency(value)

        from_date = data.get("from_date")
        to_date = data.get("to_date")

        lines = [
            "Financial summary:"
        ]

        if from_date and to_date:
            lines.append(
                f"Period: {from_date} to {to_date}"
            )

        lines.extend([
            f"Revenue (Sales Accounts): {_money(revenue)}",
            f"Expenses (derived from Tally expense lines): {_money(expenses)}",
        ])

        if net_profit is None:
            lines.append("Net profit / loss: not returned by Tally")
        elif net_profit >= 0:
            lines.append(
                f"Net profit: {format_indian_currency(net_profit)}"
            )
        else:
            lines.append(
                f"Net loss: {format_indian_currency(abs(net_profit))}"
            )

        lines.extend([
            f"Receivables (Bills Receivable total): {_money(receivables)}",
            f"Payables (Bills Payable total): {_money(payables)}",
            f"Pending invoices: {pending_invoices}"
        ])

        return "\n".join(lines)

        
    if tool_name == "get_ledger_report":
        ledger_name = data.get(
            "ledger_name",
            "The requested ledger"
        )

        opening_balance = data.get(
            "opening_balance",
        )

        closing_balance = data.get(
            "closing_balance",
            
        )

        entry_count = data.get(
            "entry_count",
            0
        )


        def _format_tally_balance(value):
            if value is None:
                return "not available in the Tally response"

            return format_indian_currency(value)

        if entry_count == 0:
            return (
                f"{ledger_name} has an opening balance of "
                f"{_format_tally_balance(opening_balance)} and no "
                f"transactions in the selected period. "
                f"The closing balance returned is "
                f"{_format_tally_balance(closing_balance)}."
            )

        lines = [
            f"{ledger_name}: opening balance "
            f"{_format_tally_balance(opening_balance)}, "
            f"{entry_count} transaction(s) found in the selected period, "
            f"closing balance "
            f"{_format_tally_balance(closing_balance)}."
        ]

        entries = data.get("entries") or data.get("transactions") or []
        if entries:
            lines.append("")
            lines.append("Transactions:")
            display_limit = 25
            for tx in entries[:display_limit]:
                tx_date = tx.get("date") or ""
                v_type = tx.get("voucher_type") or "Voucher"
                v_no = tx.get("voucher_number") or ""
                particulars = tx.get("particulars") or ""
                debit = float(tx.get("debit") or 0.0)
                credit = float(tx.get("credit") or 0.0)

                amount_parts = []
                if debit > 0:
                    amount_parts.append(f"{format_indian_currency(debit)} Dr")
                if credit > 0:
                    amount_parts.append(f"{format_indian_currency(credit)} Cr")
                amount_str = ", ".join(amount_parts) if amount_parts else "₹0"

                v_str = f"{v_type}" + (f" #{v_no}" if v_no else "")
                lines.append(f"• {tx_date} | {v_str} | {particulars} | {amount_str}")

            if len(entries) > display_limit:
                lines.append(f"... and {len(entries) - display_limit} more transactions.")

        return "\n".join(lines)
        
    if tool_name in ("get_cash_balance", "get_bank_balance"):
        label = "cash" if tool_name == "get_cash_balance" else "bank"

        def _balance_text(amount, side):
            if amount is None:
                return "not returned by Tally"
            text = format_indian_currency(abs(amount))
            return f"{text} {side}" if side else text

        ledger_name = data.get("ledger_name")

        if ledger_name:
            return (
                f"The closing balance of {ledger_name} in Tally is "
                f"{_balance_text(data.get('closing_balance'), data.get('balance_type'))}."
            )

        lines = []

        group_totals = data.get("group_totals") or []
        for group in group_totals:
            lines.append(
                f"{group.get('group')} (Tally group closing balance): "
                f"{_balance_text(group.get('closing_balance'), group.get('balance_type'))}"
            )

        if not group_totals:
            lines.append(
                f"Tally did not return a {label} group closing balance."
            )

        ledgers = data.get("ledgers") or []
        if ledgers:
            lines.append("")
            lines.append(f"{label.title()} ledgers ({len(ledgers)}):")
            for ledger in ledgers:
                lines.append(
                    f"- {ledger.get('name')}: "
                    f"{_balance_text(ledger.get('closing_balance'), ledger.get('balance_type'))}"
                )

        if tool_name == "get_bank_balance" and len(group_totals) > 1:
            lines.append("")
            lines.append(
                "Bank Accounts and Bank OD A/c are shown as Tally reports "
                "them and are not added together."
            )

        return "\n".join(lines)

    if tool_name == "get_bank_transactions":
        ledger_name = data.get(
            "ledger_name",
            "Bank account"
        )

        transactions = data.get(
            "transactions",
            data.get("entries", [])
        )

        opening_balance = data.get(
            "opening_balance",
            0
        )

        closing_balance = data.get(
            "closing_balance",
            0
        )

        from_date = data.get("from_date")
        to_date = data.get("to_date")

        if not transactions:
            return (
                f"No bank transactions were found for "
                f"{ledger_name} in the selected period."
            )

        lines = [
            f"Bank transactions for {ledger_name}:"
        ]

        if from_date and to_date:
            lines.append(
                f"Period: {from_date} to {to_date}"
            )

        lines.append(
            f"Opening balance: "
            f"{format_indian_currency(opening_balance)}"
        )

        lines.append("")

        for index, transaction in enumerate(
            transactions,
            start=1
        ):
            transaction_date = (
                transaction.get("date")
                or transaction.get("voucher_date")
                or "-"
            )

            voucher_type = (
                transaction.get("voucher_type")
                or transaction.get("type")
                or "Transaction"
            )

            voucher_number = (
                transaction.get("voucher_number")
                or transaction.get("voucher_no")
                or ""
            )

            debit = float(
                transaction.get("debit", 0) or 0
            )

            credit = float(
                transaction.get("credit", 0) or 0
            )

            if debit:
                amount_text = (
                    f"{format_indian_currency(debit)} Dr"
                )
            elif credit:
                amount_text = (
                    f"{format_indian_currency(credit)} Cr"
                )
            else:
                amount = transaction.get(
                    "amount",
                    0
                )
                amount_text = format_indian_currency(
                    amount
                )

            line = (
                f"{index}. {transaction_date} - "
                f"{voucher_type}"
            )

            if voucher_number:
                line += f" #{voucher_number}"

            line += f" - {amount_text}"

            lines.append(line)

        lines.append("")
        lines.append(
            f"Closing balance: "
            f"{format_indian_currency(closing_balance)}"
        )

        return "\n".join(lines)

    if tool_name == "get_cash_transactions":
        ledger_name = data.get("ledger_name", "Cash account")
        transactions = data.get(
            "transactions",
            data.get("entries", [])
        )

        from_date = data.get("from_date")
        to_date = data.get("to_date")

        # No transactions found for the selected date range.
        if not transactions:
            if from_date and to_date:
                return (
                    f"No cash transactions were found for "
                    f"{ledger_name} from {from_date} to {to_date}."
                )

            return (
                f"No cash transactions were found for "
                f"{ledger_name}."
            )

        lines = [
            f"Cash transactions for {ledger_name}:"
        ]

        if from_date and to_date:
            lines.append(
                f"Period: {from_date} to {to_date}"
            )

        lines.append("")

        # Format every Tally ledger transaction in a readable form.
        for index, transaction in enumerate(
            transactions,
            start=1,
        ):
            transaction_date = (
                transaction.get("date")
                or transaction.get("voucher_date")
                or "-"
            )

            voucher_type = (
                transaction.get("voucher_type")
                or transaction.get("type")
                or "Transaction"
            )

            voucher_number = (
                transaction.get("voucher_number")
                or transaction.get("voucher_no")
                or ""
            )

            debit = float(
                transaction.get("debit", 0) or 0
            )

            credit = float(
                transaction.get("credit", 0) or 0
            )

            if debit:
                amount_text = (
                    f"{format_indian_currency(debit)} Dr"
                )

            elif credit:
                amount_text = (
                    f"{format_indian_currency(credit)} Cr"
                )

            else:
                amount = (
                    transaction.get("amount", 0)
                    or 0
                )

                amount_text = (
                    format_indian_currency(amount)
                )

            line = (
                f"{index}. {transaction_date} "
                f"- {voucher_type}"
            )

            if voucher_number:
                line += f" #{voucher_number}"

            line += f" - {amount_text}"

            lines.append(line)

        return "\n".join(lines)
    
    if tool_name == "get_sales_transactions":
        ledger_name = data.get(
            "ledger_name",
            "Sales account",
        )

        transactions = data.get(
            "transactions",
            data.get("entries", []),
        )

        from_date = data.get("from_date")
        to_date = data.get("to_date")

        if not transactions:
            if from_date and to_date:
                return (
                    f"No sales transactions were found for "
                    f"{ledger_name} from {from_date} to {to_date}."
                )

            return (
                f"No sales transactions were found for "
                f"{ledger_name}."
            )

        lines = [
            f"Sales transactions for {ledger_name}:"
        ]

        if from_date and to_date:
            lines.append(
                f"Period: {from_date} to {to_date}"
            )

        lines.append("")

        for index, transaction in enumerate(
            transactions,
            start=1,
        ):
            transaction_date = (
                transaction.get("date")
                or transaction.get("voucher_date")
                or "-"
            )

            voucher_type = (
                transaction.get("voucher_type")
                or transaction.get("type")
                or "Sales"
            )

            voucher_number = (
                transaction.get("voucher_number")
                or transaction.get("voucher_no")
                or ""
            )

            debit = float(
                transaction.get("debit", 0) or 0
            )

            credit = float(
                transaction.get("credit", 0) or 0
            )

            if debit:
                amount_text = (
                    f"{format_indian_currency(debit)} Dr"
                )

            elif credit:
                amount_text = (
                    f"{format_indian_currency(credit)} Cr"
                )

            else:
                amount = (
                    transaction.get("amount", 0)
                    or 0
                )

                amount_text = (
                    format_indian_currency(amount)
                )

            line = (
                f"{index}. {transaction_date} "
                f"- {voucher_type}"
            )

            if voucher_number:
                line += f" #{voucher_number}"

            line += f" - {amount_text}"

            lines.append(line)

        return "\n".join(lines)
    
    if tool_name == "get_purchase_transactions":
        ledger_name = data.get(
            "ledger_name",
            "Purchase account",
        )

        transactions = data.get(
            "transactions",
            data.get("entries", []),
        )

        from_date = data.get("from_date")
        to_date = data.get("to_date")

        if not transactions:
            if from_date and to_date:
                return (
                    f"No purchase transactions were found for "
                    f"{ledger_name} from {from_date} to {to_date}."
                )

            return (
                f"No purchase transactions were found for "
                f"{ledger_name}."
            )

        lines = [
            f"Purchase transactions for {ledger_name}:"
        ]

        if from_date and to_date:
            lines.append(
                f"Period: {from_date} to {to_date}"
            )

        lines.append("")

        for index, transaction in enumerate(
            transactions,
            start=1,
        ):
            transaction_date = (
                transaction.get("date")
                or transaction.get("voucher_date")
                or "-"
            )

            voucher_type = (
                transaction.get("voucher_type")
                or transaction.get("type")
                or "Purchase"
            )

            voucher_number = (
                transaction.get("voucher_number")
                or transaction.get("voucher_no")
                or ""
            )

            debit = float(
                transaction.get("debit", 0) or 0
            )

            credit = float(
                transaction.get("credit", 0) or 0
            )

            if debit:
                amount_text = (
                    f"{format_indian_currency(debit)} Dr"
                )

            elif credit:
                amount_text = (
                    f"{format_indian_currency(credit)} Cr"
                )

            else:
                amount = (
                    transaction.get("amount", 0)
                    or 0
                )

                amount_text = (
                    format_indian_currency(amount)
                )

            line = (
                f"{index}. {transaction_date} "
                f"- {voucher_type}"
            )

            if voucher_number:
                line += f" #{voucher_number}"

            line += f" - {amount_text}"

            lines.append(line)

        return "\n".join(lines)
    
    if tool_name == "get_receipt_transactions":
        transactions = data.get(
            "transactions",
            data.get("entries", []),
        )

        from_date = data.get("from_date")
        to_date = data.get("to_date")

        if not transactions:
            if from_date and to_date:
                return (
                    "No receipt transactions were found "
                    f"from {from_date} to {to_date}."
                )

            return "No receipt transactions were found."

        lines = [
            "Receipt transactions:"
        ]

        if from_date and to_date:
            lines.append(
                f"Period: {from_date} to {to_date}"
            )

        lines.append("")

        for index, transaction in enumerate(
            transactions,
            start=1,
        ):
            transaction_date = (
                transaction.get("date")
                or transaction.get("voucher_date")
                or "-"
            )

            voucher_type = (
                transaction.get("voucher_type")
                or transaction.get("type")
                or "Receipt"
            )

            voucher_number = (
                transaction.get("voucher_number")
                or transaction.get("voucher_no")
                or ""
            )

            ledger_name = (
                transaction.get("ledger_name")
                or ""
            )

            debit = float(
                transaction.get("debit", 0) or 0
            )

            credit = float(
                transaction.get("credit", 0) or 0
            )

            if debit:
                amount_text = (
                    f"{format_indian_currency(debit)} Dr"
                )

            elif credit:
                amount_text = (
                    f"{format_indian_currency(credit)} Cr"
                )

            else:
                amount = (
                    transaction.get("amount", 0)
                    or 0
                )

                amount_text = (
                    format_indian_currency(amount)
                )

            line = (
                f"{index}. {transaction_date} "
                f"- {voucher_type}"
            )

            if voucher_number:
                line += f" #{voucher_number}"

            line += f" - {amount_text}"

            if ledger_name:
                line += f" ({ledger_name})"

            lines.append(line)

        return "\n".join(lines)
    
    if tool_name == "get_payment_transactions":
        transactions = data.get(
            "transactions",
            data.get("entries", []),
        )

        from_date = data.get("from_date")
        to_date = data.get("to_date")

        if not transactions:
            if from_date and to_date:
                return (
                    "No payment transactions were found "
                    f"from {from_date} to {to_date}."
                )

            return "No payment transactions were found."

        lines = ["Payment transactions:"]

        if from_date and to_date:
            lines.append(
                f"Period: {from_date} to {to_date}"
            )

        lines.append("")

        for index, transaction in enumerate(
            transactions,
            start=1,
        ):
            transaction_date = (
                transaction.get("date")
                or transaction.get("voucher_date")
                or "-"
            )

            voucher_type = (
                transaction.get("voucher_type")
                or transaction.get("type")
                or "Payment"
            )

            voucher_number = (
                transaction.get("voucher_number")
                or transaction.get("voucher_no")
                or ""
            )

            ledger_name = (
                transaction.get("ledger_name")
                or ""
            )

            debit = float(
                transaction.get("debit", 0) or 0
            )

            credit = float(
                transaction.get("credit", 0) or 0
            )

            if debit:
                amount_text = (
                    f"{format_indian_currency(debit)} Dr"
                )

            elif credit:
                amount_text = (
                    f"{format_indian_currency(credit)} Cr"
                )

            else:
                amount = (
                    transaction.get("amount", 0)
                    or 0
                )

                amount_text = (
                    format_indian_currency(amount)
                )

            line = (
                f"{index}. {transaction_date} "
                f"- {voucher_type}"
            )

            if voucher_number:
                line += f" #{voucher_number}"

            line += f" - {amount_text}"

            if ledger_name:
                line += f" ({ledger_name})"

            lines.append(line)

        return "\n".join(lines)
    
    if tool_name in {
        "get_credit_note_transactions",
        "get_debit_note_transactions",
    }:
        transactions = data.get(
            "transactions",
            data.get("entries", []),
        )

        from_date = data.get("from_date")
        to_date = data.get("to_date")

        is_credit_note = (
            tool_name == "get_credit_note_transactions"
        )

        title = (
            "Credit Note transactions"
            if is_credit_note
            else "Debit Note transactions"
        )

        if not transactions:
            if from_date and to_date:
                return (
                    f"No {title.lower()} were found "
                    f"from {from_date} to {to_date}."
                )

            return f"No {title.lower()} were found."

        lines = [f"{title}:"]

        if from_date and to_date:
            lines.append(
                f"Period: {from_date} to {to_date}"
            )

        lines.append("")

        for index, transaction in enumerate(
            transactions,
            start=1,
        ):
            transaction_date = (
                transaction.get("date")
                or transaction.get("voucher_date")
                or "-"
            )

            voucher_type = (
                transaction.get("voucher_type")
                or transaction.get("type")
                or (
                    "Credit Note"
                    if is_credit_note
                    else "Debit Note"
                )
            )

            voucher_number = (
                transaction.get("voucher_number")
                or transaction.get("voucher_no")
                or ""
            )

            ledger_name = (
                transaction.get("ledger_name")
                or ""
            )

            debit = float(
                transaction.get("debit", 0) or 0
            )

            credit = float(
                transaction.get("credit", 0) or 0
            )

            if debit:
                amount_text = (
                    f"{format_indian_currency(debit)} Dr"
                )
            elif credit:
                amount_text = (
                    f"{format_indian_currency(credit)} Cr"
                )
            else:
                amount = (
                    transaction.get("amount", 0)
                    or 0
                )

                amount_text = (
                    format_indian_currency(amount)
                )

            line = (
                f"{index}. {transaction_date} "
                f"- {voucher_type}"
            )

            if voucher_number:
                line += f" #{voucher_number}"

            line += f" - {amount_text}"

            if ledger_name:
                line += f" ({ledger_name})"

            lines.append(line)

        return "\n".join(lines)

    if tool_name in {
        "get_customer_statement",
        "get_supplier_statement",
    }:
        party_name = data.get("party_name") or "-"
        party_type = data.get("party_type") or "party"

        transactions = data.get(
            "transactions",
            data.get("entries", []),
        )

        opening_balance = float(
            data.get("opening_balance", 0) or 0
        )

        closing_balance = float(
            data.get("closing_balance", 0) or 0
        )

        from_date = data.get("from_date")
        to_date = data.get("to_date")

        title = (
            "Customer Statement"
            if party_type == "customer"
            else "Supplier Statement"
        )

        # Show the balance direction instead of hiding
        # whether the amount is debit or credit.
        def _statement_balance(value: float) -> str:
            if value > 0:
                suffix = "Dr"
            elif value < 0:
                suffix = "Cr"
            else:
                suffix = ""

            amount = format_indian_currency(
                abs(value)
            )

            return f"{amount} {suffix}".strip()

        lines = [
            f"{title}: {party_name}",
            f"Opening Balance: {_statement_balance(opening_balance)}",
            f"Closing Balance: {_statement_balance(closing_balance)}",
        ]

        if from_date and to_date:
            lines.append(
                f"Period: {from_date} to {to_date}"
            )

        lines.append("")

        if not transactions:
            lines.append(
                "No transactions were found for this period."
            )
            return "\n".join(lines)

        for index, transaction in enumerate(
            transactions,
            start=1,
        ):
            transaction_date = (
                transaction.get("date")
                or transaction.get("voucher_date")
                or "-"
            )

            voucher_type = (
                transaction.get("voucher_type")
                or transaction.get("type")
                or "Transaction"
            )

            voucher_number = (
                transaction.get("voucher_number")
                or transaction.get("voucher_no")
                or ""
            )

            debit = float(
                transaction.get("debit", 0) or 0
            )

            credit = float(
                transaction.get("credit", 0) or 0
            )

            if debit:
                amount_text = (
                    f"{format_indian_currency(debit)} Dr"
                )
            elif credit:
                amount_text = (
                    f"{format_indian_currency(credit)} Cr"
                )
            else:
                amount = (
                    transaction.get("amount", 0)
                    or 0
                )

                amount_text = (
                    format_indian_currency(amount)
                )

            line = (
                f"{index}. {transaction_date} "
                f"- {voucher_type}"
            )

            if voucher_number:
                line += f" #{voucher_number}"

            line += f" - {amount_text}"

            lines.append(line)

        return "\n".join(lines)
    
    if tool_name == "get_input_gst":
        ledgers = data.get("ledgers", [])
        total_input_gst = float(
            data.get("total_input_gst", 0) or 0
        )

        lines = ["Input GST:"]

        # Show each Input GST ledger separately so the user
        # can understand how much belongs to CGST, SGST or IGST.
        for ledger in ledgers:
            ledger_name = ledger.get("ledger_name") or "GST Ledger"
            balance = float(
                ledger.get("closing_balance", 0) or 0
            )

            lines.append(
                f"{ledger_name}: "
                f"{format_indian_currency(abs(balance))}"
            )

        lines.append("")
        lines.append(
            f"Total Input GST: "
            f"{format_indian_currency(total_input_gst)}"
        )

        return "\n".join(lines)


    if tool_name == "get_output_gst":
        ledgers = data.get("ledgers", [])
        total_output_gst = float(
            data.get("total_output_gst", 0) or 0
        )

        lines = ["Output GST:"]

        # Show the ledger-wise breakup before showing the final total.
        for ledger in ledgers:
            ledger_name = ledger.get("ledger_name") or "GST Ledger"
            balance = float(
                ledger.get("closing_balance", 0) or 0
            )

            lines.append(
                f"{ledger_name}: "
                f"{format_indian_currency(abs(balance))}"
            )

        lines.append("")
        lines.append(
            f"Total Output GST: "
            f"{format_indian_currency(total_output_gst)}"
        )

        return "\n".join(lines)


    if tool_name == "get_gst_summary":
        total_input_gst = float(
            data.get("total_input_gst", 0) or 0
        )

        total_output_gst = float(
            data.get("total_output_gst", 0) or 0
        )

        net_gst = float(
            data.get("net_gst", 0) or 0
        )

        lines = [
            "GST Summary:",
            f"Input GST: {format_indian_currency(total_input_gst)}",
            f"Output GST: {format_indian_currency(total_output_gst)}",
            f"Net GST: {format_indian_currency(abs(net_gst))}",
        ]

        # We are only showing whether the current difference is
        # towards payment or input credit. Final accounting treatment
        # should still be verified against the Tally GST report.
        if net_gst > 0:
            lines.append("Position: GST Payable")
        elif net_gst < 0:
            lines.append("Position: Input GST Credit")
        else:
            lines.append("Position: No net GST balance")

        return "\n".join(lines)
    
    if tool_name == "get_stock_items":
        items = data.get("items", [])
        count = int(data.get("count", len(items)) or 0)

        lines = [
            f"Stock Items ({count}):"
        ]

        # Show the item name and current quantity in a simple format.
        for item in items:
            item_name = item.get("name") or "Unnamed Item"
            quantity = item.get("closing_balance") or "Not available"

            lines.append(
                f"- {item_name}: {quantity}"
            )

        return "\n".join(lines)


    if tool_name == "get_stock_summary":
        valuation_rows = data.get("valuation_rows")
        if valuation_rows is not None:
            if not valuation_rows:
                return "Tally returned no inventory valuation rows."
            lines = ["Inventory valuation from Tally:"]
            if data.get("to_date"):
                lines[0] += f" as of {data['to_date']}"
            for row in valuation_rows:
                value = row.get("value")
                value_text = (
                    format_indian_currency(value)
                    if value is not None
                    else "value not reported"
                )
                lines.append(
                    f"{row.get('name') or 'Item'}: "
                    f"{row.get('quantity') or 'quantity not reported'} "
                    f"{row.get('base_units') or ''} | {value_text}"
                )
            return "\n".join(lines)

        total_items = int(
            data.get("total_items", 0) or 0
        )

        items_with_stock = int(
            data.get("items_with_stock", 0) or 0
        )

        total_stock_value = float(
            data.get("total_stock_value", 0) or 0
        )

        lines = [
            "Stock Summary:",
            f"Total Stock Items: {total_items}",
            f"Items with Stock: {items_with_stock}",
            (
                "Stock Value: "
                f"{format_indian_currency(abs(total_stock_value))}"
            ),
        ]

        items = data.get("items") or []
        if items:
            lines.append("")
            lines.append("Items Breakdown:")
            display_limit = 25
            for item in items[:display_limit]:
                name = item.get("name") or "Stock Item"
                closing_bal = item.get("closing_balance") or "0"
                closing_rate = item.get("closing_rate") or ""
                closing_val = item.get("closing_value") or ""

                val_text = ""
                if closing_val:
                    val_text = f" | Value: {_stock_value_text(closing_val, closing_bal)}"

                rate_text = f" @ {closing_rate}" if closing_rate else ""
                lines.append(f"• {name}: {closing_bal}{rate_text}{val_text}")

            if len(items) > display_limit:
                lines.append(f"... and {len(items) - display_limit} more items.")

        return "\n".join(lines)


    if tool_name == "get_stock_item_details":
        # More than one product may match when the user
        # provides only part of the stock item name.
        if data.get("multiple_matches"):
            matches = data.get("matches", [])

            lines = [
                "I found multiple matching stock items:"
            ]

            for item in matches:
                lines.append(
                    f"- {item.get('name', 'Unnamed Item')}"
                )

            lines.append(
                "Please specify which item you want."
            )

            return "\n".join(lines)

        item = data.get("item", {})

        if not item:
            return "No stock item details were found."

        item_name = item.get("name") or "Stock Item"

        return "\n".join([
            f"Stock Item: {item_name}",
            f"Group: {item.get('parent') or 'Not available'}",
            f"Unit: {item.get('base_unit') or 'Not available'}",
            (
                f"Opening Quantity: "
                f"{item.get('opening_balance') or 'Not available'}"
            ),
            (
                f"Closing Quantity: "
                f"{item.get('closing_balance') or 'Not available'}"
            ),
            (
                f"Opening Rate: "
                f"{item.get('opening_rate') or 'Not available'}"
            ),
            (
                f"Closing Rate: "
                f"{item.get('closing_rate') or 'Not available'}"
            ),
            (
                f"Opening Value: "
                f"{_stock_value_text(item.get('opening_value'), item.get('opening_balance'))}"
            ),
            (
                f"Closing Value: "
                f"{_stock_value_text(item.get('closing_value'), item.get('closing_balance'))}"
            ),
        ])


    if tool_name == "get_top_stock_items":
        items = data.get("items", [])

        lines = [
            "Top Stock Items:"
        ]

        # Show the original quantity and value received from Tally.
        for index, item in enumerate(items, start=1):
            lines.append(
                f"{index}. "
                f"{item.get('name', 'Unnamed Item')} | "
                f"Qty: {item.get('closing_balance') or 'Not available'} | "
                f"Value: {_stock_value_text(item.get('closing_value'), item.get('closing_balance'))}"
            )

        return "\n".join(lines)


    if tool_name == "get_negative_stock_items":
        items = data.get("items", [])

        if not items:
            return "No negative stock items were found."

        lines = [
            "Negative Stock Items:"
        ]

        # Negative stock may indicate an inventory entry
        # that needs to be checked in Tally.
        for item in items:
            lines.append(
                f"- {item.get('name', 'Unnamed Item')}: "
                f"{item.get('closing_balance') or 'Not available'}"
            )

        return "\n".join(lines)


    if tool_name == "get_tds_summary":
        ledgers = data.get("ledgers", [])

        if not ledgers:
            return "No TDS ledgers were found in Tally."

        lines = [
            "TDS Summary:"
        ]

        # Show each TDS ledger separately because companies
        # can maintain different TDS sections in Tally.
        for ledger in ledgers:
            lines.append(
                f"- {ledger.get('ledger_name', 'TDS Ledger')}: "
                f"{format_indian_currency(abs(ledger.get('closing_balance', 0)))}"
            )

        lines.append(
            f"Total TDS Balance: "
            f"{format_indian_currency(data.get('total_tds', 0))}"
        )

        return "\n".join(lines)


    if tool_name == "get_tds_transactions":
        transactions = data.get("transactions", [])

        if not transactions:
            return "No TDS transactions were found for the selected period."

        lines = [
            "TDS Transactions:"
        ]

        # Keep the ledger name with every transaction so it is
        # clear which TDS section the entry belongs to.
        for entry in transactions:
            lines.append(
                f"- {entry.get('date', 'Date not available')} | "
                f"{entry.get('ledger_name', 'TDS Ledger')} | "
                f"{entry.get('voucher_type', 'Voucher')} "
                f"#{entry.get('voucher_number') or entry.get('voucher_no') or '-'} | "
                f"Debit: {format_indian_currency(abs(entry.get('debit', 0) or 0))} | "
                f"Credit: {format_indian_currency(abs(entry.get('credit', 0) or 0))}"
            )

        return "\n".join(lines)
    
    if tool_name == "get_cash_flow_summary":
        total_inflow = data.get("total_inflow", 0) or 0
        total_outflow = data.get("total_outflow", 0) or 0
        net_flow = data.get("net_flow", 0) or 0

        lines = [
            "Cash Flow Summary:",
            f"Total Inflow: {format_indian_currency(total_inflow)}",
            f"Total Outflow: {format_indian_currency(total_outflow)}",
            f"Net Cash Flow: {format_indian_currency(net_flow)}",
        ]

        transactions = data.get("transactions", [])

        if transactions:
            lines.append("")
            lines.append("Recent Cash/Bank Transactions:")

            # Show only a few transactions in the chat response
            # so the answer stays easy to read.
            for entry in transactions[:10]:
                lines.append(
                    f"- {entry.get('date', 'Date not available')} | "
                    f"{entry.get('ledger_name', 'Ledger')} | "
                    f"{entry.get('voucher_type', 'Voucher')} "
                    f"#{entry.get('voucher_number') or entry.get('voucher_no') or '-'} | "
                    f"Debit: {format_indian_currency(abs(entry.get('debit', 0) or 0))} | "
                    f"Credit: {format_indian_currency(abs(entry.get('credit', 0) or 0))}"
                )

        return "\n".join(lines)
    
    if tool_name == "get_profitability_summary":
        revenue = data.get("revenue", 0) or 0
        expenses = data.get("expenses", 0) or 0
        net_profit = data.get("net_profit", 0) or 0
        profit_margin = data.get("profit_margin", 0) or 0

        # Keep the response simple so the user can quickly
        # understand whether the business is making profit or loss.
        status = (
            "Profit"
            if net_profit >= 0
            else "Loss"
        )

        lines = [
            "Profitability Summary:",
            f"Revenue: {format_indian_currency(revenue)}",
            f"Expenses: {format_indian_currency(expenses)}",
            f"Net {status}: {format_indian_currency(abs(net_profit))}",
            f"Profit Margin: {profit_margin:.2f}%",
        ]

        return "\n".join(lines)
    
    if tool_name == "get_top_expenses":
        items = data.get("items", [])

        if not items:
            return "No expense data was found."

        lines = [
            "Top Expenses:"
        ]

        # Show the largest expense ledgers first.
        for index, item in enumerate(items, start=1):
            lines.append(
                f"{index}. "
                f"{item.get('ledger_name', 'Expense')} - "
                f"{format_indian_currency(item.get('amount', 0))}"
            )

        return "\n".join(lines)


    if tool_name == "get_top_customers":
        items = data.get("items", [])

        if not items:
            return "No customer receivables were found."

        lines = [
            "Top Customers by Outstanding:"
        ]

        for index, item in enumerate(items, start=1):
            party_name = (
                item.get("party")
                or item.get("party_name")
                or item.get("customer_name")
                or "Customer"
            )

            amount = (
                item.get("outstanding_amount", 0)
                or 0
            )

            lines.append(
                f"{index}. {party_name} - "
                f"{format_indian_currency(abs(float(amount)))}"
            )

        return "\n".join(lines)


    if tool_name == "get_top_suppliers":
        items = data.get("items", [])

        if not items:
            return "No supplier payables were found."

        lines = [
            "Top Suppliers by Outstanding:"
        ]

        for index, item in enumerate(items, start=1):
            party_name = (
                item.get("party")
                or item.get("party_name")
                or item.get("supplier_name")
                or "Supplier"
            )

            amount = (
                item.get("outstanding_amount", 0)
                or 0
            )

            lines.append(
                f"{index}. {party_name} - "
                f"{format_indian_currency(abs(float(amount)))}"
            )

        return "\n".join(lines)
    
    if tool_name == "get_period_trend":
        current = data.get("current", {})
        previous = data.get("previous", {})
        changes = data.get("changes", {})

        def format_change(value):
            if value is None:
                return "Not available"

            sign = "+" if value >= 0 else ""
            return f"{sign}{value:.2f}%"

        lines = [
            "Period Comparison:",
            "",
            "Current Period:",
            f"Revenue: {format_indian_currency(current.get('revenue', 0))}",
            f"Expenses: {format_indian_currency(current.get('expenses', 0))}",
            f"Net Profit/Loss: {format_indian_currency(current.get('net_profit', 0))}",
            "",
            "Previous Period:",
            f"Revenue: {format_indian_currency(previous.get('revenue', 0))}",
            f"Expenses: {format_indian_currency(previous.get('expenses', 0))}",
            f"Net Profit/Loss: {format_indian_currency(previous.get('net_profit', 0))}",
            "",
            "Change:",
            f"Revenue: {format_change(changes.get('revenue'))}",
            f"Expenses: {format_change(changes.get('expenses'))}",
            f"Net Profit: {format_change(changes.get('net_profit'))}",
        ]

        return "\n".join(lines)
    
    if tool_name == "get_ledger_balance":
        data = tool_result.get(
            "data",
            {},
        )

        ledger_name = data.get(
            "ledger_name",
            "Ledger",
        )

        balance = float(
            data.get(
                "closing_balance",
                0,
            )
            or 0
        )

        # Keep the raw sign from Tally for now.
        # We will reconcile Dr/Cr presentation during live testing.
        return (
            f"{ledger_name} closing balance is "
            f"{format_indian_currency(abs(balance))}."
        )


    if tool_name == "get_ledger_transactions":
        data = tool_result.get(
            "data",
            {},
        )

        ledger_name = data.get(
            "ledger_name",
            "Ledger",
        )

        count = data.get(
            "count",
            0,
        )

        opening_balance = data.get("opening_balance")
        closing_balance = data.get("closing_balance")

        lines = [
            f"{ledger_name} Transactions (from Tally):",
        ]
        if opening_balance is not None:
            lines.append(f"Opening Balance: {format_indian_currency(opening_balance)}")
        if closing_balance is not None:
            lines.append(f"Closing Balance: {format_indian_currency(closing_balance)}")
        lines.append(f"Total Transactions: {count}")

        transactions = data.get("transactions") or data.get("entries") or []
        if not transactions:
            lines.append("\nNo transactions found for the requested period.")
        else:
            lines.append("")
            display_limit = 30
            for tx in transactions[:display_limit]:
                tx_date = tx.get("date") or ""
                v_type = tx.get("voucher_type") or "Voucher"
                v_no = tx.get("voucher_number") or ""
                particulars = tx.get("particulars") or ""
                debit = float(tx.get("debit") or 0.0)
                credit = float(tx.get("credit") or 0.0)

                amount_parts = []
                if debit > 0:
                    amount_parts.append(f"{format_indian_currency(debit)} Dr")
                if credit > 0:
                    amount_parts.append(f"{format_indian_currency(credit)} Cr")
                amount_str = ", ".join(amount_parts) if amount_parts else "₹0"

                v_str = f"{v_type}" + (f" #{v_no}" if v_no else "")
                lines.append(f"• {tx_date} | {v_str} | {particulars} | {amount_str}")

            if len(transactions) > display_limit:
                lines.append(f"\n... and {len(transactions) - display_limit} more transactions.")

        return "\n".join(lines)

    if tool_name == "get_sales_by_customer":
        customers = data.get(
            "customers",
            [],
        )

        if not customers:
            return (
                "No customer-wise sales were found "
                "for the selected period."
            )

        lines = [
            "Sales by Customer:"
        ]

        # Show customer-wise net sales.
        # Credit Notes are already adjusted in the tool.
        for index, customer in enumerate(
            customers,
            start=1,
        ):
            customer_name = customer.get(
                "customer_name",
                "Customer",
            )

            net_sales = float(
                customer.get(
                    "net_sales",
                    0,
                )
                or 0
            )

            lines.append(
                f"{index}. {customer_name} - "
                f"{format_indian_currency(net_sales)}"
            )

        total_net_sales = float(
            data.get(
                "total_net_sales",
                0,
            )
            or 0
        )

        lines.append("")
        lines.append(
            f"Total Net Sales: "
            f"{format_indian_currency(total_net_sales)}"
        )

        return "\n".join(lines)


    if tool_name == "get_purchases_by_supplier":
        suppliers = data.get(
            "suppliers",
            [],
        )

        if not suppliers:
            return (
                "No supplier-wise purchases were found "
                "for the selected period."
            )

        lines = [
            "Purchases by Supplier:"
        ]

        # Show supplier-wise net purchases.
        # Debit Notes are already adjusted in the tool.
        for index, supplier in enumerate(
            suppliers,
            start=1,
        ):
            supplier_name = supplier.get(
                "supplier_name",
                "Supplier",
            )

            net_purchases = float(
                supplier.get(
                    "net_purchases",
                    0,
                )
                or 0
            )

            lines.append(
                f"{index}. {supplier_name} - "
                f"{format_indian_currency(net_purchases)}"
            )

        total_net_purchases = float(
            data.get(
                "total_net_purchases",
                0,
            )
            or 0
        )

        lines.append("")
        lines.append(
            f"Total Net Purchases: "
            f"{format_indian_currency(total_net_purchases)}"
        )

        return "\n".join(lines)
    
    if tool_name == "get_sales_by_item":
        items = data.get(
            "items",
            [],
        )

        if not items:
            return (
                "No item-wise sales were found "
                "for the selected period."
            )

        lines = [
            "Sales by Item:"
        ]

        for index, item in enumerate(
            items,
            start=1,
        ):
            item_name = item.get(
                "stock_item_name",
                "Stock Item",
            )

            net_sales = float(
                item.get(
                    "net_sales",
                    0,
                )
                or 0
            )

            lines.append(
                f"{index}. {item_name} - "
                f"{format_indian_currency(net_sales)}"
            )

        total_net_sales = float(
            data.get(
                "total_net_sales",
                0,
            )
            or 0
        )

        lines.append("")
        lines.append(
            f"Total Net Sales: "
            f"{format_indian_currency(total_net_sales)}"
        )

        return "\n".join(lines)


    if tool_name == "get_purchases_by_item":
        items = data.get(
            "items",
            [],
        )

        if not items:
            return (
                "No item-wise purchases were found "
                "for the selected period."
            )

        lines = [
            "Purchases by Item:"
        ]

        for index, item in enumerate(
            items,
            start=1,
        ):
            item_name = item.get(
                "stock_item_name",
                "Stock Item",
            )

            net_purchases = float(
                item.get(
                    "net_purchases",
                    0,
                )
                or 0
            )

            lines.append(
                f"{index}. {item_name} - "
                f"{format_indian_currency(net_purchases)}"
            )

        total_net_purchases = float(
            data.get(
                "total_net_purchases",
                0,
            )
            or 0
        )

        lines.append("")
        lines.append(
            f"Total Net Purchases: "
            f"{format_indian_currency(total_net_purchases)}"
        )

        return "\n".join(lines)
    
    if tool_name == "get_top_selling_items":
        items = data.get(
            "items",
            [],
        )

        if not items:
            return (
                "No selling item data was found "
                "for the selected period."
            )

        lines = [
            "Top-Selling Items:"
        ]

        for index, item in enumerate(
            items,
            start=1,
        ):
            lines.append(
                f"{index}. "
                f"{item.get('stock_item_name', 'Item')} - "
                f"{format_indian_currency(float(item.get('net_sales', 0) or 0))}"
            )

        return "\n".join(lines)


    if tool_name == "get_low_selling_items":
        items = data.get(
            "items",
            [],
        )

        if not items:
            return (
                "No low-selling item data was found "
                "for the selected period."
            )

        lines = [
            "Low-Selling Items:"
        ]

        for index, item in enumerate(
            items,
            start=1,
        ):
            lines.append(
                f"{index}. "
                f"{item.get('stock_item_name', 'Item')} - "
                f"{format_indian_currency(float(item.get('net_sales', 0) or 0))}"
            )

        return "\n".join(lines)
    
    if tool_name == "get_stock_movement":
        rows = data.get("rows")
        if rows is not None:
            if not rows:
                return (
                    "No stock movement was found "
                    "for the selected period."
                )

            lines = ["Stock Movement from Tally:"]
            for row in rows:
                direction = row.get("is_deemed_positive")
                if direction is True:
                    movement = "Inward"
                elif direction is False:
                    movement = "Outward"
                else:
                    movement = "Direction not reported"

                details = [
                    str(row.get("date") or "Date unavailable"),
                    str(row.get("voucher_type") or "Voucher"),
                    str(row.get("voucher_number") or ""),
                    str(row.get("stock_item") or "Item"),
                    f"{movement}: {row.get('quantity') or 'not reported'}",
                ]
                if row.get("amount") is not None:
                    details.append(
                        f"Amount: {format_indian_currency(row['amount'])}"
                    )
                lines.append(" | ".join(part for part in details if part))

            return "\n".join(lines)

        items = data.get(
            "items",
            [],
        )

        if not items:
            return (
                "No stock movement was found "
                "for the selected period."
            )

        lines = [
            "Stock Movement:"
        ]

        for index, item in enumerate(
            items,
            start=1,
        ):
            lines.append(
                f"{index}. "
                f"{item.get('stock_item_name', 'Item')} | "
                f"Inward: {item.get('inward_quantity', 0):,.3f} | "
                f"Outward: {item.get('outward_quantity', 0):,.3f} | "
                f"Net: {item.get('net_movement', 0):,.3f}"
            )

        return "\n".join(lines)

    if tool_name == "get_customer_profitability":
        customers = data.get("customers", [])

        if not customers:
            return (
                "No customer sales data was found "
                "for the selected period."
            )

        lines = ["Customer Performance:"]

        for index, customer in enumerate(
            customers,
            start=1,
        ):
            customer_name = customer.get(
                "customer_name",
                "Customer"
            )

            net_sales = float(
                customer.get("net_sales", 0) or 0
            )

            contribution = float(
                customer.get(
                    "sales_contribution_percent",
                    0
                )
                or 0
            )

            lines.append(
                f"{index}. {customer_name} | "
                f"Net Sales: {format_indian_currency(net_sales)} | "
                f"Sales Contribution: {contribution:.2f}%"
            )

        if not data.get(
            "profit_calculation_available",
            False
        ):
            lines.append(
                "\nNote: Gross profit and profit margin "
                "are not calculated because customer-specific "
                "cost data is not available."
            )

        return "\n".join(lines)
    
    if tool_name == "get_product_profitability":
        products = data.get("products", [])

        if not products:
            return (
                "No product sales data was found "
                "for the selected period."
            )

        lines = ["Product Performance:"]

        for index, product in enumerate(
            products,
            start=1,
        ):
            product_name = product.get(
                "product_name",
                "Product"
            )

            net_sales = float(
                product.get("net_sales", 0) or 0
            )

            contribution = float(
                product.get(
                    "sales_contribution_percent",
                    0
                )
                or 0
            )

            lines.append(
                f"{index}. {product_name} | "
                f"Net Sales: {format_indian_currency(net_sales)} | "
                f"Sales Contribution: {contribution:.2f}%"
            )

        if not data.get(
            "profit_calculation_available",
            False
        ):
            lines.append(
                "\nNote: Gross profit and profit margin "
                "are not calculated because product-level "
                "cost data is not available."
            )

        return "\n".join(lines)
    
    if tool_name == "get_tax_liability":
        gst = data.get("gst", {}) or {}
        tds = data.get("tds", {}) or {}

        input_tax = float(
            gst.get("input_tax", 0) or 0
        )

        output_tax = float(
            gst.get("output_tax", 0) or 0
        )

        net_gst_payable = float(
            gst.get("net_gst_payable", 0) or 0
        )

        total_tds = float(
            tds.get("total_tds", 0) or 0
        )

        lines = [
            "Tax Liability Overview:",
            "",
            f"GST Input: {format_indian_currency(input_tax)}",
            f"GST Output: {format_indian_currency(output_tax)}",
            f"Net GST Payable: {format_indian_currency(net_gst_payable)}",
            f"TDS Amount: {format_indian_currency(total_tds)}",
        ]

        note = data.get("note")

        if note:
            lines.append("")
            lines.append(f"Note: {note}")

        return "\n".join(lines)
    
    if tool_name == "get_tds_receivable":
        total = float(
            data.get("total_tds_receivable", 0) or 0
        )

        ledgers = data.get("ledgers", []) or []

        lines = [
            "TDS Receivable:",
            "",
            f"Total TDS Receivable: {format_indian_currency(total)}",
        ]

        if ledgers:
            lines.append("")
            lines.append("TDS Ledgers:")

            for ledger in ledgers:
                ledger_name = ledger.get(
                    "ledger_name",
                    "Unknown"
                )

                amount = float(
                    ledger.get(
                        "receivable_amount",
                        0
                    ) or 0
                )

                lines.append(
                    f"- {ledger_name}: {format_indian_currency(amount)}"
                )

        return "\n".join(lines)
    
    if tool_name == "get_tds_payable":
        total = float(
            data.get("total_tds_payable", 0) or 0
        )

        ledgers = data.get("ledgers", []) or []

        lines = [
            "TDS Payable:",
            "",
            f"Total TDS Payable: {format_indian_currency(total)}",
        ]

        if ledgers:
            lines.append("")
            lines.append("TDS Ledgers:")

            for ledger in ledgers:
                ledger_name = ledger.get(
                    "ledger_name",
                    "Unknown"
                )

                amount = float(
                    ledger.get(
                        "payable_amount",
                        0
                    ) or 0
                )

                lines.append(
                    f"- {ledger_name}: {format_indian_currency(amount)}"
                )

        return "\n".join(lines)
    
    if tool_name == "get_financial_trends":
        periods = data.get("periods", []) or []

        if not periods:
            return "No financial trend data was found for the selected period."

        lines = [
            "Financial Trends:",
            ""
        ]

        for period in periods:
            from_date = period.get("from_date")
            to_date = period.get("to_date")

            revenue = float(
                period.get("revenue", 0) or 0
            )

            total_expenses = float(
                period.get("total_expenses", 0) or 0
            )

            net_profit = float(
                period.get("net_profit", 0) or 0
            )

            lines.extend([
                f"{from_date} to {to_date}",
                f"Revenue: {format_indian_currency(revenue)}",
                f"Total Expenses: {format_indian_currency(total_expenses)}",
                f"Net Profit: {format_indian_currency(net_profit)}",
                "",
            ])

        return "\n".join(lines).strip()
    
    if tool_name == "get_company_comparison":
        companies = data.get("companies", []) or []

        if not companies:
            return "No company comparison data was found."

        lines = [
            "Company Comparison:",
            "",
        ]

        for company in companies:
            company_name = company.get(
                "company_name",
                "Unknown Company",
            )

            # The comparison tool returns None for a lookup that failed,
            # so a company whose data could not be read is reported as
            # unavailable instead of as a genuine zero.
            def _figure(key):
                value = company.get(key)
                if value is None:
                    return "not available"
                return f"{format_indian_currency(float(value))}"

            lines.extend([
                company_name,
                f"Revenue: {_figure('revenue')}",
                f"Total Expenses: {_figure('total_expenses')}",
                f"Net Profit: {_figure('net_profit')}",
                "",
            ])

        return "\n".join(lines).strip()
    
    if tool_name == "get_cost_centre_analysis":
        cost_centres = data.get(
            "cost_centres",
            [],
        ) or []

        if not cost_centres:
            return (
                "No cost centre allocation data was found "
                "for the selected period."
            )

        lines = [
            "Cost Centre Analysis:",
            "",
        ]

        for centre in cost_centres:
            cost_centre_name = centre.get(
                "cost_centre_name",
                "Unknown Cost Centre",
            )

            net_amount = float(
                centre.get(
                    "net_amount",
                    0,
                )
                or 0
            )

            allocation_count = int(
                centre.get(
                    "allocation_count",
                    0,
                )
                or 0
            )

            lines.extend([
                cost_centre_name,
                (
                    f"Net Allocation: "
                    f"{format_indian_currency(net_amount)}"
                ),
                (
                    f"Allocations: "
                    f"{allocation_count}"
                ),
                "",
            ])

        return "\n".join(lines).strip()
    
    if tool_name == "get_party_statement":
        party_name = data.get(
            "party_name",
            "Unknown Party",
        )

        opening_balance = float(
            data.get(
                "opening_balance",
                0,
            )
            or 0
        )

        closing_balance = float(
            data.get(
                "closing_balance",
                0,
            )
            or 0
        )

        entries = data.get(
            "entries",
            [],
        ) or []

        lines = [
            f"Statement: {party_name}",
            "",
            (
                f"Opening Balance: "
                f"{format_indian_currency(opening_balance)}"
            ),
            "",
        ]

        if not entries:
            lines.append(
                "No transactions were found "
                "for the selected period."
            )
        else:
            for entry in entries:
                date_value = entry.get(
                    "date",
                    "-"
                )

                voucher_type = entry.get(
                    "voucher_type",
                    "-"
                )

                voucher_number = entry.get(
                    "voucher_number",
                    "-"
                )

                particular = (
                    entry.get("particular")
                    or entry.get("party_name")
                    or "-"
                )

                debit = float(
                    entry.get(
                        "debit",
                        0,
                    )
                    or 0
                )

                credit = float(
                    entry.get(
                        "credit",
                        0,
                    )
                    or 0
                )

                running_balance = float(
                    entry.get(
                        "running_balance",
                        0,
                    )
                    or 0
                )

                lines.extend([
                    f"Date: {date_value}",
                    (
                        f"Voucher: {voucher_type} "
                        f"{voucher_number}"
                    ),
                    f"Particulars: {particular}",
                    (
                        f"Debit: "
                        f"{format_indian_currency(debit)}"
                    ),
                    (
                        f"Credit: "
                        f"{format_indian_currency(credit)}"
                    ),
                    (
                        f"Balance: "
                        f"{format_indian_currency(running_balance)}"
                    ),
                    "",
                ])

        lines.extend([
            (
                f"Closing Balance: "
                f"{format_indian_currency(closing_balance)}"
            ),
            (
                f"Transactions: "
                f"{len(entries)}"
            ),
        ])

        return "\n".join(lines).strip()
    
    if tool_name == "get_invoice_details" and data.get("invoices") is not None:
        invoices = data.get("invoices", []) or []
        if not invoices:
            return "No invoices matched the requested filters in Tally bill data."

        lines = [f"Invoices matching Tally bill data ({len(invoices)}):"]
        for invoice in invoices:
            amount = invoice.get("amount")
            lines.extend([
                f"{invoice.get('invoice_number') or 'Reference unavailable'} | "
                f"{invoice.get('party_name') or 'Party unavailable'} | "
                f"Date: {invoice.get('invoice_date') or 'not reported'}",
                f"Tally allocation amount: {format_indian_currency(amount) if amount is not None else 'not reported'} | "
                f"Voucher: {invoice.get('voucher_type') or 'not reported'} "
                f"{invoice.get('voucher_number') or ''}".strip(),
            ])
        return "\n".join(lines)

    if tool_name == "get_invoice_details":
        amount = data.get("original_amount")
        outstanding = data.get("outstanding_amount")
        return "\n".join([
            f"Invoice: {data.get('invoice_number') or 'Reference unavailable'}",
            f"Party: {data.get('party_name') or 'not reported by Tally'}",
            f"Date: {data.get('invoice_date') or 'not reported by Tally'}",
            f"Status: {data.get('status') or 'not available'}",
            f"Original amount: {format_indian_currency(amount) if amount is not None else 'not reported'}",
            f"Outstanding amount: {format_indian_currency(outstanding) if outstanding is not None else 'not reported'}",
        ])

    if tool_name == "get_invoice_status":
        invoice_reference = data.get(
            "invoice_reference",
            "Unknown Invoice",
        )

        matches = data.get(
            "matches",
            [],
        ) or []

        if not matches:
            return (
                f"Invoice {invoice_reference} was not found "
                "in the current outstanding data."
            )

        lines = [
            f"Invoice Status: {invoice_reference}",
            "",
        ]

        for match in matches:
            party = match.get(
                "party",
                "Unknown Party",
            )

            invoice_type = match.get(
                "invoice_type",
                "unknown",
            )

            status = match.get(
                "status",
                "unknown",
            )

            outstanding_amount = float(
                match.get(
                    "outstanding_amount",
                    0,
                )
                or 0
            )

            due_date = match.get(
                "due_date"
            )

            overdue_days = int(
                match.get(
                    "overdue_days",
                    0,
                )
                or 0
            )

            lines.extend([
                f"Party: {party}",
                (
                    f"Type: "
                    f"{invoice_type.capitalize()}"
                ),
                (
                    f"Status: "
                    f"{status.capitalize()}"
                ),
                (
                    f"Outstanding Amount: "
                    f"{format_indian_currency(outstanding_amount)}"
                ),
            ])

            if due_date:
                lines.append(
                    f"Due Date: {due_date}"
                )

            if overdue_days > 0:
                lines.append(
                    f"Overdue By: {overdue_days} days"
                )

            lines.append("")

        return "\n".join(lines).strip()
    
    if tool_name == "get_bank_transactions":
        ledger_name = data.get(
            "ledger_name",
            "Bank / Cash Ledger",
        )

        opening_balance = float(
            data.get(
                "opening_balance",
                0,
            )
            or 0
        )

        closing_balance = float(
            data.get(
                "closing_balance",
                0,
            )
            or 0
        )

        total_debit = float(
            data.get(
                "total_debit",
                0,
            )
            or 0
        )

        total_credit = float(
            data.get(
                "total_credit",
                0,
            )
            or 0
        )

        transactions = data.get(
            "transactions",
            [],
        ) or []

        lines = [
            f"{ledger_name} Transactions:",
            "",
            (
                f"Opening Balance: "
                f"{format_indian_currency(opening_balance)}"
            ),
            (
                f"Total Debit: "
                f"{format_indian_currency(total_debit)}"
            ),
            (
                f"Total Credit: "
                f"{format_indian_currency(total_credit)}"
            ),
            (
                f"Closing Balance: "
                f"{format_indian_currency(closing_balance)}"
            ),
            f"Transactions: {len(transactions)}",
        ]

        return "\n".join(lines)

    if tool_name == "get_day_book":
        rows = data.get("rows", [])
        count = data.get("count", len(rows))
        from_d = data.get("from_date")
        to_d = data.get("to_date")

        if from_d and to_d:
            if from_d == to_d:
                period_str = f"for {from_d}"
            else:
                period_str = f"from {from_d} to {to_d}"
        elif to_d:
            period_str = f"as of {to_d}"
        elif from_d:
            period_str = f"from {from_d}"
        else:
            period_str = ""

        header = f"Day Book (from Tally){(' ' + period_str) if period_str else ''}:"

        if not rows:
            return f"No vouchers found in Day Book {period_str}.".strip()

        lines = [header, f"Total Vouchers: {count}", ""]

        display_limit = 35
        for row in rows[:display_limit]:
            r_date = row.get("date") or ""
            v_type = row.get("voucher_type") or "Voucher"
            v_no = row.get("voucher_number") or ""
            particulars = row.get("particulars") or ""
            debit = float(row.get("debit") or 0.0)
            credit = float(row.get("credit") or 0.0)
            inwards = row.get("inwards_qty")
            outwards = row.get("outwards_qty")
            is_cancelled = row.get("is_cancelled")

            if is_cancelled:
                amount_str = "(Cancelled)"
            else:
                amount_parts = []
                if debit > 0:
                    amount_parts.append(f"{format_indian_currency(debit)} Dr")
                if credit > 0:
                    amount_parts.append(f"{format_indian_currency(credit)} Cr")
                if inwards:
                    amount_parts.append(f"In: {inwards}")
                if outwards:
                    amount_parts.append(f"Out: {outwards}")
                amount_str = ", ".join(amount_parts) if amount_parts else "₹0"

            v_str = f"{v_type}" + (f" #{v_no}" if v_no else "")
            lines.append(f"• {r_date} | {v_str} | {particulars} | {amount_str}")

        if len(rows) > display_limit:
            lines.append(f"\n... and {len(rows) - display_limit} more vouchers.")

        return "\n".join(lines)

    # Keep this fallback at the end.
    # It is used only when no specific formatter exists for the tool.
    return (
        "The requested financial data was "
        "retrieved successfully from Tally."
    )
    
    
    
