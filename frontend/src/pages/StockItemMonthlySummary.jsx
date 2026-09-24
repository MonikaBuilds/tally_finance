import { useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import { formatCurrency, formatQuantity, formatMonthKey, financialYearRange, monthKeyToRange } from '../utils/format'

/*
 * Stock -> Stock Summary -> (click item) -> Stock Item Monthly Summary.
 *
 * Matches Tally's own "Stock Item Monthly Summary" screen: an Opening
 * Balance row, followed by one row per month showing Inward / Outward
 * quantity+value and a running Closing balance.
 *
 * Both the opening balance and the monthly movement are fetched live
 * from Tally (via the existing /stock-item and /stock-movement
 * endpoints) - the monthly buckets are built here, the same way
 * LedgerMonthlySummary already builds month buckets from raw entries.
 */

function monthKeyForDate(dateStr) {
  if (!dateStr) return null
  const value = String(dateStr).trim()
  const iso = value.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (iso) return `${iso[1]}-${iso[2]}`
  return null
}

// One day before `dateStr` (YYYY-MM-DD), for fetching the item's
// closing balance just before the period starts (= opening balance).
function dayBefore(dateStr) {
  const d = new Date(`${dateStr}T00:00:00`)
  d.setDate(d.getDate() - 1)
  return d.toISOString().slice(0, 10)
}

function toQuery(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ).toString()
  return query ? `?${query}` : ''
}

function StockItemMonthlySummary() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)

  const itemName = params.get('item') || ''
  const fy = financialYearRange(0)
  const fromDate = params.get('from') || fy.from
  const toDate = params.get('to') || fy.to

  const openingPath = itemName
    ? `/reports/stock-item${toQuery({ stock_item_name: itemName, to_date: dayBefore(fromDate) })}`
    : null

  const movementPath = itemName
    ? `/reports/stock-movement${toQuery({
        stock_item_name: itemName,
        from_date: fromDate,
        to_date: toDate,
      })}`
    : null

  const { data: openingResponse, loading: openingLoading, error: openingError } = useFetch(openingPath)
  const { data: movementResponse, loading: movementLoading, error: movementError } = useFetch(movementPath)

  const opening = openingResponse?.item || null

  const monthlyRows = useMemo(() => {
    const rows = Array.isArray(movementResponse?.report) ? movementResponse.report : []

    const buckets = new Map()

    for (const row of rows) {
      const key = monthKeyForDate(row.date)
      if (!key) continue

      if (!buckets.has(key)) {
        buckets.set(key, {
          key,
          month: formatMonthKey(key),
          inward_qty: 0,
          inward_value: 0,
          outward_qty: 0,
          outward_value: 0,
        })
      }

      const bucket = buckets.get(key)
      const qty = Number(row.quantity) || 0
      const value = Number(row.value) || 0

      if (qty >= 0) {
        bucket.inward_qty += qty
        bucket.inward_value += Math.abs(value)
      } else {
        bucket.outward_qty += Math.abs(qty)
        bucket.outward_value += Math.abs(value)
      }
    }

    const sorted = Array.from(buckets.values()).sort((a, b) => a.key.localeCompare(b.key))

    let runningQty = Number(opening?.closing_quantity) || 0
    let runningValue = Number(opening?.closing_value) || 0

    return sorted.map((bucket) => {
      runningQty += bucket.inward_qty - bucket.outward_qty
      runningValue += bucket.inward_value - bucket.outward_value

      const range = monthKeyToRange(bucket.key)

      return {
        ...bucket,
        closing_qty: runningQty,
        closing_value: runningValue,
        from: range?.from,
        to: range?.to,
      }
    })
  }, [movementResponse, opening])

  const columns = [
    { key: 'month', label: 'Particulars' },
    { key: 'inward_qty', label: 'Inward Qty', align: 'right', render: (r) => formatQuantity(r.inward_qty) },
    { key: 'inward_value', label: 'Inward Value', align: 'right', render: (r) => formatCurrency(r.inward_value) },
    { key: 'outward_qty', label: 'Outward Qty', align: 'right', render: (r) => formatQuantity(r.outward_qty) },
    { key: 'outward_value', label: 'Outward Value', align: 'right', render: (r) => formatCurrency(r.outward_value) },
    { key: 'closing_qty', label: 'Closing Qty', align: 'right', render: (r) => formatQuantity(r.closing_qty) },
    { key: 'closing_value', label: 'Closing Value', align: 'right', render: (r) => formatCurrency(r.closing_value) },
  ]

  const loading = openingLoading || movementLoading
  const error = openingError || movementError

  return (
    <>
      <PageHeader
        title={`Stock Item Monthly Summary${itemName ? `: ${itemName}` : ''}`}
        subtitle={`${fromDate} to ${toDate}`}
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

        {itemName && !loading && !error && (
          <>
            <div className="table-footer">
              <span>
                Opening Balance: {formatQuantity(opening?.closing_quantity ?? 0)}{' '}
                ({formatCurrency(opening?.closing_value ?? 0)})
              </span>
            </div>

            <p className="table-hint">Click a month to view that month's stock item vouchers.</p>

            <DataTable
              columns={columns}
              rows={monthlyRows}
              onRowClick={(row) =>
                navigate(
                  `/reports/stock-item-vouchers${toQuery({
                    item: itemName,
                    from: row.from,
                    to: row.to,
                  })}`
                )
              }
            />
          </>
        )}
      </Card>
    </>
  )
}

export default StockItemMonthlySummary
