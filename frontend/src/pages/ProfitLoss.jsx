import { useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { AlertCircle } from 'lucide-react'
import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import ExportButtons from '../components/common/ExportButtons'
import { formatCurrency, formatDate } from '../utils/format'
import { useCompanyFinancialYear } from './trialBalance/useCompanyFinancialYear'
import { buildQuery } from './trialBalance/tbRouting'

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

function drillDownPathFor(name, dates) {
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
  // The selected From/To dates ride along so the Group Summary (and the
  // ledgers below it) show the same period as this Profit & Loss.
  return `/reports/group-summary${buildQuery({ group: stripPrefix(name), ...dates })}`
}

function buildColumns(navigate, dates) {
  return [
    {
      key: 'name',
      label: 'Particulars',
      render: (row) => {
        const path = drillDownPathFor(row.name, dates)
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

/*
 * Profit & Loss.
 *
 * The selected From Date / To Date live in the page URL
 * (?from_date=...&to_date=...), the same way the Balance Sheet and
 * Trial Balance do:
 *  - they are sent to the backend, which passes them to Tally as the
 *    report period (SVFROMDATE / SVTODATE);
 *  - the Excel/PDF export uses the same period;
 *  - every drill-down link carries them.
 * With no dates in the URL the company's own financial year (from
 * Tally's company data) is used. Every figure comes from Tally.
 */
function ProfitLoss() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const financialYear = useCompanyFinancialYear()

  // Edits made in the date inputs but not applied yet.
  const [draft, setDraft] = useState({ from: null, to: null })
  const [dateError, setDateError] = useState(null)

  const urlFrom = searchParams.get('from_date') || ''
  const urlTo = searchParams.get('to_date') || ''
  const hasUrlDates = Boolean(urlFrom || urlTo)

  const fromDate = urlFrom || financialYear.from
  const toDate = urlTo || financialYear.to

  const inputFrom = draft.from ?? fromDate
  const inputTo = draft.to ?? toDate

  const datesReady = hasUrlDates || financialYear.ready

  const dates = { from_date: fromDate, to_date: toDate }

  const path = datesReady ? `/reports/profit-loss${buildQuery(dates)}` : null

  const { data: response, loading, error } = useFetch(path)

  function applyDates(event) {
    event.preventDefault()

    if (!inputFrom || !inputTo) {
      setDateError('Select both a From Date and a To Date.')
      return
    }

    if (inputFrom > inputTo) {
      setDateError('From Date cannot be later than To Date.')
      return
    }

    setDateError(null)
    setDraft({ from: null, to: null })
    setSearchParams({ from_date: inputFrom, to_date: inputTo }, { replace: true })
  }

  function resetDates() {
    setDateError(null)
    setDraft({ from: null, to: null })
    setSearchParams({}, { replace: true })
  }

  const dateFilter = (
    <Card title="Period">
      <form className="ledger-filters" onSubmit={applyDates}>
        <div className="form-field form-field--date">
          <label htmlFor="pl-from">From Date</label>
          <input
            id="pl-from"
            type="date"
            value={inputFrom}
            onChange={(event) => setDraft((d) => ({ ...d, from: event.target.value }))}
          />
        </div>

        <div className="form-field form-field--date">
          <label htmlFor="pl-to">To Date</label>
          <input
            id="pl-to"
            type="date"
            value={inputTo}
            onChange={(event) => setDraft((d) => ({ ...d, to: event.target.value }))}
          />
        </div>

        <button type="submit" className="btn">
          Apply
        </button>

        <button type="button" className="btn btn-secondary" onClick={resetDates}>
          Company financial year
        </button>
      </form>

      {dateError && (
        <p className="selection-error">
          <AlertCircle size={16} />
          {dateError}
        </p>
      )}
    </Card>
  )

  const subtitle =
    fromDate && toDate
      ? `Period ${formatDate(fromDate)} to ${formatDate(toDate)} · click any line to drill into its detail, the same way Tally does`
      : 'Click any line to drill into its detail, the same way Tally does'

  const header = (
    <PageHeader
      title="Profit & Loss"
      subtitle={subtitle}
      actions={
        <ExportButtons
          basePath="/reports/profit-loss/export"
          params={dates}
          filenameBase="profit_and_loss"
          disabled={!datesReady}
        />
      }
    />
  )

  // `!response && !error` covers the one render right after the dates
  // become ready, before useFetch has flagged the request as loading.
  if (!datesReady || loading || (!response && !error)) {
    return <>{header}{dateFilter}<Loader /></>
  }

  if (error) return <>{header}{dateFilter}<ErrorMessage message={error} /></>

  if (!response.success) {
    return <>{header}{dateFilter}<ErrorMessage message={response.error || response.message} /></>
  }

  // Tally's Profit & Loss is a two-sided (Dr | Cr) statement, not a flat
  // list - the API returns { left: [...], right: [...] } for exactly that
  // reason. Render each side as its own table, side by side, the same way
  // Tally itself lays the report out.
  const leftRows = response.report?.left || []
  const rightRows = response.report?.right || []

  const leftTotal = response.report?.total_left ?? sumGroupAmounts(leftRows)
  const rightTotal = response.report?.total_right ?? sumGroupAmounts(rightRows)

  const columns = buildColumns(navigate, dates)

  return (
    <>
      {header}

      {dateFilter}

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
