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
    Object.entries(params).filter(([, value]) => (
      value !== undefined && value !== null && value !== ''
    ))
  ).toString()

  return query ? `?${query}` : ''
}

const COLUMNS = [
  { key: 'date', label: 'Date', render: (r) => formatDate(r.date) },
  { key: 'stock_item', label: 'Stock Item' },
  { key: 'voucher_type', label: 'Vch Type' },
  { key: 'voucher_number', label: 'Vch No.' },
  { key: 'party', label: 'Party' },
  { key: 'quantity', label: 'Quantity', align: 'right', render: (r) => formatQuantity(r.quantity) },
  { key: 'rate', label: 'Rate', align: 'right', render: (r) => formatCurrency(r.rate) },
  { key: 'value', label: 'Value', align: 'right', render: (r) => formatCurrency(r.value) },
]

function LocationVouchers() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)

  const locationName = params.get('location') || ''
  const itemName = params.get('item') || ''
  const fromDate = params.get('from') || ''
  const toDate = params.get('to') || ''

  const queryParams = {
    godown_name: locationName || undefined,
    stock_item_name: itemName || undefined,
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
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} /> Back
          </button>
        }
      />

      <Card>
        {!locationName && <ErrorMessage message="No godown was specified." />}
        {locationName && loading && <Loader />}
        {locationName && error && <ErrorMessage message={error} />}

        {locationName && !loading && !error && response?.success && (
          <>
            <div className="card-toolbar">
              <ExportButtons
                basePath="/reports/stock-movement/export"
                params={queryParams}
                filenameBase="godown_vouchers"
              />
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
          </>
        )}
      </Card>
    </>
  )
}

export default LocationVouchers
