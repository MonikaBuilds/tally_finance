import { useSearchParams } from 'react-router'
import { useFetch } from '../../hooks/useFetch'
import PageHeader from '../../components/layout/PageHeader'
import ExportButtons from '../../components/common/ExportButtons'
import Loader from '../../components/common/Loader'
import ErrorMessage from '../../components/common/ErrorMessage'
import Card from '../../components/common/Card'
import DataTable from '../../components/common/DataTable'
import { formatCurrency, formatDate, formatQuantity } from '../../utils/format'
import { buildQuery, tbPath } from './tbRouting'

const COLUMNS = [
  { key: 'date', label: 'Date', render: (row) => formatDate(row.date) },
  { key: 'particulars', label: 'Particulars' },
  { key: 'order_number', label: 'Order No.' },
  {
    key: 'quantity',
    label: 'Quantity',
    align: 'right',
    render: (row) => formatQuantity(row.quantity),
  },
  {
    key: 'rate',
    label: 'Rate',
    align: 'right',
    render: (row) => formatCurrency(row.rate),
  },
  {
    key: 'value',
    label: 'Value',
    align: 'right',
    render: (row) => formatCurrency(row.value),
  },
]

/*
 * Trial Balance -> Purchase Bills to Come (Purchase Bills Pending).
 *
 * Shows goods received for which purchase bills have not yet been
 * received, matching Tally's "Purchase Bills to Come" report under
 * Current Liabilities.
 */
function TrialBalancePurchaseBillsPending() {
  const [searchParams] = useSearchParams()

  const fromDate = searchParams.get('from_date') || ''
  const toDate = searchParams.get('to_date') || ''

  const dates = { from_date: fromDate, to_date: toDate }

  const { data: response, loading, error } = useFetch(
    `/reports/trial-balance/purchase-bills-pending${buildQuery(dates)}`
  )

  const exportActions = (
    <ExportButtons
      basePath="/reports/trial-balance/purchase-bills-pending/export"
      filenameBase="purchase_bills_pending"
      params={{ from_date: fromDate, to_date: toDate }}
    />
  )

  const header = (
    <PageHeader
      title="Purchase Bills Pending"
      subtitle={fromDate && toDate ? `${fromDate} to ${toDate}` : undefined}
      backFallback={tbPath('', dates)}
      actions={exportActions}
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
