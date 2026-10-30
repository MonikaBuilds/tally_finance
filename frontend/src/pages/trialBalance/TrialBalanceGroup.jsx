import { Navigate, useNavigate, useSearchParams } from 'react-router'
import { useFetch } from '../../hooks/useFetch'
import PageHeader from '../../components/layout/PageHeader'
import ExportButtons from '../../components/common/ExportButtons'
import Loader from '../../components/common/Loader'
import ErrorMessage from '../../components/common/ErrorMessage'
import Card from '../../components/common/Card'
import DataTable from '../../components/common/DataTable'
import { formatCurrency } from '../../utils/format'
import { buildQuery, drillPathForRow, ledgerMonthlyPath, tbPath } from './tbRouting'

const COLUMNS = [
  { key: 'name', label: 'Particulars' },
  {
    key: 'debit',
    label: 'Debit',
    align: 'right',
    render: (row) => (row.debit ? formatCurrency(row.debit) : '-'),
  },
  {
    key: 'credit',
    label: 'Credit',
    align: 'right',
    render: (row) => (row.credit ? formatCurrency(row.credit) : '-'),
  },
  {
    key: 'closing',
    label: 'Closing Balance',
    align: 'right',
    render: (row) => {
      const debit = Number(row.debit) || 0
      const credit = Number(row.credit) || 0
      const diff = debit - credit
      if (Math.abs(diff) < 0.001) {
        if (debit > 0) return `${formatCurrency(debit)} Dr`
        if (credit > 0) return `${formatCurrency(credit)} Cr`
        return '-'
      }
      return diff > 0
        ? `${formatCurrency(diff)} Dr`
        : `${formatCurrency(Math.abs(diff))} Cr`
    },
  },
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

  const exportActions = (
    <ExportButtons
      basePath="/reports/group-summary/export"
      filenameBase={`group_${group}`}
      params={{ group, from_date: fromDate, to_date: toDate }}
    />
  )

  const header = (
    <PageHeader
      title={`Group Summary: ${group}`}
      subtitle={fromDate && toDate ? `${fromDate} to ${toDate}` : undefined}
      backFallback={tbPath('', dates)}
      actions={exportActions}
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

  // The line clicked is a ledger, not a group: Tally opens its Ledger
  // Monthly Summary, so follow it there.
  if (response.resolved_as === 'ledger') {
    return <Navigate to={ledgerMonthlyPath(group, dates)} replace />
  }

  const rows = response.report || []

  return (
    <>
      {header}

      <Card>
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
              onClick={() => navigate(ledgerMonthlyPath(group, dates))}
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
