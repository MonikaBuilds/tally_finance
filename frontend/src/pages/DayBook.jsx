import { Fragment, useCallback, useEffect, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { AlertCircle, Inbox } from 'lucide-react'
import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import ExportButtons from '../components/common/ExportButtons'
import { formatDate } from '../utils/format'
import { buildQuery } from './trialBalance/tbRouting'
import { useCompanyFinancialYear } from './trialBalance/useCompanyFinancialYear'

// Tally prints Day Book amounts to the paisa, without a currency sign.
const amountFormat = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const formatAmount = (value) => (Number(value) ? amountFormat.format(Number(value)) : '')

// Tally's exception lists (Ctrl+J) plus the regular list.
const VIEW_OPTIONS = [
  { value: 'regular', label: 'Regular vouchers' },
  { value: 'optional', label: 'Optional vouchers', count: 'optional' },
  { value: 'cancelled', label: 'Cancelled vouchers', count: 'cancelled' },
  { value: 'postdated', label: 'Post-dated vouchers', count: 'postdated' },
  { value: 'all', label: 'All vouchers (incl. optional)' },
]

// Tally's Basis of Values > Type of Voucher Entries (Ctrl+B).
const BASIS_OPTIONS = [
  { value: 'all', label: 'All vouchers' },
  { value: 'accounting', label: 'Accounting entries only' },
  { value: 'inventory', label: 'Inventory entries only' },
]

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

// The lines under a voucher in the Detailed view (Alt+F5): each ledger
// with its Dr / Cr amount, each stock item with its quantity.
function DetailLines({ row }) {
  return (row.lines || []).map((line, index) => {
    const isStock = line.kind === 'stock'

    return (
      <tr key={`${row.guid}-line-${index}`} className="daybook-line">
        <td />
        <td className="daybook-line__name">{line.name}</td>
        <td />
        <td />
        <td className="is-numeric">
          {isStock
            ? line.inward ? line.quantity : ''
            : formatAmount(line.debit)}
        </td>
        <td className="is-numeric">
          {isStock
            ? line.inward === false ? line.quantity : ''
            : formatAmount(line.credit)}
        </td>
      </tr>
    )
  })
}

/*
 * Day Book - the vouchers of a period, as TallyPrime's Day Book lists them:
 *
 *   Date | Particulars | Vch Type | Vch No. | Debit Amount | Credit Amount
 *
 * The period is a From Date and a To Date (Tally's F2). Like Tally, it
 * opens on ONE day - the company's current date, held inside the
 * financial year. The server picks that day (the page sends no dates
 * until the user chooses a period) and tells the page which day it
 * chose. Every voucher whose date falls from the From Date to the To
 * Date, both included, is listed. Everything else follows Tally:
 *
 *   - Voucher type (F4), with the vouchers of that type totalled
 *   - Search (Ctrl+F)
 *   - Show: regular vouchers or the optional / cancelled / post-dated
 *     exception lists (Ctrl+J)
 *   - Basis of values: accounting / inventory entries (Ctrl+B)
 *   - Detailed view (Alt+F5): every ledger / stock line and the narration
 *
 * The period and every filter live in the page URL, so a view can be
 * shared, bookmarked and returned to with Back. The server fetches the
 * day from Tally once and applies the filters to it.
 */
function DayBook() {
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  // A link with only one date means that single day.
  const urlFrom = searchParams.get('from_date') || searchParams.get('to_date') || ''
  const urlTo = searchParams.get('to_date') || searchParams.get('from_date') || ''

  const voucherType = searchParams.get('voucher_type') || ''
  const view = searchParams.get('view') || 'regular'
  const basis = searchParams.get('basis') || 'all'
  const urlSearch = searchParams.get('search') || ''
  const detailed = searchParams.get('detailed') === '1'

  const filters = {
    voucher_type: voucherType,
    view: view === 'regular' ? '' : view,
    basis: basis === 'all' ? '' : basis,
    search: urlSearch,
  }

  const path = `/reports/day-book${buildQuery({
    from_date: urlFrom,
    to_date: urlTo,
    ...filters,
  })}`
  const { data: response, loading, error } = useFetch(path)

  // The period actually shown (the opening day when none is chosen yet).
  const shownFrom = response?.from_date || urlFrom
  const shownTo = response?.to_date || urlTo

  const query = { from_date: shownFrom, to_date: shownTo, ...filters }

  // The company's own financial year, from Tally.
  const financialYear = useCompanyFinancialYear()

  // Dates typed into the fields but not applied yet.
  const [draft, setDraft] = useState({ from: null, to: null })
  const [dateError, setDateError] = useState(null)

  const inputFrom = draft.from ?? shownFrom
  const inputTo = draft.to ?? shownTo

  // Change some of the URL parameters; an empty value removes one.
  const updateParams = useCallback(
    (patch) => {
      setSearchParams(
        (previous) => {
          const next = new URLSearchParams(previous)

          Object.entries(patch).forEach(([key, value]) => {
            if (value === '' || value === null || value === undefined || value === false) {
              next.delete(key)
            } else {
              next.set(key, value === true ? '1' : value)
            }
          })

          return next
        },
        { replace: true }
      )
    },
    [setSearchParams]
  )

  // Ctrl+F: the search box applies shortly after typing stops.
  const [searchText, setSearchText] = useState(urlSearch)

  useEffect(() => {
    if (searchText === urlSearch) return undefined

    const timer = window.setTimeout(() => updateParams({ search: searchText.trim() }), 350)
    return () => window.clearTimeout(timer)
  }, [searchText, urlSearch, updateParams])

  function showPeriod(from, to) {
    setDateError(null)
    setDraft({ from: null, to: null })
    updateParams({ from_date: from, to_date: to })
  }

  function applyPeriod(event) {
    event.preventDefault()

    if (!inputFrom || !inputTo) {
      setDateError('Select both a From Date and a To Date.')
      return
    }

    if (inputFrom > inputTo) {
      setDateError('From Date cannot be later than To Date.')
      return
    }

    showPeriod(inputFrom, inputTo)
  }

  // Back to Tally's opening state: the current date.
  function showCurrentDate() {
    showPeriod('', '')
  }

  const rows = response?.success ? response.report || [] : []
  const voucherTypes = response?.success ? response.voucher_types || [] : []
  const exceptions = response?.exceptions || {}

  // Keep the chosen type selectable even when this period has none.
  const typeOptions = voucherTypes.some((t) => t.name === voucherType) || !voucherType
    ? voucherTypes
    : [...voucherTypes, { name: voucherType, count: 0 }]

  const filterCard = (
    <Card title="Period">
      <form className="ledger-filters" onSubmit={applyPeriod}>
        <div className="form-field form-field--date">
          <label htmlFor="db-from">From Date</label>
          <input
            id="db-from"
            type="date"
            value={inputFrom}
            min="1900-01-01"
            max="2999-12-31"
            onChange={(event) => setDraft((d) => ({ ...d, from: event.target.value }))}
          />
        </div>

        <div className="form-field form-field--date">
          <label htmlFor="db-to">To Date</label>
          <input
            id="db-to"
            type="date"
            value={inputTo}
            min="1900-01-01"
            max="2999-12-31"
            onChange={(event) => setDraft((d) => ({ ...d, to: event.target.value }))}
          />
        </div>

        <div className="daybook-nav">
          <button type="submit" className="btn">
            Apply
          </button>

          <button type="button" className="btn btn-secondary" onClick={showCurrentDate}>
            Current date
          </button>

          {financialYear.from && financialYear.to && (
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => showPeriod(financialYear.from, financialYear.to)}
            >
              Whole financial year
            </button>
          )}
        </div>
      </form>

      {dateError && (
        <p className="selection-error">
          <AlertCircle size={16} />
          {dateError}
        </p>
      )}

      <div className="ledger-filters daybook-filters">
        <div className="form-field form-field--compact">
          <label htmlFor="db-type">Voucher Type</label>
          <select
            id="db-type"
            value={voucherType}
            onChange={(event) => updateParams({ voucher_type: event.target.value })}
          >
            <option value="">All Vouchers</option>
            {typeOptions.map((type) => (
              <option key={type.name} value={type.name}>
                {type.name} ({type.count})
              </option>
            ))}
          </select>
        </div>

        <div className="form-field form-field--compact">
          <label htmlFor="db-view">Show</label>
          <select
            id="db-view"
            value={view}
            onChange={(event) =>
              updateParams({ view: event.target.value === 'regular' ? '' : event.target.value })
            }
          >
            {VIEW_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
                {option.count && exceptions[option.count] ? ` (${exceptions[option.count]})` : ''}
              </option>
            ))}
          </select>
        </div>

        <div className="form-field form-field--compact">
          <label htmlFor="db-basis">Type of Voucher Entries</label>
          <select
            id="db-basis"
            value={basis}
            onChange={(event) =>
              updateParams({ basis: event.target.value === 'all' ? '' : event.target.value })
            }
          >
            {BASIS_OPTIONS.map((option) => (
              <option key={option.value} value={option.value}>
                {option.label}
              </option>
            ))}
          </select>
        </div>

        <div className="form-field">
          <label htmlFor="db-search">Search</label>
          <input
            id="db-search"
            type="search"
            placeholder="Party, ledger, narration, voucher no."
            value={searchText}
            onChange={(event) => setSearchText(event.target.value)}
          />
        </div>

        <div className="daybook-toggles">
          <label className="daybook-toggle">
            <input
              type="checkbox"
              checked={detailed}
              onChange={(event) => updateParams({ detailed: event.target.checked })}
            />
            Detailed
          </label>
        </div>
      </div>
    </Card>
  )

  const header = (
    <PageHeader
      title="Day Book"
      subtitle={
        shownFrom && shownTo && shownFrom !== shownTo
          ? `${formatDate(shownFrom)} to ${formatDate(shownTo)}`
          : shownFrom
            ? formatDate(shownFrom)
            : undefined
      }
      actions={
        <ExportButtons
          basePath="/reports/day-book/export"
          params={query}
          filenameBase="day_book"
          disabled={!response?.success}
        />
      }
    />
  )

  if (loading || (!response && !error)) {
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
        {rows.length === 0 ? (
          <div className="empty-state">
            <Inbox size={28} strokeWidth={1.5} />
            <span>No vouchers found for this period and selection.</span>
          </div>
        ) : (
          <div className="data-table-scroll">
            <table className="data-table">
              <thead>
                <tr>
                  <th>Date</th>
                  <th>Particulars</th>
                  <th>Vch Type</th>
                  <th className="is-numeric">Vch No.</th>
                  <th className="is-numeric">
                    Debit Amount
                    <span className="daybook-qty">Inwards Qty</span>
                  </th>
                  <th className="is-numeric">
                    Credit Amount
                    <span className="daybook-qty">Outwards Qty</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {rows.map((row, index) => {
                  const target = voucherPath(row)
                  const open = target ? () => navigate(target) : undefined

                  return (
                    <Fragment key={`${row.guid}-${index}`}>
                      <tr
                        className={target ? 'data-table-row--clickable' : undefined}
                        onClick={open}
                        onKeyDown={
                          target
                            ? (event) => {
                                if (event.key === 'Enter' || event.key === ' ') {
                                  event.preventDefault()
                                  open()
                                }
                              }
                            : undefined
                        }
                        tabIndex={target ? 0 : undefined}
                        role={target ? 'button' : undefined}
                      >
                        <td>{formatDate(row.date)}</td>
                        <td>
                          <strong>{row.particulars}</strong>
                          {row.is_cancelled && <span className="status-cancelled"> (Cancelled)</span>}
                          {row.is_optional && <em> (Optional)</em>}
                          {row.is_postdated && <em> (Post-dated)</em>}
                          {detailed && row.narration && (
                            <span className="daybook-narration">{row.narration}</span>
                          )}
                        </td>
                        <td>{row.voucher_type}</td>
                        <td className="is-numeric">{row.voucher_number}</td>
                        <td className="is-numeric">
                          {formatAmount(row.debit)}
                          {row.inwards_qty && <em className="daybook-qty">{row.inwards_qty}</em>}
                        </td>
                        <td className="is-numeric">
                          {formatAmount(row.credit)}
                          {row.outwards_qty && <em className="daybook-qty">{row.outwards_qty}</em>}
                        </td>
                      </tr>
                      {detailed && <DetailLines row={row} />}
                    </Fragment>
                  )
                })}
              </tbody>
            </table>
          </div>
        )}

        <div className="table-footer">
          <span className="daybook-count">
            {response.count ?? rows.length} voucher{(response.count ?? rows.length) === 1 ? '' : 's'}
          </span>
          <span>Grand Total</span>
          <span>Debit: {amountFormat.format(Number(response.total_debit) || 0)}</span>
          <span>Credit: {amountFormat.format(Number(response.total_credit) || 0)}</span>
        </div>
      </Card>
    </>
  )
}

export default DayBook
