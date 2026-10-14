import { useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import ExportButtons from '../components/common/ExportButtons'
import { formatDate } from '../utils/format'
import { formatAmount, formatQuantityWithUnit, toQuery } from '../utils/stockFormat'

/*
 * Stock Item Monthly Summary -> (click a month) -> Stock Item
 * Vouchers: Tally's own drill-down screen.
 *
 *   Opening Balance
 *   one line per voucher (Inwards / Outwards, closing on the last line
 *   of each day)
 *   (Sale Bills Pending) - delivery notes not yet billed - with the
 *   notes it is made of
 *   totals
 *
 * Everything is built by /reports/stock-item-vouchers.
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

  const path = itemName ? `/reports/stock-item-vouchers${toQuery(queryParams)}` : null
  const { data: response, loading, error } = useFetch(path)

  const unit = response?.unit
  const qty = (value) => formatQuantityWithUnit(value, unit)

  const opening = response?.opening
  const totals = response?.totals

  // Flatten the backend lines into table rows: Opening Balance, the
  // vouchers, each Bills Pending line followed by its notes, Totals.
  const rows = []

  if (response?.success) {
    rows.push({
      kind: 'opening',
      date: response.from,
      inward_quantity: opening?.quantity,
      inward_value: opening?.value,
      closing_quantity: opening?.quantity,
      closing_value: opening?.value,
    })

    for (const line of response.report || []) {
      rows.push(line)

      for (const child of line.children || []) {
        rows.push({ kind: 'pending_child', ...child, pending_side: line.pending_side })
      }
    }

    if (totals) rows.push({ kind: 'total', ...totals })
  }

  const hasValue = (value) => value !== undefined && value !== null

  const quantityCell = (row, key) => {
    const value = row[key]

    if (!hasValue(value)) return ''

    const text = qty(value)

    return row.kind === 'opening' || row.kind === 'total' ? <strong>{text}</strong> : text
  }

  // Tally prints no value on the Bills Pending line, only its quantity.
  const valueCell = (row, key) => {
    const value = row[key]

    if (!hasValue(value) || row.kind === 'pending') return ''

    const text = formatAmount(value)

    return row.kind === 'opening' || row.kind === 'total' ? <strong>{text}</strong> : text
  }

  const columns = [
    {
      key: 'date',
      label: 'Date',
      render: (r) => (r.kind === 'total' ? '' : r.date ? formatDate(r.date) : ''),
    },
    {
      key: 'particulars',
      label: 'Particulars',
      render: (r) => {
        if (r.kind === 'opening') return <strong>Opening Balance</strong>
        if (r.kind === 'total') return <strong>Totals</strong>
        if (r.kind === 'pending') return <strong><em>{r.particulars}</em></strong>
        if (r.kind === 'pending_child') return <em>{r.party}</em>
        return r.particulars
      },
    },
    { key: 'voucher_type', label: 'Vch Type', render: (r) => (r.kind === 'voucher' ? r.voucher_type : '') },
    {
      key: 'voucher_number',
      label: 'Vch No.',
      render: (r) => (r.kind === 'voucher' ? r.voucher_number : r.kind === 'pending_child' ? r.tracking_number : ''),
    },
    { key: 'inward_quantity', label: 'Inwards Qty', align: 'right', render: (r) => quantityCell(r, 'inward_quantity') },
    { key: 'inward_value', label: 'Inwards Value', align: 'right', render: (r) => valueCell(r, 'inward_value') },
    {
      key: 'outward_quantity',
      label: 'Outwards Qty',
      align: 'right',
      render: (r) => (r.kind === 'pending_child' ? qty(r.quantity) : quantityCell(r, 'outward_quantity')),
    },
    { key: 'outward_value', label: 'Outwards Value', align: 'right', render: (r) => valueCell(r, 'outward_value') },
    { key: 'closing_quantity', label: 'Closing Qty', align: 'right', render: (r) => quantityCell(r, 'closing_quantity') },
    { key: 'closing_value', label: 'Closing Value', align: 'right', render: (r) => valueCell(r, 'closing_value') },
  ]

  const billsPendingPath = (extra = {}) =>
    `/reports/stock-item-bills-pending${toQuery({
      item: itemName,
      from: fromDate,
      to: toDate,
      ...extra,
    })}`

  const isClickable = (row) =>
    row.kind === 'pending' ||
    row.kind === 'pending_child' ||
    (row.kind === 'voucher' && Boolean(row.voucher_type && row.voucher_number))

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

            <DataTable
              columns={columns}
              rows={rows}
              isRowClickable={isClickable}
              onRowClick={(row) => {
                if (row.kind === 'pending') {
                  navigate(billsPendingPath())
                  return
                }

                if (row.kind === 'pending_child') {
                  navigate(billsPendingPath({ tracking_number: row.tracking_number, party: row.party }))
                  return
                }

                navigate(`/reports/inventory-voucher${toQuery({
                  voucher_type: row.voucher_type,
                  voucher_number: row.voucher_number,
                  date: row.date,
                })}`)
              }}
            />
          </>
        )}
      </Card>
    </>
  )
}

export default StockItemVouchers
