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
import { formatCurrency } from '../utils/format'
import { useCompanyFinancialYear } from './trialBalance/useCompanyFinancialYear'
import { buildQuery, drillPathForRow } from './trialBalance/tbRouting'

const COLUMNS = [
  { key: 'name', label: 'Ledger' },
  { key: 'debit', label: 'Debit', align: 'right', render: (row) => formatCurrency(row.debit) },
  { key: 'credit', label: 'Credit', align: 'right', render: (row) => formatCurrency(row.credit) },
]

/*
 * Trial Balance.
 *
 * The selected From Date / To Date live in the page URL
 * (?from_date=...&to_date=...). That has three effects:
 *  - they are sent to the backend, which passes them to Tally as the
 *    report period;
 *  - every drill-down link carries them, so all routed reports use the
 *    same period;
 *  - Back from a routed page returns here with the same dates.
 * With no dates in the URL the company's own financial year (from
 * Tally's company data) is used.
 */
function TrialBalance() {
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

  const path = datesReady
    ? `/reports/trial-balance${buildQuery({ from_date: fromDate, to_date: toDate })}`
    : null

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
          <label htmlFor="tb-from">From Date</label>
          <input
            id="tb-from"
            type="date"
            value={inputFrom}
            onChange={(event) => setDraft((d) => ({ ...d, from: event.target.value }))}
          />
        </div>

        <div className="form-field form-field--date">
          <label htmlFor="tb-to">To Date</label>
          <input
            id="tb-to"
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
    const report = response.report
    // Tally's own footer sums the magnitude of each row - a row can
    // show a signed "(-)" amount without that flipping the grand
    // total (verified against a live Tally Group Summary: 13,33,800 +
    // 2,05,000 + (-)1,58,60,100 still totals 1,73,98,900, not 0).
    const totalDebit = report.reduce((sum, row) => sum + Math.abs(row.debit || 0), 0)
    const totalCredit = report.reduce((sum, row) => sum + Math.abs(row.credit || 0), 0)

    body = (
      <Card>
        <p className="table-hint">Click a line to drill into its detail, the same way Tally does.</p>

        <DataTable
          columns={COLUMNS}
          rows={report}
          onRowClick={(row) =>
            navigate(drillPathForRow(row, { from_date: fromDate, to_date: toDate }))
          }
          isRowClickable={(row) =>
            Boolean(drillPathForRow(row, { from_date: fromDate, to_date: toDate }))
          }
        />
        <div className="table-footer">
          <span>Total Debit: {formatCurrency(totalDebit)}</span>
          <span>Total Credit: {formatCurrency(totalCredit)}</span>
        </div>
      </Card>
    )
  }

  return (
    <>
      <PageHeader
        title="Trial Balance"
        subtitle={fromDate && toDate ? `${fromDate} to ${toDate}` : undefined}
        actions={
          <ExportButtons
            basePath="/reports/trial-balance/export"
            params={{ from_date: fromDate, to_date: toDate }}
            filenameBase="trial_balance"
            disabled={!datesReady}
          />
        }
      />

      {dateFilter}

      {body}
    </>
  )
}

export default TrialBalance
