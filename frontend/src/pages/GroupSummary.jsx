import { useNavigate, useSearchParams } from 'react-router'
import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import ExportButtons from '../components/common/ExportButtons'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import { formatCurrency } from '../utils/format'

// The page Tally shows when you double-click a group line on the P&L,
// Balance Sheet, or another Group Summary screen - e.g. clicking
// "Indirect Expenses" lands here showing Office Exp (still a group),
// clicking that lands here again showing Office Rent Exp / Sweeper
// Salary / Travelling Expense (now ledgers). Each row drills further:
// another group re-enters this same page for that name, a ledger goes
// to its monthly summary on the Ledger page.
function buildColumns(navigate, fromDate, toDate) {
  function drillPath(row) {
    if (row.is_ledger) {
      const params = new URLSearchParams({
        ledger: row.name,
        view: 'monthly',
      })
      if (fromDate) params.set('from_date', fromDate)
      if (toDate) params.set('to_date', toDate)
      return `/reports/ledger?${params.toString()}`
    }

    const params = new URLSearchParams({ group: row.name })
    if (fromDate) params.set('from_date', fromDate)
    if (toDate) params.set('to_date', toDate)
    return `/reports/group-summary?${params.toString()}`
  }

  return [
    {
      key: 'name',
      label: 'Particulars',
      render: (row) => (
        <button
          type="button"
          className="link-button"
          onClick={() => navigate(drillPath(row))}
          title={row.is_ledger ? 'View ledger monthly summary' : 'View group summary'}
        >
          {row.name}
        </button>
      ),
    },
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
}

function GroupSummary() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const group = searchParams.get('group') || ''
  const fromDate = searchParams.get('from_date') || ''
  const toDate = searchParams.get('to_date') || ''

  const query = new URLSearchParams({ group })
  if (fromDate) query.set('from_date', fromDate)
  if (toDate) query.set('to_date', toDate)

  const { data: response, loading, error } = useFetch(
    group ? `/reports/group-summary?${query.toString()}` : null
  )

  const subtitle = fromDate && toDate ? `${fromDate} to ${toDate}` : undefined
  const fallbackUrl = fromDate && toDate
    ? `/reports/balance-sheet?from_date=${encodeURIComponent(fromDate)}&to_date=${encodeURIComponent(toDate)}`
    : '/reports/balance-sheet'

  if (!group) {
    return (
      <>
        <PageHeader title="Group Summary" backFallback="/reports/balance-sheet" />
        <ErrorMessage message="No group specified. Go back and click a line to drill in." />
      </>
    )
  }

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
      subtitle={subtitle}
      backFallback={fallbackUrl}
      actions={exportActions}
    />
  )

  if (loading) return <>{header}<Loader /></>
  if (error) return <>{header}<ErrorMessage message={error} /></>
  if (!response?.success) {
    return <>{header}<ErrorMessage message={response?.error || response?.message} /></>
  }

  const rows = response.report || []
  const columns = buildColumns(navigate, fromDate, toDate)

  return (
    <>
      {header}

      <Card>
        <DataTable columns={columns} rows={rows} />
        <div className="table-footer">
          <span>Total Debit: {formatCurrency(response.total_debit || 0)}</span>
          <span>Total Credit: {formatCurrency(response.total_credit || 0)}</span>
        </div>
      </Card>
    </>
  )
}

export default GroupSummary
