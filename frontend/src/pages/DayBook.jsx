import { useEffect, useState } from 'react'
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

// Tally prints Day Book amounts to the paisa, without a currency sign.
const amountFormat = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const formatAmount = (value) => (Number(value) ? amountFormat.format(Number(value)) : '')

// Where a Day Book row opens. Accounting vouchers (Journal, Sales,
// Purchase, Credit / Debit Note, Payment, Receipt, Contra ...) open the
// app's one Voucher page; stock-only vouchers (Delivery / Receipt Note,
// Stock Journal ...) open the Inventory Voucher page - the same pages
// every other report opens, no extra routes.
function voucherPath(row) {
  if (!row?.voucher_type || !row?.voucher_number) return null

  if (row.drill === 'inventory') {
    return `/reports/inventory-voucher${buildQuery({
      voucher_type: row.voucher_type,
      voucher_number: row.voucher_number,
      date: row.date,
    })}`
  }

  return `/reports/voucher${buildQuery({
    voucher_type: row.voucher_type,
    voucher_number: row.voucher_number,
    date: row.date,
    ledger_name: row.ledger_name,
  })}`
}

function buildColumns() {
  return [
    {
      key: 'date',
      label: 'Date',
      render: (row) => formatDate(row.date),
    },
    {
      key: 'particulars',
      label: 'Particulars',
      render: (row) => (
        <>
          <strong>{row.particulars}</strong>
          {row.is_cancelled && <span className="status-cancelled"> (Cancelled)</span>}
          {row.is_optional && <em> (Optional)</em>}
        </>
      ),
    },
    { key: 'voucher_type', label: 'Vch Type' },
    { key: 'voucher_number', label: 'Vch No.', align: 'right' },
    {
      key: 'debit',
      label: (
        <>
          Debit Amount
          <span className="daybook-qty">Inwards Qty</span>
        </>
      ),
      align: 'right',
      // Stock vouchers carry a quantity instead of an amount: Tally
      // prints Inwards Qty under Debit and Outwards Qty under Credit.
      render: (row) => (
        <>
          {formatAmount(row.debit)}
          {row.inwards_qty && <em className="daybook-qty">{row.inwards_qty}</em>}
        </>
      ),
    },
    {
      key: 'credit',
      label: (
        <>
          Credit Amount
          <span className="daybook-qty">Outwards Qty</span>
        </>
      ),
      align: 'right',
      render: (row) => (
        <>
          {formatAmount(row.credit)}
          {row.outwards_qty && <em className="daybook-qty">{row.outwards_qty}</em>}
        </>
      ),
    },
  ]
}

/*
 * Day Book - every voucher of the period, as Tally's Day Book lists it:
 *
 *   Date | Particulars | Vch Type | Vch No. | Debit Amount | Credit Amount
 *
 * Like Tally, the Day Book opens on ONE day: the most recent day that has
 * vouchers (found from the data itself, nothing hardcoded). The period
 * lives in the page URL (?from_date=...&to_date=...); widen it with the
 * date fields or "Whole financial year". Click a voucher to open it.
 * Every value - rows, voucher types, totals - comes from /reports/day-book.
 */
function DayBook() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()
  const financialYear = useCompanyFinancialYear()

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

  const path = datesReady ? `/reports/day-book${buildQuery(dates)}` : null
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

  // The company's whole financial year, as an explicit period.
  function showFinancialYear() {
    setDateError(null)
    setDraft({ from: null, to: null })
    setSearchParams(
      { from_date: financialYear.from, to_date: financialYear.to },
      { replace: true }
    )
  }

  const rows = response?.success ? response.report || [] : []

  // No period chosen yet: Tally shows a single day, so narrow to the
  // latest day that has vouchers. (ISO dates sort as text.)
  const latestDate = rows.reduce((latest, row) => (row.date > latest ? row.date : latest), '')
  const pickingDay = !hasUrlDates && Boolean(latestDate)

  useEffect(() => {
    if (pickingDay) {
      setSearchParams({ from_date: latestDate, to_date: latestDate }, { replace: true })
    }
  }, [pickingDay, latestDate, setSearchParams])

  const filterCard = (
    <Card title="Period">
      <form className="ledger-filters" onSubmit={applyDates}>
        <div className="form-field form-field--date">
          <label htmlFor="db-from">From Date</label>
          <input
            id="db-from"
            type="date"
            value={inputFrom}
            onChange={(event) => setDraft((d) => ({ ...d, from: event.target.value }))}
          />
        </div>

        <div className="form-field form-field--date">
          <label htmlFor="db-to">To Date</label>
          <input
            id="db-to"
            type="date"
            value={inputTo}
            onChange={(event) => setDraft((d) => ({ ...d, to: event.target.value }))}
          />
        </div>

        <button type="submit" className="btn">
          Apply
        </button>

        {financialYear.from && financialYear.to && (
          <button type="button" className="btn btn-secondary" onClick={showFinancialYear}>
            Whole financial year
          </button>
        )}
      </form>

      {dateError && (
        <p className="selection-error">
          <AlertCircle size={16} />
          {dateError}
        </p>
      )}
    </Card>
  )

  const header = (
    <PageHeader
      title="Day Book"
      subtitle={
        fromDate && toDate
          ? `${formatDate(fromDate)} to ${formatDate(toDate)}`
          : undefined
      }
      actions={
        <ExportButtons
          basePath="/reports/day-book/export"
          params={dates}
          filenameBase="day_book"
          disabled={!datesReady}
        />
      }
    />
  )

  if (!datesReady || loading || pickingDay || (!response && !error)) {
    return <>{header}{filterCard}<Loader /></>
  }

  if (error) return <>{header}{filterCard}<ErrorMessage message={error} /></>

  if (!response.success) {
    return <>{header}{filterCard}<ErrorMessage message={response.error || response.message} /></>
  }

  return (
    <>
      {header}

      {filterCard}

      <Card>
        <DataTable
          columns={buildColumns()}
          rows={rows}
          onRowClick={(row) => navigate(voucherPath(row))}
          isRowClickable={(row) => Boolean(voucherPath(row))}
        />

        <div className="table-footer">
          <span>Grand Total</span>
          <span>Debit: {amountFormat.format(Number(response.total_debit) || 0)}</span>
          <span>Credit: {amountFormat.format(Number(response.total_credit) || 0)}</span>
        </div>
      </Card>
    </>
  )
}

export default DayBook
