import { useEffect, useState } from 'react'
import {
  AlertCircle,
  ArrowDownLeft,
  ArrowUpRight,
  Landmark,
  Percent,
  Receipt,
  RefreshCw,
  ShoppingCart,
  TrendingDown,
  TrendingUp,
  Wallet,
  Scale,
  LineChart,
  Layers,
  PieChart,
} from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import { useCompanyFinancialYear } from './trialBalance/useCompanyFinancialYear'
import {
  getInitialDashboardFilter,
  getPresetDateRange,
  saveDashboardFilter,
} from '../utils/dashboardDateFilter'
import DashboardToolbar from '../components/dashboard/DashboardToolbar'
import KpiCard from '../components/dashboard/KpiCard'
import Panel from '../components/dashboard/Panel'
import IncomeExpenseChart from '../components/dashboard/IncomeExpenseChart'
import BreakdownList from '../components/dashboard/BreakdownList'
import OutstandingTable from '../components/dashboard/OutstandingTable'
import CashBankList from '../components/dashboard/CashBankList'
import AgeingBar from '../components/dashboard/AgeingBar'
import PeriodNotice from '../components/dashboard/PeriodNotice'
import ExportButtons from '../components/common/ExportButtons'
import { formatAmount, formatBalance, formatDay, isNumber } from '../components/dashboard/format'
import '../components/dashboard/dashboard.css'

// A full financial year means one Tally P&L request per month, and
// Tally answers one request at a time.
const SUMMARY_TIMEOUT_MS = 60000

const REPORT_NAMES = {
  profit_loss: 'Profit & Loss',
  profit_loss_totals: 'Profit & Loss totals',
  groups: 'Cash and bank groups',
  ledgers: 'Ledger balances',
  receivables: 'Bills receivable',
  payables: 'Bills payable',
}

// Net profit and net loss come from Tally as two figures; exactly one
// of them is non-zero, so they share a single card.
function netResult(data) {
  if (isNumber(data.net_loss) && data.net_loss > 0) {
    return { label: 'Net Loss', key: 'net_loss', value: data.net_loss, tone: 'negative', icon: TrendingDown }
  }

  if (isNumber(data.net_profit)) {
    return { label: 'Net Profit', key: 'net_profit', value: data.net_profit, tone: 'positive', icon: TrendingUp }
  }

  return { label: 'Net Profit / Loss', key: 'net_profit', value: null, tone: 'neutral', icon: TrendingUp }
}

// "FY 2024-25" for a whole Indian financial year, otherwise the dates.
function periodLabel(from, to) {
  const fy = /^(\d{4})-04-01$/.exec(from || '')
  if (fy && to === `${Number(fy[1]) + 1}-03-31`) {
    return `FY ${fy[1]}-${String(Number(fy[1]) + 1).slice(-2)}`
  }
  return `${formatDay(from)} – ${formatDay(to)}`
}

// "▲ 12% vs FY 2024-25". goodWhenUp picks the colour: true for sales,
// null where a rise is neither good nor bad (purchases).
function percentChange(current, previous, label, goodWhenUp) {
  if (!isNumber(current) || !isNumber(previous)) return null
  if (previous === 0) {
    return { text: current === 0 ? `No change vs ${label}` : `Nil in ${label}`, tone: 'flat' }
  }

  const change = ((current - previous) / Math.abs(previous)) * 100
  const size = Math.abs(change)
  const text = `${change > 0 ? '▲' : change < 0 ? '▼' : ''} ${size < 10 ? size.toFixed(1) : Math.round(size)}% vs ${label}`.trim()

  if (goodWhenUp === null || change === 0) return { text, tone: 'flat' }
  return { text, tone: (change > 0) === goodWhenUp ? 'up' : 'down' }
}

function netAmount(figures) {
  if (!isNumber(figures.net_profit) && !isNumber(figures.net_loss)) return null
  return (figures.net_profit || 0) - (figures.net_loss || 0)
}

function netChange(data, previous, label) {
  const current = netAmount(data)
  const before = netAmount(previous)
  if (current === null || before === null) return null

  return {
    text: `${before < 0 ? 'Loss' : 'Profit'} of ${formatAmount(Math.abs(before))} in ${label}`,
    tone: current > before ? 'up' : current < before ? 'down' : 'flat',
  }
}

const STATUS_KEY = 'tfi.dashboard.tally_status'

function readTallyStatus() {
  try {
    return sessionStorage.getItem(STATUS_KEY)
  } catch {
    return null
  }
}

function outstandingEmpty(data, key, { loading, offline, noun }) {
  const bills = data[`top_${key}`]

  if (loading && bills === undefined) return 'loading'
  if (Array.isArray(bills)) return bills.length ? null : `No pending ${noun} in Tally.`
  if (offline) return 'Tally could not be reached.'

  const context = data.report_contexts?.[key]
  if (context?.to_date && !context.matches_selected_as_of) {
    return `Tally returned ${noun} as on ${formatDay(context.to_date)}, not the selected date.`
  }

  return data.metric_sources?.[key]?.message || `Tally did not return ${noun}.`
}

function Dashboard() {
  const financialYear = useCompanyFinancialYear()
  const [filter, setFilter] = useState(getInitialDashboardFilter)

  // Align initial dashboard date range with company's active financial year in Tally.
  useEffect(() => {
    if (financialYear.ready && financialYear.from && financialYear.to) {
      const saved = sessionStorage.getItem('tfi.dashboard.date_filter')
      if (!saved) {
        const companyFilter = {
          fromDate: financialYear.from,
          toDate: financialYear.to,
          selectedPreset: 'fy',
        }
        // eslint-disable-next-line react-hooks/set-state-in-effect
        setFilter(companyFilter)
        saveDashboardFilter(companyFilter)
      }
    }
  }, [financialYear.ready, financialYear.from, financialYear.to])

  const [refreshedAt, setRefreshedAt] = useState(0)

  const period = `from_date=${filter.fromDate}&to_date=${filter.toDate}` +
    (refreshedAt ? `&refresh=${refreshedAt}` : '')

  const { data: response, loading, error } = useFetch(
    `/dashboard/summary?${period}`,
    { timeoutMs: SUMMARY_TIMEOUT_MS },
  )

  const summaryReady = Boolean(response || error)
  const { data: monthly, loading: monthlyWaiting } = useFetch(
    summaryReady ? `/dashboard/monthly?${period}` : null,
    { timeoutMs: SUMMARY_TIMEOUT_MS },
  )
  const monthlyLoading = monthlyWaiting || (!summaryReady && !error)
  const { data: status, error: statusError } = useFetch('/tally/status', { timeoutMs: 10000 })

  const [lastData, setLastData] = useState(null)
  if (response?.data && response.data !== lastData) {
    setLastData(response.data)
  }

  const offline = Boolean(error)
  const data = response?.data || lastData || {}
  const hasDashboardData = Boolean(response?.data || lastData)
  const usingBackendStaleCache = Boolean(
    response?.is_stale || response?.source === 'stale_cache'
  )
  const stale = Boolean(
    usingBackendStaleCache ||
    (offline && hasDashboardData) ||
    (loading && lastData)
  )
  const sources = data.metric_sources || {}

  const [knownStatus] = useState(readTallyStatus)
  const freshStatus = status?.connected
    ? 'connected'
    : (status || statusError ? 'offline' : null)
  useEffect(() => {
    if (!freshStatus) return
    try {
      sessionStorage.setItem(STATUS_KEY, freshStatus)
    } catch {
      // Storage unavailable
    }
  }, [freshStatus])
  const tallyStatus = freshStatus || knownStatus || 'checking'

  function changeFilter(next) {
    const nextFilter = typeof next === 'string' ? getPresetDateRange(next) : next
    setFilter(nextFilter)
    saveDashboardFilter(nextFilter)
    setRefreshedAt(0)
  }

  const refresh = () => setRefreshedAt(Date.now())

  const periodHint = `${formatDay(filter.fromDate)} – ${formatDay(filter.toDate)}`
  const asOnHint = `As on ${formatDay(filter.toDate)}`
  const net = netResult(data)
  const plPeriodHint = periodHint

  const kpi = (props) => (
    <KpiCard
      loading={loading}
      offline={offline}
      source={sources[props.sourceKey]}
      {...props}
    />
  )

  const failedReports = Object.keys(data.report_errors || {})
    .filter((key) => !key.startsWith('previous_'))
    .map((key) => REPORT_NAMES[key] || key)

  const previous = data.comparison?.period_verified ? data.comparison : null
  const previousLabel = previous && periodLabel(previous.from_date, previous.to_date)
  const delta = (key, goodWhenUp) =>
    previous && percentChange(data[key], previous[key], previousLabel, goodWhenUp)

  const receivablesEmpty = outstandingEmpty(data, 'receivables', { loading, offline, noun: 'receivables' })
  const payablesEmpty = outstandingEmpty(data, 'payables', { loading, offline, noun: 'payables' })

  const accounts = data.cash_bank_accounts
  const series = monthly?.data?.income_vs_expense || []
  const hasSeries = series.some((point) => isNumber(point.income) || isNumber(point.expense))
  const unverifiedMonths = series.filter((point) => point.status === 'unverified').length

  const emptyText = (hasData, message) => {
    if (hasData) return null
    if (loading) return 'loading'
    return offline ? 'Tally could not be reached.' : message
  }

  return (
    <div className="db">
      <div className={`db-progress${loading ? ' is-active' : ''}`} aria-hidden="true" />

      <DashboardToolbar
        companyName={data.company_name}
        tallyStatus={tallyStatus}
        filter={filter}
        onFilterChange={changeFilter}
        onRefresh={refresh}
        loading={loading}
        fetchedAt={data.fetched_at}
        exportButtons={
          <ExportButtons
            basePath="/dashboard/export"
            filenameBase="dashboard"
            params={{ from_date: filter.fromDate, to_date: filter.toDate }}
            disabled={loading}
          />
        }
      />

      {usingBackendStaleCache && !offline && (
        <div className="db-alert db-alert--cache" role="status">
          <AlertCircle size={16} aria-hidden="true" />
          <div className="db-alert-content">
            <p className="db-alert-title">Serving Cached Financial Figures</p>
            <p className="db-alert-desc">Tally Prime is currently unreachable. Displaying cached records.</p>
          </div>
          <button type="button" className="db-alert-btn" onClick={refresh}>
            <RefreshCw size={13} aria-hidden="true" /> Reconnect
          </button>
        </div>
      )}

      {offline && (
        <div className="db-alert db-alert--error" role="alert">
          <AlertCircle size={16} aria-hidden="true" />
          <div className="db-alert-content">
            <p className="db-alert-title">
              {hasDashboardData ? 'Displaying Offline Cached Records' : 'Unable to Connect to Tally Prime Gateway'}
            </p>
            <p className="db-alert-desc">{error}</p>
          </div>
          <button type="button" className="db-alert-btn" onClick={refresh}>
            <RefreshCw size={13} aria-hidden="true" /> Retry Connection
          </button>
        </div>
      )}

      {!offline && !loading && (
        <PeriodNotice data={data} filter={filter} onFilterChange={changeFilter} />
      )}

      {!offline && failedReports.length > 0 && (
        <div className="db-alert db-alert--warning" role="status">
          <AlertCircle size={16} aria-hidden="true" />
          <div className="db-alert-content">
            <p className="db-alert-title">Partial Tally Report Response</p>
            <p className="db-alert-desc">
              Tally Prime did not return data for: {failedReports.join(', ')}. Dependent financial metrics are marked unavailable.
            </p>
          </div>
          <button type="button" className="db-alert-btn" onClick={refresh} disabled={loading}>
            <RefreshCw size={13} aria-hidden="true" /> Retry
          </button>
        </div>
      )}

      <div className={`db-content${stale ? ' is-stale' : ''}`} aria-busy={loading}>
        {/* Operating Performance (P&L) Section */}
        <section className="db-section" aria-labelledby="db-pl-heading">
          <div className="db-section-header">
            <div className="db-section-title-wrap">
              <span className="db-section-tag db-section-tag--pl">Operating Performance</span>
              <h2 id="db-pl-heading" className="db-section-title">
                Statement of Profit &amp; Loss
              </h2>
            </div>
            <div className="db-section-meta">
              <span className="db-section-period">{plPeriodHint}</span>
              <span className="db-section-subtext">Accrual Accounting · Primary Books</span>
            </div>
          </div>

          <div className="db-kpi-grid">
            {kpi({
              label: 'Gross Sales / Turnover',
              icon: ShoppingCart,
              tone: 'sales',
              tag: 'OPERATING REVENUE',
              sourceKey: 'total_sales',
              value: data.total_sales,
              display: formatAmount(data.total_sales),
              hint: 'Sales Accounts Ledger Group',
              to: '/reports/profit-loss',
              delta: delta('total_sales', true),
            })}
            {kpi({
              label: 'Direct Purchases',
              icon: Receipt,
              tone: 'purchases',
              tag: 'COST OF GOODS (COGS)',
              sourceKey: 'total_purchases',
              value: data.total_purchases,
              display: formatAmount(data.total_purchases),
              hint: 'Purchase Accounts Ledger Group',
              to: '/reports/profit-loss',
              delta: delta('total_purchases', null),
            })}
            {kpi({
              label: net.label,
              icon: net.icon,
              tone: net.tone,
              tag: net.tone === 'negative' ? 'NET DEFICIT' : 'NET SURPLUS',
              sourceKey: net.key,
              value: net.value,
              display: formatAmount(net.value),
              hint: 'Net P&L as computed by Tally Prime',
              to: '/reports/profit-loss',
              delta: previous && netChange(data, previous, previousLabel),
            })}
          </div>
        </section>

        {/* Financial Position & Working Capital Section */}
        <section className="db-section" aria-labelledby="db-position-heading">
          <div className="db-section-header">
            <div className="db-section-title-wrap">
              <span className="db-section-tag db-section-tag--position">Balance Sheet &amp; Liquidity</span>
              <h2 id="db-position-heading" className="db-section-title">
                Financial Position &amp; Working Capital
              </h2>
            </div>
            <div className="db-section-meta">
              <span className="db-section-period">{asOnHint}</span>
              <span className="db-section-subtext">Closing Ledger Balances · Realizable Values</span>
            </div>
          </div>

          <div className="db-kpi-grid db-kpi-grid--six">
            {kpi({
              label: 'Trade Receivables',
              icon: ArrowDownLeft,
              tone: 'neutral',
              tag: 'CURRENT ASSET',
              sourceKey: 'receivables',
              value: data.receivables,
              display: formatAmount(data.receivables),
              hint: data.report_contexts?.receivables?.to_date && !data.report_contexts?.receivables?.matches_selected_as_of
                ? `As on ${formatDay(data.report_contexts.receivables.to_date)}`
                : 'Pending customer bills receivable',
              to: '/reports/receivables',
            })}
            {kpi({
              label: 'Trade Payables',
              icon: ArrowUpRight,
              tone: 'neutral',
              tag: 'CURRENT LIABILITY',
              sourceKey: 'payables',
              value: data.payables,
              display: formatAmount(data.payables),
              hint: data.report_contexts?.payables?.to_date && !data.report_contexts?.payables?.matches_selected_as_of
                ? `As on ${formatDay(data.report_contexts.payables.to_date)}`
                : 'Pending vendor bills payable',
              to: '/reports/payables',
            })}
            {kpi({
              label: 'Cash in Hand',
              icon: Wallet,
              tone: 'cash',
              tag: 'LIQUID ASSET (DR)',
              sourceKey: 'cash_in_hand',
              value: data.cash_in_hand,
              display: formatBalance(data.cash_in_hand),
              hint: 'Cash-in-Hand physical ledger balances',
              to: '/reports/balance-sheet',
            })}
            {kpi({
              label: 'Bank Accounts',
              icon: Landmark,
              tone: 'bank',
              tag: 'LIQUID ASSET (DR)',
              sourceKey: 'bank_balance',
              value: data.bank_balance,
              display: formatBalance(data.bank_balance),
              hint: 'Total commercial bank closing balances',
              to: '/reports/balance-sheet',
            })}
            {kpi({
              label: 'Net GST Liability',
              icon: Percent,
              tone: 'tax',
              tag: 'INDIRECT STATUTORY',
              sourceKey: 'gst_payable',
              value: data.gst_payable,
              display: formatAmount(data.gst_payable),
              hint: 'Output GST minus input tax credit',
              to: '/reports/trial-balance',
            })}
            {kpi({
              label: 'TDS Payable',
              icon: Percent,
              tone: 'tax',
              tag: 'DIRECT WITHHOLDING',
              sourceKey: 'tds_payable',
              value: data.tds_payable,
              display: formatAmount(data.tds_payable),
              hint: 'Statutory TDS credit ledger balances',
              to: '/reports/trial-balance',
            })}
          </div>
        </section>

        {/* Monthly Trend & Treasury Cash/Bank Grid */}
        <div className="db-grid db-grid--wide">
          <Panel
            title="Monthly Operating Trend: Sales vs Purchases"
            badge="P&L Cash Flow"
            icon={LineChart}
            subtitle={
              monthly?.data?.from_date && filter.fromDate !== monthly.data.from_date
                ? `Monthly trajectory — ${formatDay(monthly.data.from_date)} – ${formatDay(monthly.data.to_date)} (Tally Books)`
                : unverifiedMonths
                  ? `${unverifiedMonths} of ${series.length} months not plotted: Tally used differing fiscal bounds`
                  : "Month-by-month financial volume from Tally's Profit & Loss statement"
            }
            to="/reports/profit-loss"
            linkLabel="Open Statement"
            loading={monthlyLoading}
            empty={
              hasSeries ? null
                : monthlyLoading ? 'loading'
                  : offline ? 'Tally Prime could not be reached.'
                    : unverifiedMonths === series.length && series.length
                      ? 'Tally used differing dates for every month of this period; no points could be plotted.'
                      : 'No recorded sales or purchases in Tally Prime for this period.'
            }
          >
            <IncomeExpenseChart points={series} />
          </Panel>

          <Panel
            title="Treasury Liquidity & Bank Holdings"
            badge="Assets"
            icon={Landmark}
            subtitle={asOnHint}
            to="/reports/balance-sheet"
            linkLabel="Balance Sheet"
            loading={loading}
            empty={emptyText(
              Array.isArray(accounts) && accounts.length > 0,
              Array.isArray(accounts) ? 'No cash or bank ledgers found in Tally Prime.' : sources.cash_in_hand?.message,
            )}
          >
            <CashBankList accounts={accounts || []} />
          </Panel>
        </div>

        {/* Working Capital Ageing Grid */}
        <div className="db-grid">
          <Panel
            title="Trade Debtors (Receivables)"
            badge="Asset Ageing"
            icon={Layers}
            subtitle={
              data.report_contexts?.receivables?.to_date && !data.report_contexts?.receivables?.matches_selected_as_of
                ? `As on ${formatDay(data.report_contexts.receivables.to_date)} (Tally Books)`
                : 'Customer ageing risk spectrum & largest unsettled invoices'
            }
            to="/reports/receivables"
            linkLabel="All Receivables"
            loading={loading}
            empty={receivablesEmpty}
          >
            <AgeingBar buckets={data.receivables_ageing} label="Receivables" />
            <OutstandingTable bills={data.top_receivables || []} partyLabel="Customer" />
          </Panel>

          <Panel
            title="Trade Creditors (Payables)"
            badge="Liability Ageing"
            icon={Layers}
            subtitle={
              data.report_contexts?.payables?.to_date && !data.report_contexts?.payables?.matches_selected_as_of
                ? `As on ${formatDay(data.report_contexts.payables.to_date)} (Tally Books)`
                : 'Supplier ageing obligations & largest due payables'
            }
            to="/reports/payables"
            linkLabel="All Payables"
            loading={loading}
            empty={payablesEmpty}
          >
            <AgeingBar buckets={data.payables_ageing} label="Payables" />
            <OutstandingTable bills={data.top_payables || []} partyLabel="Supplier" />
          </Panel>
        </div>

        {/* Schedule Breakdown Grid */}
        <div className="db-grid">
          <Panel
            title="Operating Revenue Schedule"
            badge="Income Schedule"
            icon={PieChart}
            subtitle={periodHint}
            to="/reports/profit-loss"
            linkLabel="View P&L"
            loading={loading}
            empty={emptyText(Boolean(data.sales_breakdown?.length), 'No operating income lines in Tally Prime for this period.')}
          >
            <BreakdownList items={data.sales_breakdown} tone="sales" totalLabel="Total Operating Turnover" />
          </Panel>

          <Panel
            title="Expenditure & Cost Schedule"
            badge="Expense Schedule"
            icon={PieChart}
            subtitle={periodHint}
            to="/reports/profit-loss"
            linkLabel="View P&L"
            loading={loading}
            empty={emptyText(Boolean(data.expense_breakdown?.length), 'No direct or indirect expenses in Tally Prime for this period.')}
          >
            <BreakdownList items={data.expense_breakdown} tone="purchases" totalLabel="Total Direct & Indirect Costs" />
          </Panel>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
