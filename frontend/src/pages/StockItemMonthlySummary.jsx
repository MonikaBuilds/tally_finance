import { useNavigate, useSearchParams } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import { formatMonthKey } from '../utils/format'
import { formatAmount, formatQuantityWithUnit, toQuery } from '../utils/stockFormat'

/*
 * Stock Item Monthly Summary - every month of the period, like Tally.
 *
 * Inwards / Outwards come from the item's vouchers; the Closing Balance
 * of each month is Tally's own figure for that month end (its value
 * follows Tally's valuation method). All of it is built by the backend
 * endpoint /reports/stock-item-monthly; nothing is calculated here.
 *
 * Period: ?from / ?to when given (drill-downs always pass them).
 * Otherwise the backend picks the latest financial year that has stock
 * activity in Tally and returns it as from / to.
 */
function StockItemMonthlySummary() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const itemName = searchParams.get('item') || ''

  // ?location=<godown> turns this into Tally's Godown Monthly Summary
  // (same screen, scoped to one godown).
  const godown = searchParams.get('location') || ''

  const path = itemName
    ? `/reports/stock-item-monthly${toQuery({
        stock_item_name: itemName,
        godown_name: godown,
        from_date: searchParams.get('from'),
        to_date: searchParams.get('to'),
      })}`
    : null

  const { data: response, loading, error } = useFetch(path)

  const from = response?.from || searchParams.get('from')
  const to = response?.to || searchParams.get('to')

  const unit = response?.unit
  const rows = Array.isArray(response?.report) ? response.report : []
  const qty = (value) => formatQuantityWithUnit(value, unit)

  const columns = [
    { key: 'month', label: 'Particulars', render: (r) => formatMonthKey(r.month) },
    { key: 'inward_quantity', label: 'Inwards Qty', align: 'right', render: (r) => (r.inward_quantity ? qty(r.inward_quantity) : '') },
    { key: 'inward_value', label: 'Inwards Value', align: 'right', render: (r) => (r.inward_value ? formatAmount(r.inward_value) : '') },
    { key: 'outward_quantity', label: 'Outwards Qty', align: 'right', render: (r) => (r.outward_quantity ? qty(r.outward_quantity) : '') },
    { key: 'outward_value', label: 'Outwards Value', align: 'right', render: (r) => (r.outward_value ? formatAmount(r.outward_value) : '') },
    { key: 'closing_quantity', label: 'Closing Qty', align: 'right', render: (r) => qty(r.closing_quantity) },
    { key: 'closing_value', label: 'Closing Value', align: 'right', render: (r) => formatAmount(r.closing_value) },
  ]

  const total = (key) => rows.reduce((sum, r) => sum + (r[key] || 0), 0)
  const last = rows[rows.length - 1]

  return (
    <>
      <PageHeader
        title={
          godown
            ? `Godown Monthly Summary: ${godown}${itemName ? ` — ${itemName}` : ''}`
            : `Stock Item Monthly Summary${itemName ? `: ${itemName}` : ''}`
        }
        subtitle={from && to ? `${from} to ${to}` : undefined}
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
        {itemName && !loading && !error && response && !response.success && (
          <ErrorMessage message={response.error || response.message || 'Unable to load the monthly summary.'} />
        )}

        {itemName && !loading && !error && response?.success && (
          <>
            <div className="table-footer">
              <span>
                Opening Balance: {qty(response.opening?.quantity)} · {formatAmount(response.opening?.value)}
              </span>
            </div>

            <p className="table-hint">
              Click a month to view that month's {godown ? 'godown' : 'stock item'} vouchers.
            </p>
            {response.approximate && (
              <p className="table-hint">
                This item is held in more than one godown, so this godown's closing figures are worked
                out from its opening allocation and vouchers at Tally's closing rate.
              </p>
            )}

            <DataTable
              columns={columns}
              rows={rows}
              onRowClick={(row) =>
                navigate(
                  godown
                    ? `/reports/location-vouchers${toQuery({ location: godown, item: itemName, from: row.from, to: row.to })}`
                    : `/reports/stock-item-vouchers${toQuery({ item: itemName, from: row.from, to: row.to })}`
                )
              }
            />

            {rows.some((r) => r.pending_bills_quantity) && (
              <p className="table-hint">
                Outwards quantity includes Tally's Sale / Purchase Bills Pending adjustment
                (delivered but not yet billed); Tally does not itemise its value.
              </p>
            )}

            {last && (
              <div className="table-footer">
                <span>
                  Grand Total — Inwards {qty(total('inward_quantity'))} · {formatAmount(total('inward_value'))} ·
                  Outwards {qty(total('outward_quantity'))} · {formatAmount(total('outward_value'))} ·
                  Closing {qty(last.closing_quantity)} · {formatAmount(last.closing_value)}
                </span>
              </div>
            )}
          </>
        )}
      </Card>
    </>
  )
}

export default StockItemMonthlySummary
