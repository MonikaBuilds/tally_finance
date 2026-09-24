import { useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import { formatCurrency, formatQuantity, formatMonthKey, financialYearRange } from '../utils/format'

function monthKeyForDate(dateStr) {
  if (!dateStr) return null
  const value = String(dateStr).trim()
  const iso = value.match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (iso) return `${iso[1]}-${iso[2]}`
  return null
}

function toQuery(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ).toString()
  return query ? `?${query}` : ''
}

/*
 * Location Summary -> (click an item, or "view all") -> Location
 * Monthly Summary: month-wise Inward / Outward movement at this
 * location, optionally scoped to one stock item, matching Tally's
 * own Location Monthly Summary screen.
 */
function LocationMonthlySummary() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)

  const locationName = params.get('location') || ''
  const itemName = params.get('item') || ''
  const fy = financialYearRange(0)
  const fromDate = params.get('from') || fy.from
  const toDate = params.get('to') || fy.to

  const path = locationName
    ? `/reports/stock-movement${toQuery({
        godown_name: locationName,
        stock_item_name: itemName || undefined,
        from_date: fromDate,
        to_date: toDate,
      })}`
    : null

  const { data: response, loading, error } = useFetch(path)

  const monthlyRows = useMemo(() => {
    const rows = Array.isArray(response?.report) ? response.report : []
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

    let runningQty = 0
    let runningValue = 0

    return Array.from(buckets.values())
      .sort((a, b) => a.key.localeCompare(b.key))
      .map((bucket) => {
        runningQty += bucket.inward_qty - bucket.outward_qty
        runningValue += bucket.inward_value - bucket.outward_value
        return { ...bucket, closing_qty: runningQty, closing_value: runningValue }
      })
  }, [response])

  const columns = [
    { key: 'month', label: 'Particulars' },
    { key: 'inward_qty', label: 'Inward Qty', align: 'right', render: (r) => formatQuantity(r.inward_qty) },
    { key: 'inward_value', label: 'Inward Value', align: 'right', render: (r) => formatCurrency(r.inward_value) },
    { key: 'outward_qty', label: 'Outward Qty', align: 'right', render: (r) => formatQuantity(r.outward_qty) },
    { key: 'outward_value', label: 'Outward Value', align: 'right', render: (r) => formatCurrency(r.outward_value) },
    { key: 'closing_qty', label: 'Closing Qty', align: 'right', render: (r) => formatQuantity(r.closing_qty) },
    { key: 'closing_value', label: 'Closing Value', align: 'right', render: (r) => formatCurrency(r.closing_value) },
  ]

  return (
    <>
      <PageHeader
        title={`Location Monthly Summary: ${locationName}${itemName ? ` — ${itemName}` : ''}`}
        subtitle={`${fromDate} to ${toDate}`}
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} /> Back
          </button>
        }
      />

      <Card>
        {!locationName && <ErrorMessage message="No location was specified." />}
        {locationName && loading && <Loader />}
        {locationName && error && <ErrorMessage message={error} />}
        {locationName && !loading && !error && <DataTable columns={columns} rows={monthlyRows} />}
      </Card>
    </>
  )
}

export default LocationMonthlySummary
