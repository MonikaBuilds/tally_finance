import { useNavigate, useSearchParams, Link } from 'react-router'
import { ArrowLeft } from 'lucide-react'
import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
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
      render: (row) => (row.debit ? formatCurrency(row.debit) : ''),
    },
    {
      key: 'credit',
      label: 'Credit',
      align: 'right',
      render: (row) => (row.credit ? formatCurrency(row.credit) : ''),
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

  if (!group) {
    return <ErrorMessage message="No group specified. Go back and click a line to drill in." />
  }

  if (loading) return <Loader />
  if (error) return <ErrorMessage message={error} />
  if (!response?.success) return <ErrorMessage message={response?.error || response?.message} />

  const rows = response.report || []
  const columns = buildColumns(navigate, fromDate, toDate)

  return (
    <>
      <PageHeader
        title={`Group Summary: ${group}`}
        subtitle="Click a row to drill further - into a sub-group, or into a ledger's monthly summary"
      />

      <nav className="breadcrumbs">
        <Link to="/reports/profit-loss">
          <ArrowLeft size={16} />
          Back to Profit &amp; Loss
        </Link>
      </nav>

      <Card>
        <DataTable columns={columns} rows={rows} />
        <div className="table-footer">
          <span>Total</span>
          <span>
            {formatCurrency(response.total_debit || 0)} / {formatCurrency(response.total_credit || 0)}
          </span>
        </div>
      </Card>
    </>
  )
}

export default GroupSummary