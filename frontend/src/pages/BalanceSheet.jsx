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
import { formatDate } from '../utils/format'
import { useCompanyFinancialYear } from './trialBalance/useCompanyFinancialYear'
import { buildQuery } from './trialBalance/tbRouting'
import { balanceSheetLinePath, balanceSheetChildPath } from './balanceSheet/bsRouting'

// Tally prints Balance Sheet amounts to the paisa (47,21,200.00), so the
// two-decimal form is used here rather than the whole-rupee formatter.
const amountFormat = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

// Tally leaves a zero line blank, and shows a sub-line that runs the
// other way from its parent as "(-)amount".
function formatAmount(value) {
  if (value === undefined || value === null || Number(value) === 0) return ''

  const number = Number(value)
  return number < 0
    ? `(-)${amountFormat.format(Math.abs(number))}`
    : amountFormat.format(number)
}

// One line per Balance Sheet line, with its sub-lines (e.g. Profit &
// Loss A/c -> Opening Balance / Current Period) directly underneath.
function flatten(lines) {
  const rows = []

  for (const line of lines || []) {
    rows.push({ ...line, _kind: 'line' })

    for (const child of line.children || []) {
      rows.push({ ...child, _kind: 'child', _parent: line })
    }
  }

  return rows
}

const COLUMNS = [
  {
    key: 'name',
    label: 'Particulars',
    render: (row) =>
      row._kind === 'child' ? (
        <span style={{ paddingLeft: 24, fontStyle: 'italic' }}>{row.name}</span>
      ) : (
        <strong>{row.name}</strong>
      ),
  },
  {
    key: 'amount',
    label: 'Amount',
    align: 'right',
    render: (row) => formatAmount(row.amount),
  },
]

/*
 * Balance Sheet.
 *
 * Laid out like Tally's own screen: Liabilities on the left, Assets on
 * the right, each with its total. Every figure comes from the Tally
 * server through /reports/balance-sheet; nothing is hardcoded.
 *
 * The selected From Date / To Date live in the page URL
 * (?from_date=...&to_date=...), the same way the Trial Balance does:
 *  - they are sent to the backend, which passes them to Tally as the
 *    report period (SVFROMDATE / SVTODATE);
 *  - every drill-down link carries them, so the routed reports use the
 *    same period;
 *  - Back from a routed page returns here with the same dates.
 * With no dates in the URL the company's own financial year (from
 * Tally's company data) is used.
 */
function BalanceSheet() {
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

  const path = datesReady ? `/reports/balance-sheet${buildQuery(dates)}` : null

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
          <label htmlFor="bs-from">From Date</label>
          <input
            id="bs-from"
            type="date"
            value={inputFrom}
            onChange={(event) => setDraft((d) => ({ ...d, from: event.target.value }))}
          />
        </div>

        <div className="form-field form-field--date">
          <label htmlFor="bs-to">To Date</label>
          <input
            id="bs-to"
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

  const companyName =
    response?.company_name || sessionStorage.getItem('selected_company') || ''

  const subtitleParts = []
  if (companyName) subtitleParts.push(companyName)
  if (toDate) subtitleParts.push(`as at ${formatDate(toDate)}`)
  if (fromDate && toDate) {
    subtitleParts.push(`period ${formatDate(fromDate)} to ${formatDate(toDate)}`)
  }

  let body

  // `!response && !error` covers the one render right after the dates
  // become ready, before useFetch has flagged the request as loading.
  if (!datesReady || loading || (!response && !error)) {
    body = <Loader />
  } else if (error) {
    body = <ErrorMessage message={error} />
  } else if (!response?.success) {
    body = <ErrorMessage message={response?.error || response?.message} />
  } else {
    const report = response.report || {}

    const liabilityRows = flatten(report.liabilities)
    const assetRows = flatten(report.assets)

    const rowPath = (row) =>
      row._kind === 'child'
        ? balanceSheetChildPath(row, row._parent)
        : balanceSheetLinePath(row, dates)

    const table = (rows) => (
      <DataTable
        columns={COLUMNS}
        rows={rows}
        onRowClick={(row) => navigate(rowPath(row))}
        isRowClickable={(row) => Boolean(rowPath(row))}
      />
    )

    const difference = Number(report.difference) || 0

    body = (
      <>
        <p className="table-hint">Click a line to drill into its detail, the same way Tally does.</p>

        <div className="split-grid">
          <Card title="Liabilities">
            {table(liabilityRows)}
            <div className="table-footer">
              <span>Total</span>
              <span>{amountFormat.format(report.total_liabilities || 0)}</span>
            </div>
          </Card>

          <Card title="Assets">
            {table(assetRows)}
            <div className="table-footer">
              <span>Total</span>
              <span>{amountFormat.format(report.total_assets || 0)}</span>
            </div>
          </Card>
        </div>

        {Math.abs(difference) >= 0.01 && (
          <p className="selection-error">
            <AlertCircle size={16} />
            Liabilities and Assets totals differ by {amountFormat.format(Math.abs(difference))}.
          </p>
        )}
      </>
    )
  }

  return (
    <>
      <PageHeader
        title="Balance Sheet"
        subtitle={subtitleParts.length ? subtitleParts.join(' · ') : undefined}
        actions={
          <ExportButtons
            basePath="/reports/balance-sheet/export"
            params={dates}
            filenameBase="balance_sheet"
            disabled={!datesReady}
          />
        }
      />

      {dateFilter}

      {body}
    </>
  )
}

export default BalanceSheet
