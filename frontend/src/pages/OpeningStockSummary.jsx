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

function OpeningStockSummary() {
  const {
    data: response,
    loading,
    error,
  } = useFetch('/reports/stock-summary')

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
      key: 'opening_quantity',
      label: 'Opening Qty',
      render: (row) =>
        formatQuantity(row.opening_quantity),
    },
    {
      key: 'opening_value',
      label: 'Opening Value',
      render: (row) =>
        formatCurrency(row.opening_value),
    },
  ]

  const totalOpeningValue = rows.reduce(
    (sum, row) =>
      sum + (Number(row.opening_value) || 0),
    0
  )

  return (
    <>
      <PageHeader
        title="Opening Stock Summary"
        subtitle="Opening stock details fetched from Tally"
        actions={
          <ExportButtons
            basePath="/reports/stock-summary/export"
            filenameBase="opening_stock_summary"
          />
        }
      />

      <Card title="Opening Stock Summary">
        <DataTable
          columns={columns}
          rows={rows}
        />

        <div className="table-footer">
          <span>Total Opening Value</span>
          <span>
            {formatCurrency(totalOpeningValue)}
          </span>
        </div>
      </Card>
    </>
  )
}

export default OpeningStockSummary