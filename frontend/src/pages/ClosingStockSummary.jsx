import { useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'
import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import ExportButtons from '../components/common/ExportButtons'
import {
  formatCurrency,
  formatQuantity,
} from '../utils/format'

function toQuery(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(
      ([, value]) => value !== undefined && value !== null && value !== ''
    )
  ).toString()

  return query ? `?${query}` : ''
}

/*
 * Stock Group Summary (closing stock). Reached from the Balance Sheet:
 * Current Assets -> Closing Stock. The Balance Sheet's From/To dates
 * arrive in the URL (?from_date=...&to_date=...); the closing stock is
 * fetched as at the To Date. Clicking an item opens its Stock Item
 * Monthly Summary for the same period. With no dates in the URL it
 * behaves as it did before.
 */
function ClosingStockSummary() {
  const location = useLocation()
  const navigate = useNavigate()
  const urlParams = new URLSearchParams(location.search)

  const fromDate = urlParams.get('from_date') || ''
  const toDate = urlParams.get('to_date') || ''

  const {
    data: response,
    loading,
    error,
  } = useFetch(`/reports/stock-summary${toQuery({ to_date: toDate })}`)

  if (loading) return <Loader />

  if (error) {
    return <ErrorMessage message={error} />
  }

  if (!response?.success) {
    return (
      <ErrorMessage
        message={response?.error || response?.message}
      />
    )
  }

  const rows = response.report || []

  const columns = [
    {
      key: 'stock_item',
      label: 'Stock Item',
      render: (row) =>
        row.stock_item || row.name || '-',
    },
    {
      key: 'stock_group',
      label: 'Stock Group',
      render: (row) =>
        row.stock_group || row.parent || '-',
    },
    {
      key: 'unit',
      label: 'Unit',
      render: (row) =>
        row.unit || row.base_units || '-',
    },
    {
      key: 'closing_quantity',
      label: 'Closing Qty',
      render: (row) =>
        formatQuantity(row.closing_quantity),
    },
    {
      key: 'closing_rate',
      label: 'Closing Rate',
      render: (row) =>
        formatCurrency(
          row.closing_rate ?? row.rate
        ),
    },
    {
      key: 'closing_value',
      label: 'Closing Value',
      render: (row) =>
        formatCurrency(row.closing_value),
    },
  ]

  const totalClosingValue = rows.reduce(
    (sum, row) =>
      sum + (Number(row.closing_value) || 0),
    0
  )

  return (
    <>
      <PageHeader
        title="Stock Group Summary"
        subtitle={
          fromDate && toDate
            ? `Closing stock details fetched from Tally - ${fromDate} to ${toDate}`
            : 'Closing stock details fetched from Tally'
        }
        actions={
          <>
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => navigate(-1)}
            >
              <ArrowLeft size={16} /> Back
            </button>
            <ExportButtons
              basePath="/reports/stock-summary/export"
              params={{ to_date: toDate }}
              filenameBase="closing_stock_summary"
            />
          </>
        }
      />

      <Card title="Stock Group Summary">
        <p className="table-hint">Click a stock item to view its Stock Monthly Summary.</p>

        <DataTable
          columns={columns}
          rows={rows}
          onRowClick={(row) =>
            navigate(
              `/reports/stock-item-monthly${toQuery({
                item: row.stock_item || row.name,
                from: fromDate,
                to: toDate,
              })}`
            )
          }
        />

        <div className="table-footer">
          <span>Total Closing Value</span>
          <span>
            {formatCurrency(totalClosingValue)}
          </span>
        </div>
      </Card>
    </>
  )
}

export default ClosingStockSummary