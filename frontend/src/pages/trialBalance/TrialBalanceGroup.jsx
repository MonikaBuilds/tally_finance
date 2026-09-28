import { useNavigate, useSearchParams } from 'react-router'
import { useFetch } from '../../hooks/useFetch'
import PageHeader from '../../components/layout/PageHeader'
import Loader from '../../components/common/Loader'
import ErrorMessage from '../../components/common/ErrorMessage'
import Card from '../../components/common/Card'
import DataTable from '../../components/common/DataTable'
import { formatCurrency } from '../../utils/format'
import TrialBalanceBackButton from './TrialBalanceBackButton'
import { buildQuery, drillPathForRow, tbPath } from './tbRouting'

const COLUMNS = [
  { key: 'name', label: 'Particulars' },
  { key: 'debit', label: 'Debit', align: 'right', render: (row) => (row.debit ? formatCurrency(row.debit) : '') },
  { key: 'credit', label: 'Credit', align: 'right', render: (row) => (row.credit ? formatCurrency(row.credit) : '') },
]

/*
 * Trial Balance -> Group Summary (Tally's F4 / double-click on a group).
 *
 * Data: the existing /reports/group-summary API (the same one the
 * Profit & Loss drill-down uses), for the selected From/To dates.
 * Each row leads on, exactly as in Tally:
 *   - a sub-group        -> this page again for that group
 *   - a ledger           -> its Ledger Monthly Summary
 *   - "Opening Stock"    -> Opening Stock Summary
 *   - "Purchase Bills to Come" -> Purchase Bills Pending
 */
function TrialBalanceGroup() {
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
      actions={<TrialBalanceBackButton fallbackTo={tbPath('', dates)} />}
    />
  )

  if (!group) {
    return (
      <>
        {header}
        <ErrorMessage message="No group specified. Go back to the Trial Balance and click a line." />
      </>
    )
  }

  if (loading) return <>{header}<Loader /></>
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
          Click a row to drill further - into a sub-group, or into a ledger&apos;s monthly summary.
        </p>

        <DataTable
          columns={COLUMNS}
          rows={rows}
          onRowClick={(row) => navigate(drillPathForRow(row, dates))}
          isRowClickable={(row) => Boolean(drillPathForRow(row, dates))}
        />

        {rows.length === 0 && (
          <p className="table-hint">
            Tally has no sub-groups or ledgers under this name.{' '}
            <button
              type="button"
              className="link-button"
              onClick={() => navigate(tbPath('/ledger', { ledger: group, ...dates }))}
            >
              Open it as a ledger instead
            </button>
          </p>
        )}

        <div className="table-footer">
          <span>Total Debit: {formatCurrency(response.total_debit || 0)}</span>
          <span>Total Credit: {formatCurrency(response.total_credit || 0)}</span>
        </div>
      </Card>
    </>
  )
}

export default TrialBalanceGroup
