import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import StatCard from '../components/common/StatCard'
import DataTable from '../components/common/DataTable'
import ExportButtons from '../components/common/ExportButtons'
import { ArrowUpRight } from 'lucide-react'
import { formatCurrency } from '../utils/format'

const COLUMNS = [
  { key: 'party', label: 'Party' },
  { key: 'bill_reference', label: 'Bill Reference' },
  { key: 'bill_date', label: 'Bill Date' },
  { key: 'original_voucher_number', label: 'Voucher #' },
  {
    key: 'outstanding_amount',
    label: 'Outstanding',
    align: 'right',
    render: (row) => formatCurrency(row.outstanding_amount),
  },
]

function Payables() {
  const { data: response, loading, error } = useFetch('/reports/payables')

  if (loading) return <Loader />
  if (error) return <ErrorMessage message={error} />
  if (!response.success) return <ErrorMessage message={response.error || response.message} />

  const { total_payable, bills } = response.data

  return (
    <>
      <PageHeader
        title="Payables"
        actions={<ExportButtons basePath="/reports/payables/export" filenameBase="payables" />}
      />

      <div className="stat-grid">
        <StatCard label="Total Payable" value={total_payable} tone="warning" icon={ArrowUpRight} />
      </div>

      <Card title="Outstanding Bills">
        <DataTable columns={COLUMNS} rows={bills} />
      </Card>
    </>
  )
}

export default Payables