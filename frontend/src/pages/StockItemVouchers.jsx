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
  { key: 'party', label: 'Particulars' },
  { key: 'voucher_type', label: 'Vch Type' },
  { key: 'voucher_number', label: 'Vch No.' },
  { key: 'quantity', label: 'Quantity', align: 'right', render: (r) => formatQuantity(r.quantity) },
  { key: 'rate', label: 'Rate', align: 'right', render: (r) => formatCurrency(r.rate) },
  { key: 'value', label: 'Value', align: 'right', render: (r) => formatCurrency(r.value) },
  { key: 'tracking_number', label: 'Tracking Number' },
  { key: 'godown', label: 'Godown' },
  { key: 'batch', label: 'Batch' },
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

  const pendingPath = itemName
    ? `/reports/stock-item-bills-pending${toQuery({
        stock_item_name: itemName,
        from_date: fromDate || undefined,
        to_date: toDate || undefined,
      })}`
    : null

  const { data: pendingResponse } = useFetch(pendingPath)

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
              <button
                type="button"
                className="btn btn-secondary"
                onClick={() => navigate(`/reports/stock-item-bills-pending${toQuery({
                  item: itemName,
                  from: fromDate,
                  to: toDate,
                })}`)}
              >
                Bills Pending
              </button>
            </div>
            <DataTable
              columns={COLUMNS}
              rows={response.report || []}
              onRowClick={(row) => {
                if (!row.voucher_type || !row.voucher_number) return

                navigate(`/reports/inventory-voucher${toQuery({
                  voucher_type: row.voucher_type,
                  voucher_number: row.voucher_number,
                  date: row.date,
                })}`)
              }}
            />

            {pendingResponse?.success && (pendingResponse.report || []).length > 0 && (
              <div className="card-section">
                <p className="table-hint">Bills Made but Goods not Delivered</p>
                <DataTable
                  columns={[
                    { key: 'date', label: 'Date', render: (row) => formatDate(row.date) },
                    { key: 'tracking_number', label: 'Tracking Number' },
                    { key: 'party', label: 'Name of Party' },
                    { key: 'initial_quantity', label: 'Initial Quantity', align: 'right', render: (row) => formatQuantity(row.initial_quantity) },
                    { key: 'pending_quantity', label: 'Pending Quantity', align: 'right', render: (row) => formatQuantity(row.pending_quantity) },
                    { key: 'rate', label: 'Rate', align: 'right', render: (row) => formatCurrency(row.rate) },
                    { key: 'value', label: 'Value', align: 'right', render: (row) => formatCurrency(row.value) },
                  ]}
                  rows={pendingResponse.report}
                  onRowClick={(row) => navigate(`/reports/stock-item-bills-pending${toQuery({
                    item: itemName,
                    from: fromDate,
                    to: toDate,
                    tracking_number: row.tracking_number,
                    party: row.party,
                  })}`)}
                />
              </div>
            )}
          </>
        )}
      </Card>
    </>
  )
}

export default StockItemVouchers
