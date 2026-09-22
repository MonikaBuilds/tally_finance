from collections import defaultdict


def build_outstanding_summary(bill_allocations):
    grouped = defaultdict(lambda: {
        "party": "",
        "bill_reference": "",
        "bill_date": None,
        "original_voucher_type": None,
        "original_voucher_number": None,
        "balance": 0.0,
        "transactions": []
    })

    for bill in bill_allocations:
        party = bill.get("party", "").strip()
        reference = bill.get("bill_reference", "").strip()

        if not party or not reference:
            continue

        key = (party.lower(), reference.lower())
        item = grouped[key]

        item["party"] = party
        item["bill_reference"] = reference

        amount = float(bill.get("amount", 0) or 0)
        item["balance"] += amount

        item["transactions"].append({
            "voucher_type": bill.get("voucher_type"),
            "voucher_number": bill.get("voucher_number"),
            "voucher_date": bill.get("voucher_date"),
            "bill_type": bill.get("bill_type"),
            "amount": amount,
            "guid": bill.get("guid")
        })

        # New Ref tells us where the bill originally came from.
        if bill.get("bill_type", "").strip().lower() == "new ref":
            item["bill_date"] = bill.get("bill_date")
            item["original_voucher_type"] = bill.get("voucher_type")
            item["original_voucher_number"] = bill.get("voucher_number")

    result = []

    for item in grouped.values():
        balance = round(item["balance"], 2)
        item["balance"] = balance

        original_type = (
            item["original_voucher_type"] or ""
        ).strip().lower()

        if abs(balance) < 0.01:
            item["status"] = "settled"
            item["type"] = "settled"
            item["outstanding_amount"] = 0.0

        elif original_type == "sales":
            item["status"] = "pending"
            item["type"] = "receivable"
            item["outstanding_amount"] = abs(balance)

        elif original_type == "purchase":
            item["status"] = "pending"
            item["type"] = "payable"
            item["outstanding_amount"] = abs(balance)

        else:
            # We do not assume the accounting meaning of other voucher types.
            item["status"] = "pending"
            item["type"] = "unclassified"
            item["outstanding_amount"] = abs(balance)

        result.append(item)

    return result


def get_receivables(outstanding_bills):
    items = [
        bill
        for bill in outstanding_bills
        if bill["type"] == "receivable"
        and bill["status"] == "pending"
    ]

    total = sum(
        bill["outstanding_amount"]
        for bill in items
    )

    return {
        "total_receivable": round(total, 2),
        "count": len(items),
        "bills": items
    }


def get_payables(outstanding_bills):
    items = [
        bill
        for bill in outstanding_bills
        if bill["type"] == "payable"
        and bill["status"] == "pending"
    ]

    total = sum(
        bill["outstanding_amount"]
        for bill in items
    )

    return {
        "total_payable": round(total, 2),
        "count": len(items),
        "bills": items
    }


def get_pending_invoices(outstanding_bills):
    items = [
        bill
        for bill in outstanding_bills
        if bill["status"] == "pending"
        and bill["type"] in ("receivable", "payable")
    ]

    return {
        "count": len(items),
        "invoices": items
    }
    
def build_receivables_from_tally_report(
    tally_bills,
    outstanding_bills
):
    existing = {
        (
            bill.get("party", "").strip().lower(),
            bill.get("bill_reference", "").strip().lower()
        ): bill
        for bill in outstanding_bills
    }

    items = []

    for tally_bill in tally_bills:
        party = tally_bill.get("party", "").strip()
        reference = tally_bill.get(
            "bill_reference",
            ""
        ).strip()

        if not party or not reference:
            continue

        key = (
            party.lower(),
            reference.lower()
        )

        old_bill = existing.get(key, {})

        amount = float(
            tally_bill.get(
                "outstanding_amount",
                0
            ) or 0
        )

        items.append({
            "party": party,
            "bill_reference": reference,
            "bill_date": tally_bill.get(
                "bill_date"
            ),
            "original_voucher_type": old_bill.get(
                "original_voucher_type"
            ),
            "original_voucher_number": old_bill.get(
                "original_voucher_number"
            ),
            "balance": -abs(amount),
            "transactions": old_bill.get(
                "transactions",
                []
            ),
            "status": "pending",
            "type": "receivable",
            "outstanding_amount": abs(amount),
            "due_date": tally_bill.get(
                "due_date"
            ),
            "overdue_days": tally_bill.get(
                "overdue_days",
                0
            )
        })

    total = sum(
        bill["outstanding_amount"]
        for bill in items
    )

    return {
        "total_receivable": round(total, 2),
        "count": len(items),
        "bills": items
    }


def build_payables_from_tally_report(
    tally_bills,
    outstanding_bills
):
    existing = {
        (
            bill.get("party", "").strip().lower(),
            bill.get("bill_reference", "").strip().lower()
        ): bill
        for bill in outstanding_bills
    }

    items = []

    for tally_bill in tally_bills:
        party = tally_bill.get("party", "").strip()
        reference = tally_bill.get(
            "bill_reference",
            ""
        ).strip()

        if not party or not reference:
            continue

        key = (
            party.lower(),
            reference.lower()
        )

        old_bill = existing.get(key, {})

        amount = float(
            tally_bill.get(
                "outstanding_amount",
                0
            ) or 0
        )

        items.append({
            "party": party,
            "bill_reference": reference,
            "bill_date": tally_bill.get(
                "bill_date"
            ),
            "original_voucher_type": old_bill.get(
                "original_voucher_type"
            ),
            "original_voucher_number": old_bill.get(
                "original_voucher_number"
            ),
            "balance": abs(amount),
            "transactions": old_bill.get(
                "transactions",
                []
            ),
            "status": "pending",
            "type": "payable",
            "outstanding_amount": abs(amount),
            "due_date": tally_bill.get(
                "due_date"
            ),
            "overdue_days": tally_bill.get(
                "overdue_days",
                0
            )
        })

    total = sum(
        bill["outstanding_amount"]
        for bill in items
    )

    return {
        "total_payable": round(total, 2),
        "count": len(items),
        "bills": items
    }
    
def build_pending_invoices_from_reports(
    receivables_data,
    payables_data
):
    invoices = []

    invoices.extend(
        receivables_data.get("bills", [])
    )

    invoices.extend(
        payables_data.get("bills", [])
    )

    return {
        "count": len(invoices),
        "invoices": invoices
    }