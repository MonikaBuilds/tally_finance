import { useLocation, useNavigate } from 'react-router'
import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import ExportButtons from '../components/common/ExportButtons'
import { formatDate } from '../utils/format'
import { formatSignedAmount, formatSignedQuantityWithUnit, toQuery } from '../utils/stockFormat'

function formatQty(row) {
  const signed = row.signed_quantity !== undefined ? row.signed_quantity : row.quantity
  return formatSignedQuantityWithUnit(signed, row.base_units || row.unit)
}

function formatRate(row) {
  if (row.rate_value === undefined || row.rate_value === null) return ''
  const number = Number(row.rate_value)
  if (!Number.isFinite(number)) return ''
  return `₹ ${Math.abs(number).toLocaleString('en-IN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })}`
}

function formatAmount(row) {
  const signed = row.signed_amount !== undefined ? row.signed_amount : row.value
  return formatSignedAmount(signed)
}

const COLUMNS = [
  { key: 'date', label: 'Date', render: (r) => formatDate(r.date) },
  { key: 'particulars', label: 'Particulars' },
  { key: 'voucher_type', label: 'Vch Type' },
  { key: 'voucher_number', label: 'Vch No.' },
  { key: 'quantity', label: 'Quantity', align: 'right', render: formatQty },
  { key: 'rate_value', label: 'Rate', align: 'right', render: formatRate },
  { key: 'value', label: 'Value', align: 'right', render: formatAmount },
]

/*
 * Stock Item Vouchers / Godown Vouchers (item-level).
 *
 * All voucher lines affecting one stock item for a date range. Reached
 * by clicking an item on the Stock Summary or a month on the Stock
 * Item Monthly Summary.
 */
function StockItemVouchers() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)

  const itemName = params.get('item') || ''
  const godownName = params.get('godown') || ''
  const fromDate = params.get('from') || ''
  const toDate = params.get('to') || ''

  const queryParams = {
    stock_item_name: itemName,
    godown_name: godownName,
    from_date: fromDate || undefined,
    to_date: toDate || undefined,
  }

  const path = itemName
    ? `/reports/stock-item-vouchers${toQuery(queryParams)}`
    : null

  const { data: response, loading, error } = useFetch(path)

  const rows = response?.report || []

  const totals = rows.reduce(
    (acc, row) => {
      const qty = row.signed_quantity !== undefined ? Number(row.signed_quantity) : Number(row.quantity)
      const amt = row.signed_amount !== undefined ? Number(row.signed_amount) : Number(row.value)
      if (Number.isFinite(qty)) acc.quantity += qty
      if (Number.isFinite(amt)) acc.value += amt
      return acc
    },
    { quantity: 0, value: 0 }
  )

  const units = new Set(rows.map((row) => row.base_units || row.unit).filter(Boolean))
  const singleUnit = units.size === 1 ? [...units][0] : ''

  return (
    <>
      <PageHeader
        title={
          godownName
            ? `Godown Vouchers: ${godownName}`
            : `Stock Item Vouchers${itemName ? `: ${itemName}` : ''}`
        }
        subtitle={fromDate && toDate ? `${fromDate} to ${toDate}` : undefined}
        backFallback="/reports/inventory"
        actions={
          <ExportButtons
            basePath="/reports/stock-item-vouchers/export"
            params={queryParams}
            filenameBase="stock_item_vouchers"
          />
        }
      />

      <Card>
        {!itemName && <ErrorMessage message="No stock item was specified." />}
        {itemName && loading && <Loader />}
        {itemName && error && <ErrorMessage message={error} />}

        {itemName && !loading && !error && response?.success && (
          <>
            <div className="meta-list">
              <div className="meta-item">
                <span>Stock Item</span>
                <strong>{itemName}</strong>
              </div>
              {godownName && (
                <div className="meta-item">
                  <span>Godown</span>
                  <strong>{godownName}</strong>
                </div>
              )}
            </div>

            <DataTable
              columns={COLUMNS}
              rows={rows}
              onRowClick={(row) => {
                if (!row.voucher_type || !row.voucher_number) return
                navigate(
                  `/reports/inventory-voucher${toQuery({
                    voucher_type: row.voucher_type,
                    voucher_number: row.voucher_number,
                    date: row.date,
                  })}`
                )
              }}
              isRowClickable={(row) => Boolean(row.voucher_type && row.voucher_number)}
            />

            <div className="table-footer">
              <span>
                Total Quantity: {formatSignedQuantityWithUnit(totals.quantity, singleUnit)}
              </span>
              <span>Total Value: {formatSignedAmount(totals.value)}</span>
            </div>
          </>
        )}
      </Card>
    </>
  )
}

export default StockItemVouchers
