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

function ClosingStockSummary() {
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
        subtitle="Closing stock details fetched from Tally"
        actions={
          <ExportButtons
            basePath="/reports/stock-summary/export"
            filenameBase="closing_stock_summary"
          />
        }
      />

      <Card title="Stock Group Summary">
        <DataTable
          columns={columns}
          rows={rows}
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