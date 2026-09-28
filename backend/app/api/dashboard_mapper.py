"""Dashboard mapping from native report values, with field-level provenance."""

from app.tally.parsers.common import to_optional_float

UNAVAILABLE = 'Direct authoritative Tally value not currently available through the verified request.'


def exact_row(rows, *names):
    names = {name.casefold() for name in names}
    matches = [row for row in rows or [] if (row.get('reserved_name') or row.get('name') or '').casefold() in names]
    return matches[0] if len(matches) == 1 else None


def purchase_row(rows):
    # Preserve the verified Purchase label; never use a trading total instead.
    return exact_row(rows, 'Add: Purchase Accounts') or exact_row(rows, 'Purchase Accounts')


def map_dashboard_summary(reports, start, end, company):
    sources = {}

    def metric(key, row, report, *, period=True, reason=None):
        value = row.get('amount') if row else None
        sources[key] = {
            'report': report, 'label': row.get('name') if row else None,
            'field': row.get('field') if row else None, 'raw': row.get('raw') if row else None,
            'from_date': start.isoformat() if period else None, 'to_date': end.isoformat(),
            'status': 'available' if value is not None else 'unavailable',
            'message': None if value is not None else (reason or UNAVAILABLE),
        }
        return value

    pl = reports.get('profit_loss', [])
    data = {
        'total_sales': metric('total_sales', exact_row(pl, 'Sales Accounts'), 'Profit and Loss'),
        'total_purchases': metric('total_purchases', purchase_row(pl), 'Profit and Loss'),
    }
    native_pl = reports.get('profit_loss_totals', {})
    period_matches = (
        native_pl.get('from_date') == start.isoformat()
        and native_pl.get('to_date') == end.isoformat()
        and any(company in row for row in native_pl.get('rows', []))
    )
    for key, names in [('net_profit', ('Net Profit', 'Nett Profit')), ('net_loss', ('Net Loss', 'Nett Loss'))]:
        matches = []
        if period_matches:
            for cells in native_pl['rows']:
                nonempty = [cell for cell in cells if cell]
                if len(nonempty) == 2 and nonempty[0] in names:
                    matches.append({'name': nonempty[0], 'amount': to_optional_float(nonempty[1]), 'raw': nonempty[1], 'field': 'HTML result row'})
        reason = None if period_matches else 'Tally returned a different or unverified P&L period; its net result is not used for the selected dates.'
        data[key] = metric(key, matches[0] if len(matches) == 1 else None, 'Profit and Loss (native HTML)', reason=reason)

    groups = reports.get('groups', [])
    for key, name in [('cash_in_hand', 'Cash-in-Hand'), ('bank_balance', 'Bank Accounts')]:
        data[key] = metric(key, exact_row(groups, name), 'Group closing balances', period=False)

    # Duties & Taxes is not a verified GST/TDS statutory payable.
    for key in ('tds_payable', 'gst_payable'):
        data[key] = metric(key, None, 'Statutory payable report not verified', period=False)

    contexts = {}
    for key in ('receivables', 'payables'):
        report = reports.get(key, {})
        matches_date = report.get('to_date') == end.isoformat()
        contexts[key] = {'from_date': report.get('from_date'), 'to_date': report.get('to_date'), 'matches_selected_as_of': matches_date}
        total = {'name': 'Pending Amount total', 'amount': report.get('total'), 'raw': report.get('raw_total'), 'field': 'HTML Pending Amount footer'} if matches_date else None
        reason = None if matches_date else 'Tally returned a different or unverified outstanding as-of date; select its returned period to view these balances.'
        data[key] = metric(key, total, f'Bills {"Receivable" if key == "receivables" else "Payable"} (native HTML)', period=False, reason=reason)
        bills = report.get('bills') if matches_date else None
        data[f'top_{key}'] = None if bills is None else [
            {**bill, 'status': 'Unavailable' if bill['days_overdue'] is None else ('Overdue' if bill['days_overdue'] > 0 else 'Not overdue')}
            for bill in sorted(bills, key=lambda bill: (bill['amount'] is not None, bill['amount'] if bill['amount'] is not None else 0), reverse=True)[:5]
        ]

    group_by_name = {row['name']: row for row in groups}

    def category(parent):
        visited = set()
        while parent and parent not in visited:
            visited.add(parent)
            group = group_by_name.get(parent, {})
            identity = group.get('reserved_name') or parent
            if identity == 'Cash-in-Hand':
                return 'Cash'
            if identity in ('Bank Accounts', 'Bank OD A/c'):
                return 'Bank'
            parent = group.get('parent')
        return None

    accounts = None
    if 'ledgers' in reports and 'groups' in reports:
        accounts = []
        for ledger in reports['ledgers']:
            kind = category(ledger.get('parent'))
            if kind:
                accounts.append({'name': ledger['name'], 'balance': ledger['amount'], 'category': kind, 'raw': ledger['raw']})
    data['cash_bank_accounts'] = accounts

    def breakdown(names):
        return [
            {'label': row['name'], 'value': row['amount']}
            for name in names
            if (row := exact_row(pl, name)) is not None and row['amount'] is not None
        ] or None

    data['sales_breakdown'] = breakdown(('Sales Accounts',))
    data['expense_breakdown'] = breakdown(('Direct Expenses', 'Indirect Expenses'))
    data.update({
        'revenue': data['total_sales'], 'expenses': data['total_purchases'],
        'pending_invoices': None,
        'sales_growth_pct': None, 'purchases_growth_pct': None, 'profit_growth_pct': None,
        'metric_sources': sources, 'report_contexts': contexts,
        'tally_report_period': {'from_date': native_pl.get('from_date'), 'to_date': native_pl.get('to_date')},
        'company_name': company, 'from_date': start.isoformat(), 'to_date': end.isoformat(),
        'balance_convention': 'Tally signed closing balances: negative is debit, positive is credit. Signs are preserved.',
    })
    return data
