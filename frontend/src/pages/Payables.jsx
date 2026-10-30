import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import StatCard from '../components/common/StatCard'
import BillsOutstandingTable from '../components/common/BillsOutstandingTable'
import ExportButtons from '../components/common/ExportButtons'
import { ArrowUpRight } from 'lucide-react'

/*
 * Payables - laid out like Tally's "Bills Payable" report.
 * Double-click a bill to see the vouchers behind it; double-click a
 * voucher to open it. All data comes from /reports/payables.
 */
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

      <Card title="Bills Payable">
        <BillsOutstandingTable bills={bills} />
      </Card>
    </>
  )
}

export default Payables
