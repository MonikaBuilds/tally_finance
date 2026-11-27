import { useSearchParams } from 'react-router'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import StatCard from '../components/common/StatCard'
import BillsOutstandingTable from '../components/common/BillsOutstandingTable'
import ExportButtons from '../components/common/ExportButtons'
import AsOnDateFilter from '../components/common/AsOnDateFilter'
import { ArrowDownLeft } from 'lucide-react'
import { formatDate } from '../utils/format'

/*
 * Receivables - laid out like Tally's "Bills Receivable" report.
 * Double-click a bill to see the vouchers behind it; double-click a
 * voucher to open it. All data comes from /reports/receivables.
 *
 * Tally's Bills Receivable is an "as on" report, so the page filters by a
 * single date rather than a period. That date is passed to Tally as
 * SVTODATE, which decides which bills are still open, their outstanding
 * amounts, and the overdue days shown against each one. With no date in
 * the URL, Tally uses its own active period and the report says so.
 */
function Receivables() {
  const [searchParams, setSearchParams] = useSearchParams()

  const asOn = searchParams.get('as_on') || ''
  const path = asOn
    ? `/reports/receivables?as_on=${encodeURIComponent(asOn)}`
    : '/reports/receivables'

  const { data: response, loading, error } = useFetch(path)

  function applyDate(value) {
    setSearchParams({ as_on: value }, { replace: true })
  }

  function resetDate() {
    setSearchParams({}, { replace: true })
  }

  const dateFilter = (
    <AsOnDateFilter
      asOn={asOn}
      onApply={applyDate}
      onReset={resetDate}
      idPrefix="receivables-on"
      showFyPresets
    />
  )

  const header = (
    <PageHeader
      title="Receivables"
      subtitle={asOn ? `As on ${formatDate(asOn)}` : undefined}
      actions={
        <ExportButtons
          basePath="/reports/receivables/export"
          filenameBase="receivables"
          params={asOn ? { as_on: asOn } : {}}
        />
      }
    />
  )

  if (loading) return <>{header}{dateFilter}<Loader /></>
  if (error) return <>{header}{dateFilter}<ErrorMessage message={error} /></>
  if (!response.success) return <>{header}{dateFilter}<ErrorMessage message={response.error || response.message} /></>

  const { total_receivable, bills } = response.data || {}

  return (
    <>
      {header}
      {dateFilter}

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
