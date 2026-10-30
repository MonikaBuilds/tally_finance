import { useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router'
import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import ExportButtons from '../components/common/ExportButtons'
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
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const ledgerName = searchParams.get('ledger') || ''
  const monthKey = searchParams.get('month') || ''

  const range = useMemo(() => monthKeyToRange(monthKey), [monthKey])

  const query = new URLSearchParams()
  if (ledgerName) query.set('ledger_name', ledgerName)
  if (range?.from) query.set('from_date', range.from)
  if (range?.to) query.set('to_date', range.to)
  query.set('view', 'detailed')

  const { data: response, loading, error } = useFetch(
    ledgerName && range ? `/reports/ledger?${query.toString()}` : null
  )

  const report = response?.report
  const entries = report?.entries || []

  const rows = useMemo(() => {
    if (!report) return []

    const openingRow = {
      date: range?.from || '-',
      particulars: 'Opening Balance',
      voucher_type: '',
      voucher_number: '',
      debit: Number(report.opening_balance) > 0 ? report.opening_balance : null,
      credit: Number(report.opening_balance) < 0 ? Math.abs(Number(report.opening_balance)) : null,
      running_balance: report.opening_balance,
      isOpening: true,
    }

    return [openingRow, ...entries]
  }, [report, entries, range])

  function handleRowClick(row) {
    if (row.isOpening) return

    const params = new URLSearchParams()
    if (row.guid) params.set('guid', row.guid)
    if (row.date) params.set('date', row.date)
    if (row.voucher_number) params.set('voucher_number', row.voucher_number)
    if (row.voucher_type) params.set('voucher_type', row.voucher_type)
    if (row.particulars) params.set('ledger', row.particulars)
    if (ledgerName) params.set('return_ledger', ledgerName)
    if (monthKey) params.set('return_month', monthKey)

    navigate(`/reports/voucher?${params.toString()}`)
  }

  if (!ledgerName || !range) {
    return (
      <>
        <PageHeader title="Ledger" subtitle="Month detail" backFallback="/reports/ledger" />
        <Card>
          <ErrorMessage message="Missing or invalid ledger/month reference." />
        </Card>
      </>
    )
  }

  const exportActions = (
    <ExportButtons
      basePath="/reports/ledger/export"
      filenameBase={`${ledgerName}_${monthKey}`}
      params={{
        ledger_name: ledgerName,
        from_date: range?.from,
        to_date: range?.to,
        view: 'detailed',
      }}
    />
  )

  return (
    <>
      <PageHeader
        title={ledgerName}
        subtitle={`${formatMonthKey(monthKey)} · Live data from TallyPrime`}
        backFallback={`/reports/ledger?ledger=${encodeURIComponent(ledgerName)}&view=monthly`}
        actions={exportActions}
      />

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
            onRowClick={handleRowClick}
            isRowClickable={(row) => !row.isOpening}
          />

          <div className="table-footer">
            <span>Closing Balance</span>
            <span>{formatBalance(report.closing_balance)}</span>
          </div>
        </Card>
      )}
    </>
  )
}

export default LedgerMonthDetail
