import { useMemo } from 'react'
import { useSearchParams } from 'react-router'
import { useFetch } from '../../hooks/useFetch'
import PageHeader from '../../components/layout/PageHeader'
import Loader from '../../components/common/Loader'
import ErrorMessage from '../../components/common/ErrorMessage'
import Card from '../../components/common/Card'
import DataTable from '../../components/common/DataTable'
import { formatCurrency } from '../../utils/format'
import TrialBalanceBackButton from './TrialBalanceBackButton'
import { buildQuery, tbPath } from './tbRouting'

// Closing balances follow the Ledger page's convention: positive = Dr,
// negative = Cr.
function formatBalance(value) {
  if (value === undefined || value === null) return '-'
  if (Number(value) === 0) return formatCurrency(0)

  const suffix = Number(value) < 0 ? 'Cr' : 'Dr'
  return `${formatCurrency(Math.abs(Number(value)))} ${suffix}`
}

function formatAmount(value) {
  return formatCurrency(Number(value) || 0)
}

const COLUMNS = [
  { key: 'month', label: 'Particulars' },
  { key: 'debit', label: 'Debit', align: 'right', render: (row) => formatAmount(row.debit) },
  { key: 'credit', label: 'Credit', align: 'right', render: (row) => formatAmount(row.credit) },
  { key: 'closing_balance', label: 'Closing Balance', align: 'right', render: (row) => formatBalance(row.closing_balance) },
]

/*
 * Trial Balance -> ... -> Ledger Monthly Summary.
 *
 * Data: the existing /reports/ledger API (Tally ledger vouchers), which
 * already returns a continuous month-by-month summary in
 * report.monthly_summary, for the selected From/To dates.
 */
function TrialBalanceLedgerMonthly() {
  const [searchParams] = useSearchParams()

  const ledger = searchParams.get('ledger') || ''
  const fromDate = searchParams.get('from_date') || ''
  const toDate = searchParams.get('to_date') || ''

  const dates = { from_date: fromDate, to_date: toDate }

  const { data: response, loading, error } = useFetch(
    ledger ? `/reports/ledger${buildQuery({ ledger_name: ledger, ...dates })}` : null
  )

  const report = response?.success ? response.report : null

  const monthlyRows = useMemo(() => {
    const summary = report?.monthly_summary

    if (!summary || typeof summary !== 'object') return []

    return Object.entries(summary)
      .sort(([a], [b]) => a.localeCompare(b))
      .map(([key, bucket]) => ({
        key,
        month: bucket.month || key,
        debit: bucket.debit,
        credit: bucket.credit,
        closing_balance: bucket.closing_balance,
      }))
  }, [report])

  const header = (
    <PageHeader
      title="Ledger Monthly Summary"
      subtitle={[ledger && `Ledger: ${ledger}`, fromDate && toDate && `${fromDate} to ${toDate}`]
        .filter(Boolean)
        .join('  |  ')}
      actions={<TrialBalanceBackButton fallbackTo={tbPath('', dates)} />}
    />
  )

  if (!ledger) {
    return (
      <>
        {header}
        <ErrorMessage message="No ledger specified. Go back and click a ledger line." />
      </>
    )
  }

  if (loading) return <>{header}<Loader /></>
  if (error) return <>{header}<ErrorMessage message={error} /></>
  if (!report) {
    return <>{header}<ErrorMessage message={response?.error || response?.message} /></>
  }

  const opening = Number(report.opening_balance) || 0

  const rows = [
    {
      month: 'Opening Balance',
      debit: opening > 0 ? opening : 0,
      credit: opening < 0 ? Math.abs(opening) : 0,
      closing_balance: opening,
    },
    ...monthlyRows,
  ]

  const totalDebit = Number(report.total_debit) || 0
  const totalCredit = Number(report.total_credit) || 0

  return (
    <>
      {header}

      <Card title={report.ledger_name || ledger}>
        <DataTable columns={COLUMNS} rows={rows} />

        <div className="table-footer">
          <span>Total Debit: {formatCurrency(totalDebit)}</span>
          <span>Total Credit: {formatCurrency(totalCredit)}</span>
          <span>Closing Balance: {formatBalance(report.closing_balance)}</span>
        </div>
      </Card>
    </>
  )
}

export default TrialBalanceLedgerMonthly
