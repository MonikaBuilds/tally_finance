import { useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import { formatCurrency, formatDate, formatQuantity } from '../utils/format'

function toQuery(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => (
      value !== undefined && value !== null && value !== ''
    ))
  ).toString()

  return query ? `?${query}` : ''
}

const SUMMARY_COLUMNS = [
  { key: 'date', label: 'Date', render: (row) => formatDate(row.date) },
  { key: 'tracking_number', label: 'Tracking Number' },
  { key: 'party', label: 'Name of Party' },
  { key: 'initial_quantity', label: 'Initial Quantity', align: 'right', render: (row) => formatQuantity(row.initial_quantity) },
  { key: 'pending_quantity', label: 'Pending Quantity', align: 'right', render: (row) => formatQuantity(row.pending_quantity) },
  { key: 'rate', label: 'Rate (Disc %)', align: 'right', render: (row) => formatCurrency(row.rate) },
  { key: 'value', label: 'Value', align: 'right', render: (row) => formatCurrency(row.value) },
]

const DETAIL_COLUMNS = [
  { key: 'date', label: 'Date', render: (row) => formatDate(row.date) },
  { key: 'voucher_type', label: 'Particulars' },
  { key: 'voucher_number', label: 'Vch No.' },
  { key: 'party', label: 'Name of Party' },
  { key: 'quantity', label: 'Quantity', align: 'right', render: (row) => formatQuantity(row.quantity) },
  { key: 'rate', label: 'Rate', align: 'right', render: (row) => formatCurrency(row.rate) },
  { key: 'value', label: 'Value', align: 'right', render: (row) => formatCurrency(row.value) },
  { key: 'reference', label: 'Reference' },
  { key: 'godown', label: 'Godown' },
  { key: 'batch', label: 'Batch' },
]

function StockItemBillsPending() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)

  const itemName = params.get('item') || ''
  const fromDate = params.get('from') || ''
  const toDate = params.get('to') || ''
  const trackingNumber = params.get('tracking_number') || ''
  const party = params.get('party') || ''

  const query = {
    stock_item_name: itemName,
    from_date: fromDate || undefined,
    to_date: toDate || undefined,
    tracking_number: trackingNumber || undefined,
    party: party || undefined,
  }

  const path = itemName
    ? `/reports/stock-item-bills-pending${toQuery(query)}`
    : null

  const { data: response, loading, error } = useFetch(path)

  const detailView = Boolean(trackingNumber)
  const rows = response?.report || []
  const details = response?.details || []

  return (
    <>
      <PageHeader
        title={detailView ? 'Bills Pending' : 'Sales Bills Pending'}
        subtitle={
          itemName
            ? `${itemName}${party ? ` — ${party}` : ''}${fromDate && toDate ? ` · ${fromDate} to ${toDate}` : ''}`
            : undefined
        }
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

        {itemName && !loading && !error && response?.success && !detailView && (
          <>
            <p className="table-hint">
              Bills Made but Goods not Delivered
            </p>
            <DataTable
              columns={SUMMARY_COLUMNS}
              rows={rows}
              onRowClick={(row) => navigate(`/reports/stock-item-bills-pending${toQuery({
                item: itemName,
                from: fromDate,
                to: toDate,
                tracking_number: row.tracking_number,
                party: row.party,
              })}`)}
            />
          </>
        )}

        {itemName && !loading && !error && response?.success && detailView && (
          <>
            <div className="meta-list">
              <div className="meta-item">
                <span>Stock Item</span>
                <strong>{itemName}</strong>
              </div>
              {party && (
                <div className="meta-item">
                  <span>Name of Party</span>
                  <strong>{party}</strong>
                </div>
              )}
              <div className="meta-item">
                <span>Tracking Number</span>
                <strong>{trackingNumber}</strong>
              </div>
            </div>

            <p className="table-hint">
              Pending bill details are read from the Tally inventory voucher response.
            </p>

            <DataTable columns={DETAIL_COLUMNS} rows={details} />
          </>
        )}
      </Card>
    </>
  )
}

export default StockItemBillsPending
