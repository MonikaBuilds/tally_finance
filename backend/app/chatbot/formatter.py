def format_indian_currency(value) -> str:
    try:
        amount = float(value or 0)
    except (TypeError, ValueError):
        amount = 0.0

    negative = amount < 0
    amount = abs(amount)

    integer_part = int(round(amount))
    number = str(integer_part)

    if len(number) <= 3:
        formatted = number
    else:
        last_three = number[-3:]
        remaining = number[:-3]

        groups = []

        while len(remaining) > 2:
            groups.insert(
                0,
                remaining[-2:]
            )
            remaining = remaining[:-2]

        if remaining:
            groups.insert(
                0,
                remaining
            )

        formatted = (
            ",".join(groups)
            + ","
            + last_three
        )

    prefix = "-₹" if negative else "₹"

    return f"{prefix}{formatted}"


def format_tool_response(
    tool_name: str,
    tool_result: dict
) -> str:
    if not tool_result.get("success"):
        return tool_result.get(
            "message",
            "Unable to retrieve the requested data from Tally."
        )

    if tool_result.get("source") != "tally":
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

        return (
            f"Your total outstanding receivables are "
            f"{format_indian_currency(total)} "
            f"across {count} pending bill(s)."
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

        return (
            f"Your total outstanding payables are "
            f"{format_indian_currency(total)} "
            f"across {count} pending bill(s)."
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

    if tool_name == "get_revenue":
        revenue = data.get(
            "revenue",
            0
        )

        return (
            f"Your revenue is "
            f"{format_indian_currency(revenue)}."
        )

    if tool_name == "get_expenses":
        expenses = data.get(
            "expenses",
            0
        )

        return (
            f"Your total expenses are "
            f"{format_indian_currency(expenses)}."
        )

    if tool_name == "get_net_profit":
        result_type = data.get(
            "result_type"
        )

        amount = data.get(
            "amount",
            0
        )

        if result_type == "loss":
            return (
                f"You currently have a net loss of "
                f"{format_indian_currency(amount)}."
            )

        return (
            f"You currently have a net profit of "
            f"{format_indian_currency(amount)}."
        )

    if tool_name == "get_profit_loss":
        count = data.get(
            "count",
            0
        )

        return (
            f"The Profit & Loss report was retrieved "
            f"successfully from Tally with "
            f"{count} item(s)."
        )

    if tool_name == "get_trial_balance":
        count = data.get(
            "count",
            0
        )

        return (
            f"The Trial Balance was retrieved "
            f"successfully from Tally with "
            f"{count} item(s)."
        )

    if tool_name == "get_balance_sheet":
        count = data.get(
            "count",
            0
        )

        return (
            f"The Balance Sheet was retrieved "
            f"successfully from Tally with "
            f"{count} item(s)."
        )

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
        revenue = data.get("revenue", 0)
        expenses = data.get("expenses", 0)
        net_profit = data.get("net_profit", 0)
        receivables = data.get("receivables", 0)
        payables = data.get("payables", 0)
        pending_invoices = data.get("pending_invoices", 0)

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
            f"Revenue: {format_indian_currency(revenue)}",
            f"Expenses: {format_indian_currency(expenses)}",
        ])

        if net_profit >= 0:
            lines.append(
                f"Net profit: {format_indian_currency(net_profit)}"
            )
        else:
            lines.append(
                f"Net loss: {format_indian_currency(abs(net_profit))}"
            )

        lines.extend([
            f"Receivables: {format_indian_currency(receivables)}",
            f"Payables: {format_indian_currency(payables)}",
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

        return (
            f"{ledger_name}: opening balance "
            f"{_format_tally_balance(opening_balance)}, "
            f"{entry_count} transaction(s) found in the selected period, "
            f"closing balance "
            f"{_format_tally_balance(closing_balance)}."
        )
        
    if tool_name == "get_cash_balance":
        ledger_name = data.get(
            "ledger_name"
        )

        if ledger_name:
            balance = data.get(
                "closing_balance",
                0
            )

            return (
                f"The current balance of {ledger_name} is "
                f"{format_indian_currency(balance)}."
            )

        total_balance = data.get(
            "total_balance",
            0
        )

        ledger_count = data.get(
            "ledger_count",
            0
        )

        ledgers = data.get(
            "ledgers",
            []
        )

        if ledger_count == 1 and ledgers:
            # Use the already calculated total balance here.
            # The tool has already converted Tally's debit sign correctly.
            return (
                f"Your current cash balance is "
                f"{format_indian_currency(total_balance)}."
            )

        lines = [
            (
                f"Your total cash balance is "
                f"{format_indian_currency(total_balance)} "
                f"across {ledger_count} cash ledger(s)."
            )
        ]

        for ledger in ledgers:
            name = ledger.get(
                "name",
                "Cash"
            )

            # Tally may return cash debit balances as negative values.
            # Show them as positive available cash amounts.
            balance = abs(
                ledger.get(
                    "closing_balance",
                    0
                )
            )

            lines.append(
                f"{name}: "
                f"{format_indian_currency(balance)}"
            )

        return "\n".join(lines)

    if tool_name == "get_cash_balance":
        ledger_name = data.get(
            "ledger_name"
        )

        if ledger_name:
            balance = data.get(
                "closing_balance",
                0
            )

            return (
                f"The current balance of {ledger_name} is "
                f"{format_indian_currency(balance)}."
            )

        total_balance = data.get(
            "total_balance",
            0
        )

        ledger_count = data.get(
            "ledger_count",
            0
        )

        ledgers = data.get(
            "ledgers",
            []
        )

        if ledger_count == 1 and ledgers:
            ledger = ledgers[0]

            return (
                f"Your current cash balance is "
                f"{format_indian_currency(
                    ledger.get('closing_balance', 0)
                )}."
            )

        lines = [
            (
                f"Your total cash balance is "
                f"{format_indian_currency(total_balance)} "
                f"across {ledger_count} cash ledger(s)."
            )
        ]

        for ledger in ledgers:
            name = ledger.get(
                "name",
                "Cash"
            )

            balance = ledger.get(
                "closing_balance",
                0
            )

            lines.append(
                f"{name}: "
                f"{format_indian_currency(balance)}"
            )

        return "\n".join(lines)


    if tool_name == "get_bank_balance":
        ledger_name = data.get(
            "ledger_name"
        )

        if ledger_name:
            balance = data.get(
                "closing_balance",
                0
            )

            return (
                f"The current balance of {ledger_name} is "
                f"{format_indian_currency(balance)}."
            )

        total_balance = data.get(
            "total_balance",
            0
        )

        ledger_count = data.get(
            "ledger_count",
            0
        )

        ledgers = data.get(
            "ledgers",
            []
        )

        lines = [
            (
                f"Your total bank balance is "
                f"{format_indian_currency(total_balance)} "
                f"across {ledger_count} bank account(s)."
            )
        ]

        for ledger in ledgers:
            name = ledger.get(
                "name",
                "Bank account"
            )

            # Tally returns normal bank debit balances with a negative sign.
            # Reverse that sign before showing the balance to the user.
            balance = -float(
                ledger.get(
                    "closing_balance",
                    0
                )
            )

            lines.append(
                f"{name}: "
                f"{format_indian_currency(balance)}"
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
        total_items = int(
            data.get("total_items", 0) or 0
        )

        items_with_stock = int(
            data.get("items_with_stock", 0) or 0
        )

        total_stock_value = float(
            data.get("total_stock_value", 0) or 0
        )

        return "\n".join([
            "Stock Summary:",
            f"Total Stock Items: {total_items}",
            f"Items with Stock: {items_with_stock}",
            (
                "Stock Value: "
                f"{format_indian_currency(abs(total_stock_value))}"
            ),
        ])


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
                f"{item.get('opening_value') or 'Not available'}"
            ),
            (
                f"Closing Value: "
                f"{item.get('closing_value') or 'Not available'}"
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
                f"Value: {item.get('closing_value') or 'Not available'}"
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
                f"₹{abs(ledger.get('closing_balance', 0)):,.2f}"
            )

        lines.append(
            f"Total TDS Balance: "
            f"₹{data.get('total_tds', 0):,.2f}"
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
                f"Debit: ₹{abs(entry.get('debit', 0) or 0):,.2f} | "
                f"Credit: ₹{abs(entry.get('credit', 0) or 0):,.2f}"
            )

        return "\n".join(lines)
    
    if tool_name == "get_cash_flow_summary":
        total_inflow = data.get("total_inflow", 0) or 0
        total_outflow = data.get("total_outflow", 0) or 0
        net_flow = data.get("net_flow", 0) or 0

        lines = [
            "Cash Flow Summary:",
            f"Total Inflow: ₹{total_inflow:,.2f}",
            f"Total Outflow: ₹{total_outflow:,.2f}",
            f"Net Cash Flow: ₹{net_flow:,.2f}",
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
                    f"Debit: ₹{abs(entry.get('debit', 0) or 0):,.2f} | "
                    f"Credit: ₹{abs(entry.get('credit', 0) or 0):,.2f}"
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
            f"Revenue: ₹{revenue:,.2f}",
            f"Expenses: ₹{expenses:,.2f}",
            f"Net {status}: ₹{abs(net_profit):,.2f}",
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
                f"₹{item.get('amount', 0):,.2f}"
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
                f"₹{abs(float(amount)):,.2f}"
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
                f"₹{abs(float(amount)):,.2f}"
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
            f"Revenue: ₹{current.get('revenue', 0):,.2f}",
            f"Expenses: ₹{current.get('expenses', 0):,.2f}",
            f"Net Profit/Loss: ₹{current.get('net_profit', 0):,.2f}",
            "",
            "Previous Period:",
            f"Revenue: ₹{previous.get('revenue', 0):,.2f}",
            f"Expenses: ₹{previous.get('expenses', 0):,.2f}",
            f"Net Profit/Loss: ₹{previous.get('net_profit', 0):,.2f}",
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
            f"₹{abs(balance):,.2f}."
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

        closing_balance = data.get(
            "closing_balance"
        )

        if closing_balance is None:
            closing_balance_text = (
                "not available in the Tally response"
            )
        else:
            closing_balance_text = (
                f"₹{closing_balance:,.2f}"
            )

        return (
            f"{ledger_name} has {count} transaction(s) "
            f"for the requested period. "
            f"Closing balance is "
            f"{closing_balance_text}."
        )

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
                f"₹{net_sales:,.2f}"
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
            f"₹{total_net_sales:,.2f}"
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
                f"₹{net_purchases:,.2f}"
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
            f"₹{total_net_purchases:,.2f}"
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
                f"₹{net_sales:,.2f}"
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
            f"₹{total_net_sales:,.2f}"
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
                f"₹{net_purchases:,.2f}"
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
            f"₹{total_net_purchases:,.2f}"
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
                f"₹{float(item.get('net_sales', 0) or 0):,.2f}"
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
                f"₹{float(item.get('net_sales', 0) or 0):,.2f}"
            )

        return "\n".join(lines)
    
    if tool_name == "get_stock_movement":
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
                f"Net Sales: ₹{net_sales:,.2f} | "
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
                f"Net Sales: ₹{net_sales:,.2f} | "
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

        combined_tax_amount = float(
            data.get("combined_tax_amount", 0) or 0
        )

        lines = [
            "Tax Liability Overview:",
            "",
            f"GST Input: ₹{input_tax:,.2f}",
            f"GST Output: ₹{output_tax:,.2f}",
            f"Net GST Payable: ₹{net_gst_payable:,.2f}",
            f"TDS Amount: ₹{total_tds:,.2f}",
            f"Combined Tax Amount: ₹{combined_tax_amount:,.2f}",
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
            f"Total TDS Receivable: ₹{total:,.2f}",
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
                    f"- {ledger_name}: ₹{amount:,.2f}"
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
            f"Total TDS Payable: ₹{total:,.2f}",
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
                    f"- {ledger_name}: ₹{amount:,.2f}"
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
                f"Revenue: ₹{revenue:,.2f}",
                f"Total Expenses: ₹{total_expenses:,.2f}",
                f"Net Profit: ₹{net_profit:,.2f}",
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

            revenue = float(
                company.get(
                    "revenue",
                    0,
                )
                or 0
            )

            total_expenses = float(
                company.get(
                    "total_expenses",
                    0,
                )
                or 0
            )

            net_profit = float(
                company.get(
                    "net_profit",
                    0,
                )
                or 0
            )

            lines.extend([
                company_name,
                f"Revenue: ₹{revenue:,.2f}",
                f"Total Expenses: ₹{total_expenses:,.2f}",
                f"Net Profit: ₹{net_profit:,.2f}",
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
    # Keep this fallback at the end.
    # It is used only when no specific formatter exists for the tool.
    return (
        "The requested financial data was "
        "retrieved successfully from Tally."
    )
    
    
    
