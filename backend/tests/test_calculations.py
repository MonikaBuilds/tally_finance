from app.financial.service import (
    build_outstanding_summary,
    get_receivables,
    get_payables,
    get_pending_invoices,
    build_receivables_from_tally_report,
    build_payables_from_tally_report,
    build_pending_invoices_from_reports
)


def test_build_outstanding_summary_receivable():
    allocations = [
        {
            "party": "Test Customer",
            "bill_reference": "INV-001",
            "bill_type": "New Ref",
            "bill_date": "2026-01-01",
            "amount": -1000.0,
            "voucher_type": "Sales",
            "voucher_number": "S-001",
            "voucher_date": "2026-01-01",
            "guid": "test-sales-guid"
        },
        {
            "party": "Test Customer",
            "bill_reference": "INV-001",
            "bill_type": "Agst Ref",
            "bill_date": "2026-01-01",
            "amount": 400.0,
            "voucher_type": "Receipt",
            "voucher_number": "R-001",
            "voucher_date": "2026-01-10",
            "guid": "test-receipt-guid"
        }
    ]

    result = build_outstanding_summary(
        allocations
    )

    assert len(result) == 1

    bill = result[0]

    assert bill["party"] == "Test Customer"
    assert bill["bill_reference"] == "INV-001"

    # -1000 + 400 = -600
    assert bill["balance"] == -600.0

    assert bill["type"] == "receivable"
    assert bill["status"] == "pending"
    assert bill["outstanding_amount"] == 600.0

    assert len(bill["transactions"]) == 2


def test_build_outstanding_summary_payable():
    allocations = [
        {
            "party": "Test Supplier",
            "bill_reference": "PUR-001",
            "bill_type": "New Ref",
            "bill_date": "2026-01-01",
            "amount": 2000.0,
            "voucher_type": "Purchase",
            "voucher_number": "P-001",
            "voucher_date": "2026-01-01",
            "guid": "test-purchase-guid"
        },
        {
            "party": "Test Supplier",
            "bill_reference": "PUR-001",
            "bill_type": "Agst Ref",
            "bill_date": "2026-01-01",
            "amount": -500.0,
            "voucher_type": "Payment",
            "voucher_number": "PAY-001",
            "voucher_date": "2026-01-10",
            "guid": "test-payment-guid"
        }
    ]

    result = build_outstanding_summary(
        allocations
    )

    assert len(result) == 1

    bill = result[0]

    # 2000 - 500 = 1500
    assert bill["balance"] == 1500.0

    assert bill["type"] == "payable"
    assert bill["status"] == "pending"
    assert bill["outstanding_amount"] == 1500.0

    assert len(bill["transactions"]) == 2


def test_settled_bill():
    allocations = [
        {
            "party": "Test Customer",
            "bill_reference": "INV-002",
            "bill_type": "New Ref",
            "bill_date": "2026-02-01",
            "amount": -1000.0,
            "voucher_type": "Sales",
            "voucher_number": "S-002",
            "voucher_date": "2026-02-01",
            "guid": "test-sales-guid-2"
        },
        {
            "party": "Test Customer",
            "bill_reference": "INV-002",
            "bill_type": "Agst Ref",
            "bill_date": "2026-02-01",
            "amount": 1000.0,
            "voucher_type": "Receipt",
            "voucher_number": "R-002",
            "voucher_date": "2026-02-10",
            "guid": "test-receipt-guid-2"
        }
    ]

    result = build_outstanding_summary(
        allocations
    )

    assert len(result) == 1

    bill = result[0]

    assert bill["balance"] == 0.0
    assert bill["status"] == "settled"
    assert bill["type"] == "settled"
    assert bill["outstanding_amount"] == 0.0


def test_get_receivables():
    outstanding = [
        {
            "type": "receivable",
            "status": "pending",
            "outstanding_amount": 600.0
        },
        {
            "type": "payable",
            "status": "pending",
            "outstanding_amount": 1500.0
        }
    ]

    result = get_receivables(
        outstanding
    )

    assert result["total_receivable"] == 600.0
    assert result["count"] == 1
    assert len(result["bills"]) == 1


def test_get_payables():
    outstanding = [
        {
            "type": "receivable",
            "status": "pending",
            "outstanding_amount": 600.0
        },
        {
            "type": "payable",
            "status": "pending",
            "outstanding_amount": 1500.0
        }
    ]

    result = get_payables(
        outstanding
    )

    assert result["total_payable"] == 1500.0
    assert result["count"] == 1
    assert len(result["bills"]) == 1


def test_get_pending_invoices():
    outstanding = [
        {
            "type": "receivable",
            "status": "pending",
            "outstanding_amount": 600.0
        },
        {
            "type": "payable",
            "status": "pending",
            "outstanding_amount": 1500.0
        },
        {
            "type": "settled",
            "status": "settled",
            "outstanding_amount": 0.0
        }
    ]

    result = get_pending_invoices(
        outstanding
    )

    assert result["count"] == 2
    assert len(result["invoices"]) == 2


def test_build_receivables_from_tally_report():
    tally_bills = [
        {
            "party": "Test Customer",
            "bill_reference": "INV-001",
            "bill_date": "2026-01-01",
            "outstanding_amount": 600.0,
            "due_date": "2026-01-15",
            "overdue_days": 10,
            "type": "receivable"
        }
    ]

    calculated_outstanding = [
        {
            "party": "Test Customer",
            "bill_reference": "INV-001",
            "bill_date": "2026-01-01",
            "original_voucher_type": "Sales",
            "original_voucher_number": "S-001",
            "balance": -600.0,
            "transactions": [
                {
                    "voucher_type": "Sales",
                    "voucher_number": "S-001"
                },
                {
                    "voucher_type": "Receipt",
                    "voucher_number": "R-001"
                }
            ],
            "status": "pending",
            "type": "receivable",
            "outstanding_amount": 600.0
        }
    ]

    result = build_receivables_from_tally_report(
        tally_bills,
        calculated_outstanding
    )

    assert result["total_receivable"] == 600.0
    assert result["count"] == 1

    bill = result["bills"][0]

    assert bill["party"] == "Test Customer"
    assert bill["bill_reference"] == "INV-001"

    # Important:
    # final outstanding amount should come from
    # the Tally report.
    assert bill["outstanding_amount"] == 600.0

    assert bill["due_date"] == "2026-01-15"
    assert bill["overdue_days"] == 10

    # Extra transaction information should
    # still be preserved.
    assert bill["original_voucher_type"] == "Sales"
    assert bill["original_voucher_number"] == "S-001"
    assert len(bill["transactions"]) == 2


def test_build_payables_from_tally_report():
    tally_bills = [
        {
            "party": "Test Supplier",
            "bill_reference": "PUR-001",
            "bill_date": "2026-01-01",
            "outstanding_amount": 1500.0,
            "due_date": "2026-01-20",
            "overdue_days": 5,
            "type": "payable"
        }
    ]

    calculated_outstanding = [
        {
            "party": "Test Supplier",
            "bill_reference": "PUR-001",
            "bill_date": "2026-01-01",
            "original_voucher_type": "Purchase",
            "original_voucher_number": "P-001",
            "balance": 1500.0,
            "transactions": [
                {
                    "voucher_type": "Purchase",
                    "voucher_number": "P-001"
                },
                {
                    "voucher_type": "Payment",
                    "voucher_number": "PAY-001"
                }
            ],
            "status": "pending",
            "type": "payable",
            "outstanding_amount": 1500.0
        }
    ]

    result = build_payables_from_tally_report(
        tally_bills,
        calculated_outstanding
    )

    assert result["total_payable"] == 1500.0
    assert result["count"] == 1

    bill = result["bills"][0]

    assert bill["party"] == "Test Supplier"
    assert bill["bill_reference"] == "PUR-001"
    assert bill["outstanding_amount"] == 1500.0

    assert bill["due_date"] == "2026-01-20"
    assert bill["overdue_days"] == 5

    assert bill["original_voucher_type"] == "Purchase"
    assert bill["original_voucher_number"] == "P-001"
    assert len(bill["transactions"]) == 2


def test_build_pending_invoices_from_reports():
    receivables = {
        "total_receivable": 600.0,
        "count": 1,
        "bills": [
            {
                "party": "Test Customer",
                "bill_reference": "INV-001",
                "type": "receivable",
                "outstanding_amount": 600.0
            }
        ]
    }

    payables = {
        "total_payable": 1500.0,
        "count": 1,
        "bills": [
            {
                "party": "Test Supplier",
                "bill_reference": "PUR-001",
                "type": "payable",
                "outstanding_amount": 1500.0
            }
        ]
    }

    result = build_pending_invoices_from_reports(
        receivables,
        payables
    )

    assert result["count"] == 2
    assert len(result["invoices"]) == 2

    assert (
        result["invoices"][0]["type"]
        == "receivable"
    )

    assert (
        result["invoices"][1]["type"]
        == "payable"
    )