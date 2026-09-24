import { useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import ExportButtons from '../components/common/ExportButtons'
import { formatCurrency, formatQuantity, formatDate } from '../utils/format'

function toQuery(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ).toString()
  return query ? `?${query}` : ''
}

const COLUMNS = [
  { key: 'date', label: 'Date', render: (r) => formatDate(r.date) },
  { key: 'voucher_type', label: 'Vch Type' },
  { key: 'voucher_number', label: 'Vch No.' },
  { key: 'party', label: 'Party' },
  { key: 'quantity', label: 'Quantity', align: 'right', render: (r) => formatQuantity(r.quantity) },
  { key: 'rate', label: 'Rate', align: 'right', render: (r) => formatCurrency(r.rate) },
  { key: 'value', label: 'Value', align: 'right', render: (r) => formatCurrency(r.value) },
  { key: 'direction', label: 'Movement' },
]

/*
 * Stock Item Monthly Summary -> (click a month) -> Stock Item
 * Vouchers - the voucher-level detail for that item in that month,
 * matching Tally's own "Stock Item Vouchers" drill-down screen.
 */
function StockItemVouchers() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)

  const itemName = params.get('item') || ''
  const fromDate = params.get('from') || ''
  const toDate = params.get('to') || ''

  const queryParams = {
    stock_item_name: itemName || undefined,
    from_date: fromDate || undefined,
    to_date: toDate || undefined,
  }

  const path = itemName ? `/reports/stock-movement${toQuery(queryParams)}` : null
  const { data: response, loading, error } = useFetch(path)

  return (
    <>
      <PageHeader
        title={`Stock Item Vouchers${itemName ? `: ${itemName}` : ''}`}
        subtitle={fromDate && toDate ? `${fromDate} to ${toDate}` : undefined}
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} /> Back
          </button>
        }
      />

      <Card>
        {!itemName && <ErrorMessage message="No stock item was specified." />}
        {itemName && loading && <Loader />}
        {itemName && error && <ErrorMessage message={error} />}

        {itemName && !loading && !error && response?.success && (
          <>
            <div className="card-toolbar">
              <ExportButtons
                basePath="/reports/stock-movement/export"
                params={queryParams}
                filenameBase="stock_item_vouchers"
              />
            </div>
            <DataTable columns={COLUMNS} rows={response.report || []} />
          </>
        )}
      </Card>
    </>
  )
}

export default StockItemVouchers
