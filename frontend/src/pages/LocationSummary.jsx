import { useMemo } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import { formatCurrency, formatQuantity, financialYearRange } from '../utils/format'

function toQuery(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ).toString()
  return query ? `?${query}` : ''
}

/*
 * Locations -> (select a location) -> Location Summary: item-wise
 * inward/outward/net movement at that location, matching Tally's
 * Location Summary screen. Built from the same live stock-movement
 * data used by Stock Item Vouchers, scoped to this godown - Tally
 * does not expose per-godown opening/closing via a simple XML
 * collection, so the net figures below are the movement that
 * actually happened at this location within the selected period.
 */
function LocationSummary() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)

  const locationName = params.get('location') || ''
  const fy = financialYearRange(0)
  const fromDate = params.get('from') || fy.from
  const toDate = params.get('to') || fy.to

  const path = locationName
    ? `/reports/stock-movement${toQuery({ godown_name: locationName, from_date: fromDate, to_date: toDate })}`
    : null

  const { data: response, loading, error } = useFetch(path)

  const rows = useMemo(() => {
    const movement = Array.isArray(response?.report) ? response.report : []
    const buckets = new Map()

    for (const row of movement) {
      const item = row.stock_item || 'Unknown'

      if (!buckets.has(item)) {
        buckets.set(item, {
          stock_item: item,
          inward_qty: 0,
          inward_value: 0,
          outward_qty: 0,
          outward_value: 0,
        })
      }

      const bucket = buckets.get(item)
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

    return Array.from(buckets.values())
      .map((b) => ({
        ...b,
        net_qty: b.inward_qty - b.outward_qty,
        net_value: b.inward_value - b.outward_value,
      }))
      .sort((a, b) => a.stock_item.localeCompare(b.stock_item))
  }, [response])

  const columns = [
    { key: 'stock_item', label: 'Stock Item' },
    { key: 'inward_qty', label: 'Inward Qty', align: 'right', render: (r) => formatQuantity(r.inward_qty) },
    { key: 'inward_value', label: 'Inward Value', align: 'right', render: (r) => formatCurrency(r.inward_value) },
    { key: 'outward_qty', label: 'Outward Qty', align: 'right', render: (r) => formatQuantity(r.outward_qty) },
    { key: 'outward_value', label: 'Outward Value', align: 'right', render: (r) => formatCurrency(r.outward_value) },
    { key: 'net_qty', label: 'Net Qty', align: 'right', render: (r) => formatQuantity(r.net_qty) },
    { key: 'net_value', label: 'Net Value', align: 'right', render: (r) => formatCurrency(r.net_value) },
  ]

  return (
    <>
      <PageHeader
        title={`Location Summary${locationName ? `: ${locationName}` : ''}`}
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

        {locationName && !loading && !error && (
          <>
            <p className="table-hint">Click a stock item to view its Location Monthly Summary.</p>
            <DataTable
              columns={columns}
              rows={rows}
              onRowClick={(row) =>
                navigate(
                  `/reports/location-monthly${toQuery({
                    location: locationName,
                    item: row.stock_item,
                    from: fromDate,
                    to: toDate,
                  })}`
                )
              }
            />
            <div className="table-footer">
              <button
                type="button"
                className="btn"
                onClick={() =>
                  navigate(`/reports/location-monthly${toQuery({ location: locationName, from: fromDate, to: toDate })}`)
                }
              >
                View Location Monthly Summary (all items)
              </button>
            </div>
          </>
        )}
      </Card>
    </>
  )
}

export default LocationSummary
