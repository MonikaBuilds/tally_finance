import { useSearchParams } from 'react-router'
import { useFetch } from '../../hooks/useFetch'
import PageHeader from '../../components/layout/PageHeader'
import Loader from '../../components/common/Loader'
import ErrorMessage from '../../components/common/ErrorMessage'
import Card from '../../components/common/Card'
import DataTable from '../../components/common/DataTable'
import { formatCurrency, formatDate, formatQuantity } from '../../utils/format'
import TrialBalanceBackButton from './TrialBalanceBackButton'
import { buildQuery, tbPath } from './tbRouting'

const COLUMNS = [
  { key: 'date', label: 'Date', render: (row) => formatDate(row.date) },
  { key: 'tracking_number', label: 'Tracking Number' },
  { key: 'stock_item', label: 'Name of Item' },
  { key: 'party', label: 'From' },
  { key: 'initial_quantity', label: 'Initial Quantity', align: 'right', render: (row) => formatQuantity(row.initial_quantity) },
  { key: 'pending_quantity', label: 'Pending Quantity', align: 'right', render: (row) => formatQuantity(row.pending_quantity) },
  { key: 'rate', label: 'Rate', align: 'right', render: (row) => formatCurrency(row.rate) },
  { key: 'value', label: 'Value', align: 'right', render: (row) => formatCurrency(row.value) },
]

/*
 * Trial Balance -> Purchase Accounts -> Purchase Bills to Come ->
 * Purchase Bills Pending: goods received (Receipt Notes) for the
 * selected period, item by item, from the Tally-backed
 * /reports/trial-balance/purchase-bills-pending API.
 */
function TrialBalancePurchaseBillsPending() {
  const [searchParams] = useSearchParams()

  const fromDate = searchParams.get('from_date') || ''
  const toDate = searchParams.get('to_date') || ''

  const dates = { from_date: fromDate, to_date: toDate }

  const { data: response, loading, error } = useFetch(
    `/reports/trial-balance/purchase-bills-pending${buildQuery(dates)}`
  )

  const header = (
    <PageHeader
      title="Purchase Bills Pending"
      subtitle={fromDate && toDate ? `${fromDate} to ${toDate}` : undefined}
      actions={<TrialBalanceBackButton fallbackTo={tbPath('', dates)} />}
    />
  )

  if (loading) return <>{header}<Loader /></>
  if (error) return <>{header}<ErrorMessage message={error} /></>
  if (!response?.success) {
    return <>{header}<ErrorMessage message={response?.error || response?.message} /></>
  }

  return (
    <>
      {header}

      <Card title="Goods Recd. but Bills not Recd.">
        <DataTable columns={COLUMNS} rows={response.report || []} />

        <div className="table-footer">
          <span>Total Value: {formatCurrency(response.total_value || 0)}</span>
        </div>
      </Card>
    </>
  )
}

export default TrialBalancePurchaseBillsPending
