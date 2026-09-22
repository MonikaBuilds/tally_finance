// Single source of truth for the Reports tab: every report that
// exists and where it lives. Sidebar and the Reports index page both
// read from this list so they can never fall out of sync.
// No categories/labels on purpose - just one flat list under Reports.

export const ALL_REPORTS = [
  { to: '/reports/profit-loss', label: 'Profit & Loss', description: 'Income and expenditure for the selected period.' },
  { to: '/reports/balance-sheet', label: 'Balance Sheet', description: 'Assets and liabilities as on a given date.' },
  { to: '/reports/trial-balance', label: 'Trial Balance', description: 'Ledger-wise debit and credit closing balances.' },
  { to: '/reports/ledger', label: 'Ledger', description: 'Voucher-wise entries for any ledger account.' },
  { to: '/reports/receivables', label: 'Receivables', description: 'Bills receivable and ageing by party.' },
  { to: '/reports/payables', label: 'Payables', description: 'Bills payable and ageing by party.' },
  { to: '/reports/pending-invoices', label: 'Pending Invoices', description: 'Invoices awaiting payment or approval.' },
  { to: '/reports/inventory', label: 'Stock Summary', description: 'Item-wise stock quantity and value.' },
]

export const REPORT_ROUTES = ALL_REPORTS.map((report) => report.to)