import { useNavigate } from 'react-router'
import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import ExportButtons from '../components/common/ExportButtons'
import { formatCurrency } from '../utils/format'

// Tally lets you double-click almost any line on the P&L to drill into
// where it came from. We reproduce that exactly:
//  - Opening Stock / Closing Stock -> Stock Summary (item-wise, with both
//    opening and closing quantity/value columns)
//  - Direct Expenses, Indirect Expenses, Sales Accounts, Purchase
//    Accounts (and any other group line) -> Group Summary for that
//    group, which itself keeps drilling: another sub-group (e.g. Office
//    Exp under Indirect Expenses) re-enters Group Summary, a ledger
//    (e.g. Office Rent Exp) goes to that ledger's Monthly Summary
//  - Gross Profit c/o / Gross Profit b/f / Nett Loss / Net Profit are
//    computed totals, not accounts - nothing to drill into
function stripPrefix(name) {
  return (name || '').replace(/^(add:|less:)\s*/i, '').trim()
}

function normalizeParticular(name) {
  return stripPrefix(name).toLowerCase()
}

function drillDownPathFor(name) {
  if (!name) return null

  const normalized = normalizeParticular(name)

  if (normalized === 'opening stock' || normalized === 'closing stock') {
    return '/reports/inventory'
  }

  if (/gross (profit|loss)|nett? (profit|loss)/i.test(normalized)) {
    return null
  }

  // Tally's P&L labels lines "Add: Purchase Accounts" / "Less: ..." but
  // the actual ledger/group name in Tally is just "Purchase Accounts" -
  // querying Group Summary with the "Add: " prefix still attached
  // returns nothing, which is why this used to show "No records found."
  return `/reports/group-summary?group=${encodeURIComponent(stripPrefix(name))}`
}

function buildColumns(navigate) {
  return [
    {
      key: 'name',
      label: 'Particulars',
      render: (row) => {
        const path = drillDownPathFor(row.name)
        const label = row.is_group ? <strong>{row.name}</strong> : row.name

        if (!path) return label

        return (
          <button
            type="button"
            className="link-button"
            onClick={() => navigate(path)}
            title="View details"
          >
            {label}
          </button>
        )
      },
    },
    {
      key: 'amount',
      label: 'Amount',
      align: 'right',
      render: (row) => (row.is_group ? <strong>{formatCurrency(row.amount)}</strong> : formatCurrency(row.amount)),
    },
  ]
}

// The backend (parse_profit_loss) never emits a container's own summary
// row into left/right - container entries are consumed structurally and
// skipped (see the `is_container` handling in financial.py). So every
// row that reaches this page, group or leaf, appears exactly once and
// must be counted exactly once. Filtering to is_group-only rows drops
// leaf lines (Opening Stock, Direct Expenses, Sales Accounts, Purchase
// Accounts, ...) from the footer total - that's the bug that produced
// the wrong total on screen.
//
// NOTE: this is now only a fallback - the backend sends total_left /
// total_right directly (the true Tally bottom-line total, which
// excludes the trading-section rows already folded into Gross Profit
// c/o). This function is kept in case those fields are ever missing.
function sumGroupAmounts(rows) {
  return (rows || [])
    .reduce((total, row) => total + (Number(row.amount) || 0), 0)
}

function ProfitLoss() {
  const navigate = useNavigate()
  const { data: response, loading, error } = useFetch('/reports/profit-loss')

  if (loading) return <Loader />
  if (error) return <ErrorMessage message={error} />
  if (!response.success) return <ErrorMessage message={response.error || response.message} />

  // Tally's Profit & Loss is a two-sided (Dr | Cr) statement, not a flat
  // list - the API returns { left: [...], right: [...] } for exactly that
  // reason. Render each side as its own table, side by side, the same way
  // Tally itself lays the report out.
  const leftRows = response.report?.left || []
  const rightRows = response.report?.right || []

  const leftTotal = response.report?.total_left ?? sumGroupAmounts(leftRows)
  const rightTotal = response.report?.total_right ?? sumGroupAmounts(rightRows)

  const columns = buildColumns(navigate)

  return (
    <>
      <PageHeader
        title="Profit & Loss"
        subtitle="Click any line to drill into its detail, the same way Tally does"
        actions={<ExportButtons basePath="/reports/profit-loss/export" filenameBase="profit_and_loss" />}
      />

      <div className="split-grid">
        <Card title="Expenditure">
          <DataTable columns={columns} rows={leftRows} />
          <div className="table-footer">
            <span>Total</span>
            <span>{formatCurrency(leftTotal)}</span>
          </div>
        </Card>

        <Card title="Income">
          <DataTable columns={columns} rows={rightRows} />
          <div className="table-footer">
            <span>Total</span>
            <span>{formatCurrency(rightTotal)}</span>
          </div>
        </Card>
      </div>
    </>
  )
}

export default ProfitLoss