dashboard_summary = {
    "company": "Demo Enterprises",
    "period": {
        "from": "2026-08-01",
        "to": "2026-08-24"
    },
    "revenue": 850000,
    "expenses": 520000,
    "net_profit": 330000,
    "receivables": 275000,
    "payables": 180000
}


profit_loss = {
    "revenue": 850000,
    "expenses": {
        "purchases": 250000,
        "salary": 120000,
        "rent": 50000,
        "other_expenses": 100000
    },
    "total_expenses": 520000,
    "net_profit": 330000
}


receivables = {
    "total": 275000,
    "customers": [
        {
            "customer": "ABC Traders",
            "outstanding": 150000
        },
        {
            "customer": "XYZ Pvt Ltd",
            "outstanding": 125000
        }
    ]
}


payables = {
    "total": 180000,
    "suppliers": [
        {
            "supplier": "Sharma Enterprises",
            "outstanding": 100000
        },
        {
            "supplier": "Tech Solutions",
            "outstanding": 80000
        }
    ]
}


pending_invoices = [
    {
        "invoice_number": "INV-1001",
        "customer": "ABC Traders",
        "invoice_date": "2026-08-05",
        "due_date": "2026-08-20",
        "invoice_amount": 120000,
        "outstanding_amount": 70000,
        "status": "overdue"
    },
    {
        "invoice_number": "INV-1002",
        "customer": "XYZ Pvt Ltd",
        "invoice_date": "2026-08-10",
        "due_date": "2026-08-30",
        "invoice_amount": 90000,
        "outstanding_amount": 55000,
        "status": "pending"
    }
]
trial_balance = [
    {
        "ledger": "Cash",
        "debit": 150000,
        "credit": 0
    },
    {
        "ledger": "Bank",
        "debit": 250000,
        "credit": 0
    },
    {
        "ledger": "Sales",
        "debit": 0,
        "credit": 850000
    },
    {
        "ledger": "Purchases",
        "debit": 250000,
        "credit": 0
    }
]


balance_sheet = {
    "assets": {
        "cash": 150000,
        "bank": 250000,
        "receivables": 275000,
        "inventory": 200000
    },
    "liabilities": {
        "payables": 180000,
        "loan": 100000
    },
    "capital": 595000
}