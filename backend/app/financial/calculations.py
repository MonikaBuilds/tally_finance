import re


def normalize_account_name(value):
    """
    Normalize Tally report names so small formatting
    differences do not break account matching.

    Example:
    'Cost of Sales :'
    'Cost of Sales:'
    'cost of sales'

    All become:
    'cost of sales'
    """
    if not value:
        return ""

    value = value.strip().lower()

    # Remove punctuation such as ":" while keeping
    # letters, numbers and spaces.
    value = re.sub(
        r"[^a-z0-9\s]",
        " ",
        value
    )

    # Remove extra spaces.
    return " ".join(
        value.split()
    )


def find_report_value(
    report,
    account_name,
    field="main_amount"
):
    """
    Find a particular value from a Tally report
    using a normalized account/report name.
    """

    expected_name = normalize_account_name(
        account_name
    )

    for item in report:
        actual_name = normalize_account_name(
            item.get("name", "")
        )

        if actual_name != expected_name:
            continue

        value = item.get(field)

        if value is not None:
            return float(value)

    return 0.0


def build_dashboard_financials(
    profit_loss,
    receivables,
    payables,
    pending_invoices
):
    """
    Build the financial values required by
    the existing dashboard API response.
    """

    sales = find_report_value(
        profit_loss,
        "Sales Accounts"
    )

    cost_of_sales = find_report_value(
        profit_loss,
        "Cost of Sales"
    )

    indirect_expenses = find_report_value(
        profit_loss,
        "Indirect Expenses"
    )

    revenue = abs(
        sales
    )

    total_expenses = (
        abs(cost_of_sales)
        + abs(indirect_expenses)
    )

    net_profit = (
        revenue
        - total_expenses
    )

    return {
        "revenue": round(
            revenue,
            2
        ),
        "expenses": round(
            total_expenses,
            2
        ),
        "net_profit": round(
            net_profit,
            2
        ),
        "receivables": round(
            receivables.get(
                "total_receivable",
                0
            ),
            2
        ),
        "payables": round(
            payables.get(
                "total_payable",
                0
            ),
            2
        ),
        "pending_invoices": pending_invoices.get(
            "count",
            0
        )
    }