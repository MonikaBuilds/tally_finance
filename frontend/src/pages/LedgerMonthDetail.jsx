import { useMemo } from 'react'
import { useSearchParams, useNavigate, Link } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'

import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import { formatCurrency, formatMonthKey, monthKeyToRange } from '../utils/format'

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

/*
 * Ledger > Monthly Summary > one month's vouchers - what opens when
 * you click a month row, matching Tally's own drill-down from the
 * Ledger Monthly Summary screen into that month's Ledger Vouchers.
 */
function LedgerMonthDetail() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const ledgerName = searchParams.get('ledger') || ''
  const monthKey = searchParams.get('month') || ''
  const range = monthKeyToRange(monthKey)

  const queryPath = useMemo(() => {
    if (!ledgerName || !range) return null

    const params = new URLSearchParams({
      ledger_name: ledgerName,
      from_date: range.from,
      to_date: range.to,
    })

    return `/reports/ledger?${params.toString()}`
  }, [ledgerName, range])

  const { data: reportResponse, loading, error } = useFetch(queryPath)

  const report =
    reportResponse?.success && reportResponse?.report
      ? reportResponse.report
      : null

  const entries = Array.isArray(report?.entries) ? report.entries : []

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

  const rows = openingRow ? [openingRow, ...entries] : []

  function goToVoucher(row) {
    if (!row.voucher_number) return

    const params = new URLSearchParams({
      voucher_type: row.voucher_type || '',
      voucher_number: row.voucher_number,
      ledger_name: ledgerName,
    })

    if (row.date) params.set('date', row.date)

    navigate(`/reports/voucher?${params.toString()}`)
  }

  if (!ledgerName || !range) {
    return (
      <>
        <PageHeader title="Ledger" subtitle="Month detail" />
        <Card>
          <ErrorMessage message="Missing or invalid ledger/month reference." />
        </Card>
      </>
    )
  }

  return (
    <>
      <PageHeader
        title={ledgerName}
        subtitle={`${formatMonthKey(monthKey)} · Live data from TallyPrime`}
      />

      <nav className="breadcrumbs">
        <Link to={`/reports/ledger?ledger=${encodeURIComponent(ledgerName)}&view=monthly`}>
          <ArrowLeft size={16} />
          Back to Ledger
        </Link>
      </nav>

      {loading && <Loader />}

      {error && <ErrorMessage message={error} />}

      {report && (
        <Card title={`${formatMonthKey(monthKey)} Vouchers`}>
          <div className="meta-list">
            <div className="meta-item">
              <span>Period</span>
              <strong>{range.from} to {range.to}</strong>
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

          <DataTable
            columns={COLUMNS}
            rows={rows}
            onRowClick={goToVoucher}
            isRowClickable={(row) => Boolean(row.voucher_number)}
          />

          <div className="table-footer">
            <span>Total Debit: {formatCurrency(report.total_debit)}</span>
            <span>Total Credit: {formatCurrency(report.total_credit)}</span>
            <span>
              Closing Balance: {formatBalance(report.closing_balance)}
            </span>
          </div>
        </Card>
      )}
    </>
  )
}

export default LedgerMonthDetail