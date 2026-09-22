import { useEffect, useMemo, useState } from 'react'
import { useSearchParams, useNavigate } from 'react-router'
import { AlertCircle, BookOpen } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'

import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import ExportButtons from '../components/common/ExportButtons'
import SearchableSelect from '../components/common/SearchableSelect'
import { formatCurrency, financialYearRange } from '../utils/format'

function formatBalance(value) {
  if (value === undefined || value === null) return '-'
  if (Number(value) === 0) return formatCurrency(0)

  const suffix = Number(value) < 0 ? 'Cr' : 'Dr'
  return `${formatCurrency(Math.abs(Number(value)))} ${suffix}`
}

function formatAmount(value) {
  if (value === undefined || value === null || value === '') {
    return formatCurrency(0)
  }

  return formatCurrency(Number(value) || 0)
}

const COLUMNS = [
  { key: 'date', label: 'Date' },
  { key: 'particulars', label: 'Particulars' },
  { key: 'voucher_type', label: 'Vch Type' },
  { key: 'voucher_number', label: 'Vch No.' },
  {
    key: 'debit',
    label: 'Debit',
    align: 'right',
    render: (row) => formatAmount(row.debit),
  },
  {
    key: 'credit',
    label: 'Credit',
    align: 'right',
    render: (row) => formatAmount(row.credit),
  },
  {
    key: 'running_balance',
    label: 'Balance',
    align: 'right',
    render: (row) => formatBalance(row.running_balance),
  },
]

function Ledger() {
  const navigate = useNavigate()

  const {
    data: listResponse,
    loading: listLoading,
    error: listError,
  } = useFetch('/reports/ledgers')

  const ledgers = Array.isArray(listResponse?.ledgers)
    ? listResponse.ledgers
    : []

  // Dropdown options, grouped by the ledger's Tally parent group.
  const ledgerOptions = useMemo(
    () =>
      (Array.isArray(listResponse?.ledgers) ? listResponse.ledgers : [])
        .filter((ledger) => ledger.name)
        .map((ledger) => ({
          value: ledger.name,
          label: ledger.name,
          group: ledger.parent || 'Other',
        }))
        .sort(
          (a, b) =>
            a.group.localeCompare(b.group) ||
            a.label.localeCompare(b.label)
        ),
    [listResponse]
  )

  const [ledgerName, setLedgerName] = useState('')
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [selectionError, setSelectionError] = useState(null)
  const [activeLedger, setActiveLedger] = useState(null)
  const [view, setView] = useState('detailed')

  // Support arriving here via a drill-down link, e.g.
  // /reports/ledger?ledger=Office%20Rent%20Exp&view=monthly - the same
  // way double-clicking a ledger in a Group Summary lands you straight
  // on its Monthly Summary in Tally, and the same way "back to ledger"
  // links from the Voucher / Month Detail pages return here with the
  // original filters restored. Runs once the ledger list has loaded (so
  // it can be validated the same way manual selection is), and only
  // once per incoming link.
  const [searchParams] = useSearchParams()

  useEffect(() => {
    const linkedLedger = searchParams.get('ledger')
    if (!linkedLedger || ledgers.length === 0) return

    const match = ledgers.find(
      (ledger) =>
        ledger.name &&
        ledger.name.toLowerCase() === linkedLedger.trim().toLowerCase()
    )

    if (!match) return

    const linkedFrom = searchParams.get('from_date') || ''
    const linkedTo = searchParams.get('to_date') || ''
    const linkedView = searchParams.get('view')

    setLedgerName(match.name)
    setFromDate(linkedFrom)
    setToDate(linkedTo)
    setSelectionError(null)
    setActiveLedger({ name: match.name, from: linkedFrom || null, to: linkedTo || null })

    if (linkedView === 'monthly') {
      setView('monthly')
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [searchParams, ledgers.length])

  /*
   * Build the ledger API request only after
   * the user clicks View Statement.
   */
  const queryPath = useMemo(() => {
    if (!activeLedger) return null

    const params = new URLSearchParams({
      ledger_name: activeLedger.name,
    })

    if (activeLedger.from) {
      params.set('from_date', activeLedger.from)
    }

    if (activeLedger.to) {
      params.set('to_date', activeLedger.to)
    }

    return `/reports/ledger?${params.toString()}`
  }, [activeLedger])

  const {
    data: reportResponse,
    loading: reportLoading,
    error: reportError,
  } = useFetch(queryPath)

  function runSearch(name, from, to) {
    const trimmed = name.trim()

    const match = ledgers.find(
      (ledger) =>
        ledger.name &&
        ledger.name.toLowerCase() === trimmed.toLowerCase()
    )

    if (!match) {
      setSelectionError(
        'Select a ledger from the Tally ledger list before viewing its statement.'
      )
      return
    }

    if (from && to && from > to) {
      setSelectionError('From date cannot be later than to date.')
      return
    }

    setSelectionError(null)

    setActiveLedger({
      name: match.name,
      from: from || null,
      to: to || null,
    })
  }

  function handleViewStatement(event) {
    event.preventDefault()
    runSearch(ledgerName, fromDate, toDate)
  }

  // "This FY" / "Last FY" - fill the date fields and, if a ledger is
  // already selected, run the search immediately (a true one-click
  // shortcut); otherwise the user just needs to pick a ledger next.
  function applyFinancialYear(offset) {
    const { from, to } = financialYearRange(offset)

    setFromDate(from)
    setToDate(to)

    if (ledgerName.trim()) {
      runSearch(ledgerName, from, to)
    }
  }

  /*
   * Backend response:
   *
   * {
   *   success: true,
   *   report: {
   *     ledger_name: "...",
   *     opening_balance: ...,
   *     entries: [...],
   *     monthly_summary: { "2025-04": { month, opening_balance, debit, credit, closing_balance }, ... },
   *     total_debit: ...,
   *     total_credit: ...,
   *     closing_balance: ...
   *   }
   * }
   */
  const report =
    reportResponse?.success && reportResponse?.report
      ? reportResponse.report
      : null

  const entries = Array.isArray(report?.entries)
    ? report.entries
    : []

  /*
   * Opening balance row
   */
  const openingRow = report
    ? {
        date: '',
        particulars: 'Opening Balance',
        voucher_type: '',
        voucher_number: '',
        debit:
          Number(report.opening_balance) > 0
            ? Number(report.opening_balance)
            : 0,
        credit:
          Number(report.opening_balance) < 0
            ? Math.abs(Number(report.opening_balance))
            : 0,
        running_balance: Number(report.opening_balance) || 0,
      }
    : null

  /*
   * Detailed table rows
   */
  const detailedRows = openingRow
    ? [openingRow, ...entries]
    : []

  const totalDebit = Number(
    report?.total_debit ??
      entries.reduce(
        (sum, row) => sum + (Number(row?.debit) || 0),
        0
      )
  )

  const totalCredit = Number(
    report?.total_credit ??
      entries.reduce(
        (sum, row) => sum + (Number(row?.credit) || 0),
        0
      )
  )

  /*
   * Monthly Summary - the backend now builds a continuous,
   * Tally-accurate month-by-month summary (carrying the closing
   * balance forward through months with no transactions) as
   * report.monthly_summary, keyed "YYYY-MM" -> bucket. Just turn it
   * into a sorted array here instead of recomputing it from entries
   * (which would silently drop zero-transaction months).
   */
  const monthlyRows = useMemo(() => {
    const summary = report?.monthly_summary

    if (!summary || typeof summary !== 'object') return []

    return Object.entries(summary)
      .sort(([keyA], [keyB]) => keyA.localeCompare(keyB))
      .map(([key, bucket]) => ({
        key,
        month: bucket.month || key,
        opening_balance: bucket.opening_balance,
        debit: bucket.debit,
        credit: bucket.credit,
        closing_balance: bucket.closing_balance,
      }))
  }, [report])

  const monthlyColumns = [
    {
      key: 'month',
      label: 'Particulars',
    },
    {
      key: 'debit',
      label: 'Debit',
      align: 'right',
      render: (row) => formatAmount(row.debit),
    },
    {
      key: 'credit',
      label: 'Credit',
      align: 'right',
      render: (row) => formatAmount(row.credit),
    },
    {
      key: 'closing_balance',
      label: 'Closing Balance',
      align: 'right',
      render: (row) => formatBalance(row.closing_balance),
    },
  ]

  /*
   * Drill-downs, matching Tally: click a month row -> that month's
   * vouchers; click a transaction row -> the full voucher.
   */
  function goToMonth(row) {
    if (!row.key || !activeLedger) return

    const params = new URLSearchParams({
      ledger: activeLedger.name,
      month: row.key,
    })

    navigate(`/reports/ledger/month?${params.toString()}`)
  }

  function goToVoucher(row) {
    if (!row.voucher_number || !activeLedger) return

    const params = new URLSearchParams({
      voucher_type: row.voucher_type || '',
      voucher_number: row.voucher_number,
      ledger_name: activeLedger.name,
    })

    if (row.date) params.set('date', row.date)

    navigate(`/reports/voucher?${params.toString()}`)
  }

  return (
    <>
      <PageHeader
        title="Ledger"
        subtitle="Live Ledger Vouchers data from TallyPrime"
      />

      <Card title="Select Ledger">
        {listLoading && <Loader />}

        {listError && (
          <ErrorMessage message={listError} />
        )}

        {!listLoading && !listError && (
          <form
            className="ledger-filters"
            onSubmit={handleViewStatement}
          >
            <div className="form-field">
              <label htmlFor="ledger-search">
                Ledger
              </label>

              <SearchableSelect
                id="ledger-search"
                value={ledgerName}
                options={ledgerOptions}
                onChange={(name) => {
                  setLedgerName(name)
                  setSelectionError(null)
                }}
                placeholder="Select ledger from Tally"
                searchPlaceholder="Search ledgers or groups…"
                emptyMessage="No ledger matches your search."
              />
            </div>

            <div className="form-field form-field--date">
              <label htmlFor="ledger-from">
                From Date
              </label>

              <input
                id="ledger-from"
                type="date"
                value={fromDate}
                onChange={(event) =>
                  setFromDate(event.target.value)
                }
              />
            </div>

            <div className="form-field form-field--date">
              <label htmlFor="ledger-to">
                To Date
              </label>

              <input
                id="ledger-to"
                type="date"
                value={toDate}
                onChange={(event) =>
                  setToDate(event.target.value)
                }
              />
            </div>

            <div className="form-field form-field--quick-range">
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => applyFinancialYear(0)}
              >
                This FY
              </button>

              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => applyFinancialYear(-1)}
              >
                Last FY
              </button>
            </div>

            <button
              type="submit"
              className="btn"
            >
              View Statement
            </button>
          </form>
        )}

        {selectionError && (
          <p className="selection-error">
            <AlertCircle size={16} />
            {selectionError}
          </p>
        )}
      </Card>

      {!activeLedger && (
        <Card>
          <div className="empty-state">
            <BookOpen size={28} strokeWidth={1.5} />
            <span>
              Select a ledger from Tally and click View
              Statement.
            </span>
          </div>
        </Card>
      )}

      {activeLedger && reportLoading && <Loader />}

      {activeLedger && reportError && (
        <ErrorMessage message={reportError} />
      )}

      {activeLedger &&
        reportResponse &&
        !reportResponse.success && (
          <ErrorMessage
            message={
              reportResponse.error ||
              reportResponse.message ||
              'Unable to fetch ledger report.'
            }
          />
        )}

      {report && (
        <Card title={`Ledger: ${report.ledger_name}`}>
          <div className="meta-list">
            <div className="meta-item">
              <span>Period</span>
              <strong>
                {report.from_date || activeLedger.from || 'books beginning'} to{' '}
                {report.to_date || activeLedger.to || 'today'}
              </strong>
            </div>
            <div className="meta-item">
              <span>Opening Balance</span>
              <strong>{formatBalance(report.opening_balance)}</strong>
            </div>
            <div className="meta-item">
              <span>Entries</span>
              <strong>{report.entry_count ?? entries.length}</strong>
            </div>
          </div>

          <div className="card-toolbar">
            <div className="segmented" role="tablist" aria-label="Ledger view">
              <button
                type="button"
                role="tab"
                aria-selected={view === 'detailed'}
                className={`segmented-option${
                  view === 'detailed'
                    ? ' segmented-option--active'
                    : ''
                }`}
                onClick={() => setView('detailed')}
              >
                Detailed
              </button>

              <button
                type="button"
                role="tab"
                aria-selected={view === 'monthly'}
                className={`segmented-option${
                  view === 'monthly'
                    ? ' segmented-option--active'
                    : ''
                }`}
                onClick={() => setView('monthly')}
              >
                Monthly Summary
              </button>
            </div>

            <ExportButtons
              basePath="/reports/ledger/export"
              params={{
                ledger_name: activeLedger.name,
                from_date:
                  activeLedger.from || undefined,
                to_date:
                  activeLedger.to || undefined,
              }}
              filenameBase={`${activeLedger.name
                .trim()
                .replace(/\s+/g, '_')
                .replace(/\//g, '-')}_ledger`}
            />
          </div>

          {view === 'detailed' ? (
            <DataTable
              columns={COLUMNS}
              rows={detailedRows}
              onRowClick={goToVoucher}
              isRowClickable={(row) => Boolean(row.voucher_number)}
            />
          ) : (
            <DataTable
              columns={monthlyColumns}
              rows={[
                {
                  month: 'Opening Balance',
                  debit:
                    Number(report.opening_balance) > 0
                      ? Number(report.opening_balance)
                      : 0,
                  credit:
                    Number(report.opening_balance) < 0
                      ? Math.abs(
                          Number(report.opening_balance)
                        )
                      : 0,
                  closing_balance:
                    Number(report.opening_balance) || 0,
                },
                ...monthlyRows,
              ]}
              onRowClick={goToMonth}
              isRowClickable={(row) => Boolean(row.key)}
            />
          )}

          <div className="table-footer">
            <span>
              Total Debit: {formatCurrency(totalDebit)}
            </span>

            <span>
              Total Credit: {formatCurrency(totalCredit)}
            </span>

            <span>
              Closing Balance:{' '}
              {formatBalance(report.closing_balance)}
            </span>
          </div>
        </Card>
      )}
    </>
  )
}

export default Ledger