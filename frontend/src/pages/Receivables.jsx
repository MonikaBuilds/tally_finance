import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import StatCard from '../components/common/StatCard'
import BillsOutstandingTable from '../components/common/BillsOutstandingTable'
import ExportButtons from '../components/common/ExportButtons'
import { ArrowDownLeft } from 'lucide-react'

/*
 * Receivables - laid out like Tally's "Bills Receivable" report.
 * Double-click a bill to see the vouchers behind it; double-click a
 * voucher to open it. All data comes from /reports/receivables.
 */
function Receivables() {
  const { data: response, loading, error } = useFetch('/reports/receivables')

  if (loading) return <Loader />
  if (error) return <ErrorMessage message={error} />
  if (!response.success) return <ErrorMessage message={response.error || response.message} />

  const { total_receivable, bills } = response.data

  return (
    <>
      <PageHeader
        title="Receivables"
        actions={<ExportButtons basePath="/reports/receivables/export" filenameBase="receivables" />}
      />

      <div className="stat-grid">
        <StatCard label="Total Receivable" value={total_receivable} tone="info" icon={ArrowDownLeft} />
      </div>

      <Card title="Bills Receivable">
        <BillsOutstandingTable bills={bills} />
      </Card>
    </>
  )
}

export default Receivables
