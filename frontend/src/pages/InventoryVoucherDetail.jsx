import { useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import { formatDate } from '../utils/format'
import { formatAmount } from '../utils/stockFormat'

function toQuery(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => (
      value !== undefined && value !== null && value !== ''
    ))
  ).toString()

  return query ? `?${query}` : ''
}

// Tally's own amounts for stock entries are signed (Dr/Cr); show the
// magnitude with two decimals like the voucher screen does.
const money = (value) => {
  const number = Math.abs(parseFloat(String(value ?? '').replace(/,/g, '')))
  return Number.isFinite(number) ? formatAmount(number) : value || ''
}

const ENTRY_COLUMNS = [
  { key: 'stock_item', label: 'Stock Item' },
  { key: 'godown', label: 'Godown' },
  { key: 'batch', label: 'Batch' },
  { key: 'actual_quantity', label: 'Actual Qty' },
  { key: 'billed_quantity', label: 'Billed Qty' },
  { key: 'rate', label: 'Rate' },
  { key: 'amount', label: 'Amount', align: 'right', render: (r) => money(r.amount) },
  { key: 'tracking_number', label: 'Tracking Number' },
]

// Order vouchers have no actual / billed split - Tally shows the item,
// quantity, rate, due date and amount.
const ORDER_ENTRY_COLUMNS = [
  { key: 'stock_item', label: 'Name of Item' },
  { key: 'actual_quantity', label: 'Quantity' },
  { key: 'rate', label: 'Rate' },
  { key: 'order_due_date', label: 'Due on' },
  { key: 'amount', label: 'Amount', align: 'right', render: (r) => money(r.amount) },
]

const LEDGER_COLUMNS = [
  { key: 'ledger', label: 'Ledger' },
  { key: 'amount', label: 'Amount', align: 'right', render: (r) => money(r.amount) },
]

function InventoryVoucherDetail() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)

  const voucherType = params.get('voucher_type') || ''
  const voucherNumber = params.get('voucher_number') || ''
  const voucherDate = params.get('date') || ''

  const query = {
    voucher_type: voucherType,
    voucher_number: voucherNumber,
    voucher_date: voucherDate || undefined,
  }

  const path = voucherType && voucherNumber
    ? `/reports/inventory-voucher${toQuery(query)}`
    : null

  const { data: response, loading, error } = useFetch(path)
  const voucher = response?.voucher || null

  return (
    <>
      <PageHeader
        title={
          voucher?.is_order
            ? 'Order Voucher Alteration (Secondary)'
            : 'Inventory Voucher Alteration (Secondary)'
        }
        subtitle={voucher ? `${voucher.voucher_type} No. ${voucher.voucher_number}` : 'Live data from Tally'}
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} /> Back
          </button>
        }
      />

      <Card>
        {!voucherType || !voucherNumber ? (
          <ErrorMessage message="Missing inventory voucher reference." />
        ) : loading ? (
          <Loader />
        ) : error ? (
          <ErrorMessage message={error} />
        ) : !response?.success ? (
          <ErrorMessage message={response?.error || response?.message || 'Voucher not found.'} />
        ) : !voucher ? (
          <div className="empty-state">This voucher was not returned by Tally.</div>
        ) : (
          <>
            <div className="meta-list">
              <div className="meta-item">
                <span>Date</span>
                <strong>{formatDate(voucher.date)}</strong>
              </div>
              {voucher.party && (
                <div className="meta-item">
                  <span>Party</span>
                  <strong>{voucher.party}</strong>
                </div>
              )}
              {voucher.reference && (
                <div className="meta-item">
                  <span>{voucher.is_order ? 'Order No.' : 'Reference'}</span>
                  <strong>{voucher.reference}</strong>
                </div>
              )}
              {Object.entries(voucher.voucher_godowns || {}).map(([name, value]) => (
                <div className="meta-item" key={name}>
                  <span>{name}</span>
                  <strong>{value}</strong>
                </div>
              ))}
              {voucher.reference_date && (
                <div className="meta-item">
                  <span>Reference Date</span>
                  <strong>{formatDate(voucher.reference_date)}</strong>
                </div>
              )}
              {voucher.is_cancelled && (
                <div className="meta-item">
                  <span>Status</span>
                  <strong className="status-cancelled">Cancelled</strong>
                </div>
              )}
            </div>

            <p className="table-hint">
              Inventory entries below are read directly from the Tally voucher response.
            </p>

            <DataTable
              columns={voucher.is_order ? ORDER_ENTRY_COLUMNS : ENTRY_COLUMNS}
              rows={voucher.inventory_entries || []}
            />

            {(voucher.ledger_entries || []).length > 0 && (
              <DataTable columns={LEDGER_COLUMNS} rows={voucher.ledger_entries} />
            )}

            {voucher.narration && (
              <p className="card-note voucher-narration">
                <strong>Narration:</strong> {voucher.narration}
              </p>
            )}

            <div className="table-footer">
              <span>Inventory Entries: {voucher.inventory_entry_count ?? 0}</span>
            </div>
          </>
        )}
      </Card>
    </>
  )
}

export default InventoryVoucherDetail
