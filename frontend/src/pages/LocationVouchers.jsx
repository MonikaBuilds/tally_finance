import { useLocation, useNavigate } from 'react-router'
import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import ExportButtons from '../components/common/ExportButtons'
import { formatCurrency, formatDate, formatQuantity } from '../utils/format'
import { toQuery } from '../utils/stockFormat'

const COLUMNS = [
  { key: 'date', label: 'Date', render: (r) => formatDate(r.date) },
  { key: 'stock_item', label: 'Stock Item' },
  { key: 'voucher_type', label: 'Vch Type' },
  { key: 'voucher_number', label: 'Vch No.' },
  { key: 'party', label: 'Party' },
  { key: 'quantity', label: 'Quantity', align: 'right', render: (r) => formatQuantity(r.quantity) },
  { key: 'rate', label: 'Rate', align: 'right', render: (r) => formatCurrency(r.rate) },
  { key: 'value', label: 'Value', align: 'right', render: (r) => formatCurrency(r.value) },
  { key: 'direction', label: 'Movement' },
]

/*
 * Godown Vouchers: /reports/location-vouchers?location=&from=&to=
 *
 * All inventory movements into or out of one godown for a date range.
 * Data: /reports/stock-movement with ?godown_name=...
 */
function LocationVouchers() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)

  const locationName = params.get('location') || ''
  const fromDate = params.get('from') || ''
  const toDate = params.get('to') || ''

  const queryParams = {
    godown_name: locationName,
    from_date: fromDate || undefined,
    to_date: toDate || undefined,
  }

  const path = locationName
    ? `/reports/stock-movement${toQuery(queryParams)}`
    : null

  const { data: response, loading, error } = useFetch(path)

  return (
    <>
      <PageHeader
        title={`Godown Vouchers${locationName ? `: ${locationName}` : ''}`}
        subtitle={fromDate && toDate ? `${fromDate} to ${toDate}` : 'Live data from Tally'}
        backFallback="/reports/inventory"
        actions={
          <ExportButtons
            basePath="/reports/stock-movement/export"
            params={queryParams}
            filenameBase="godown_vouchers"
          />
        }
      />

      <Card>
        {!locationName && <ErrorMessage message="No godown was specified." />}
        {locationName && loading && <Loader />}
        {locationName && error && <ErrorMessage message={error} />}

        {locationName && !loading && !error && response?.success && (
          <DataTable
            columns={COLUMNS}
            rows={response.report || []}
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
        )}
      </Card>
    </>
  )
}

export default LocationVouchers
