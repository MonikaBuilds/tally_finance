import { Link } from 'react-router'
import {
  ArrowDownLeft,
  ArrowUpRight,
  ChevronRight,
  FileClock,
  TrendingDown,
  TrendingUp,
  Wallet,
} from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import StatCard from '../components/common/StatCard'
import { REPORT_ICONS } from '../components/layout/navConfig'
import { ALL_REPORTS } from '../reportsConfig'

function Dashboard() {
  const { data: response, loading, error } = useFetch('/dashboard/summary')

  if (loading) return <Loader />
  if (error) return <ErrorMessage message={error} />
  if (!response.success) return <ErrorMessage message={response.error || response.message} />

  const summary = response.data
  const netProfitTone = Number(summary.net_profit) < 0 ? 'negative' : 'positive'

  return (
    <>
      <PageHeader title="Dashboard" subtitle="Live overview from Tally" />

      <div className="stat-grid">
        <StatCard label="Revenue" value={summary.revenue} tone="positive" icon={TrendingUp} />
        <StatCard label="Expenses" value={summary.expenses} tone="negative" icon={TrendingDown} />
        <StatCard label="Net Profit" value={summary.net_profit} tone={netProfitTone} icon={Wallet} />
        <StatCard label="Receivables" value={summary.receivables} tone="info" icon={ArrowDownLeft} />
        <StatCard label="Payables" value={summary.payables} tone="warning" icon={ArrowUpRight} />
        <StatCard
          label="Pending Invoices"
          value={summary.pending_invoices}
          format="number"
          icon={FileClock}
        />
      </div>

      <h2 className="section-title">Reports</h2>

      <div className="reports-grid">
        {ALL_REPORTS.map((report) => {
          const Icon = REPORT_ICONS[report.to]

          return (
            <Link key={report.to} to={report.to} className="report-card">
              {Icon && (
                <span className="report-card-icon">
                  <Icon size={18} />
                </span>
              )}
              <span className="report-card-body">
                <span className="report-card-title">{report.label}</span>
                <span className="report-card-desc">{report.description}</span>
              </span>
              <ChevronRight size={16} className="report-card-arrow" />
            </Link>
          )
        })}
      </div>
    </>
  )
}

export default Dashboard
