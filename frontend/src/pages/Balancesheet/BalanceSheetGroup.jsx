import { useNavigate, useSearchParams } from 'react-router'
import { useFetch } from '../../hooks/useFetch'
import PageHeader from '../../components/layout/PageHeader'
import Loader from '../../components/common/Loader'
import ErrorMessage from '../../components/common/ErrorMessage'
import Card from '../../components/common/Card'
import DataTable from '../../components/common/DataTable'
import { formatCurrency } from '../../utils/format'
import TrialBalanceBackButton from '../trialBalance/TrialBalanceBackButton'
import { buildQuery } from '../trialBalance/tbRouting'
import { bsPath, balanceSheetGroupRowPath } from './bsRouting'

const COLUMNS = [
  { key: 'name', label: 'Particulars' },
  { key: 'debit', label: 'Debit', align: 'right', render: (row) => (row.debit ? formatCurrency(row.debit) : '') },
  { key: 'credit', label: 'Credit', align: 'right', render: (row) => (row.credit ? formatCurrency(row.credit) : '') },
]

/*
 * Balance Sheet -> Group Summary (Tally's drill-down on a Balance Sheet
 * line, e.g. Capital Account, Loans (Liability), Current Liabilities,
 * Current Assets).
 *
 * Data: the existing /reports/group-summary API - the same one the
 * Trial Balance and Profit & Loss drill-downs use - for the Balance
 * Sheet's From/To dates. Row drilling reuses the Trial Balance rules
 * (sub-group, ledger monthly summary, Opening Stock, ...) and adds
 * Closing Stock -> Stock Group Summary, which the Trial Balance rules
 * do not cover. This page exists only so the Trial Balance files could
 * be left untouched; it has no data logic of its own.
 */
function BalanceSheetGroup() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const group = searchParams.get('group') || ''
  const fromDate = searchParams.get('from_date') || ''
  const toDate = searchParams.get('to_date') || ''

  const dates = { from_date: fromDate, to_date: toDate }

  const { data: response, loading, error } = useFetch(
    group ? `/reports/group-summary${buildQuery({ group, ...dates })}` : null
  )

  const header = (
    <PageHeader
      title={`Group Summary: ${group}`}
      subtitle={fromDate && toDate ? `${fromDate} to ${toDate}` : undefined}
      actions={<TrialBalanceBackButton fallbackTo={bsPath('', dates)} />}
    />
  )

  if (!group) {
    return (
      <>
        {header}
        <ErrorMessage message="No group specified. Go back to the Balance Sheet and click a line." />
      </>
    )
  }

  if (loading || (!response && !error)) return <>{header}<Loader /></>
  if (error) return <>{header}<ErrorMessage message={error} /></>
  if (!response?.success) {
    return <>{header}<ErrorMessage message={response?.error || response?.message} /></>
  }

  const rows = response.report || []

  return (
    <>
      {header}

      <Card>
        <p className="table-hint">
          Click a row to drill further - into a sub-group, a ledger&apos;s monthly summary, or stock.
        </p>

        <DataTable
          columns={COLUMNS}
          rows={rows}
          onRowClick={(row) => navigate(balanceSheetGroupRowPath(row, dates))}
          isRowClickable={(row) => Boolean(balanceSheetGroupRowPath(row, dates))}
        />

        <div className="table-footer">
          <span>Total Debit: {formatCurrency(response.total_debit || 0)}</span>
          <span>Total Credit: {formatCurrency(response.total_credit || 0)}</span>
        </div>
      </Card>
    </>
  )
}

export default BalanceSheetGroup
