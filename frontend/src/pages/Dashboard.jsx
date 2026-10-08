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
} from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
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
    return { label: 'Net loss', key: 'net_loss', value: data.net_loss, tone: 'negative', icon: TrendingDown }
  }

  if (isNumber(data.net_profit)) {
    return { label: 'Net profit', key: 'net_profit', value: data.net_profit, tone: 'positive', icon: TrendingUp }
  }

  return { label: 'Net profit / loss', key: 'net_profit', value: null, tone: 'neutral', icon: TrendingUp }
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
  const [filter, setFilter] = useState(getInitialDashboardFilter)

  // Set only by the Refresh button, and cleared when the period
  // changes: the backend then re-reads Tally instead of reusing
  // answers from the last minute.
  const [refreshedAt, setRefreshedAt] = useState(0)

  const period = `from_date=${filter.fromDate}&to_date=${filter.toDate}` +
    (refreshedAt ? `&refresh=${refreshedAt}` : '')

  // Headline figures come back in a few round trips; the monthly chart
  // needs one Tally request per month, so it loads on its own.
  const { data: response, loading, error } = useFetch(
    `/dashboard/summary?${period}`,
    { timeoutMs: SUMMARY_TIMEOUT_MS },
  )
  // Tally answers one request at a time, so the chart is only asked
  // for once the headline figures are in; otherwise its per-month
  // requests would queue ahead of them.
  const summaryReady = Boolean(response || error)
  const { data: monthly, loading: monthlyWaiting } = useFetch(
    summaryReady ? `/dashboard/monthly?${period}` : null,
    { timeoutMs: SUMMARY_TIMEOUT_MS },
  )
  const monthlyLoading = monthlyWaiting || (!summaryReady && !error)
  const { data: status, error: statusError } = useFetch('/tally/status', { timeoutMs: 10000 })

  // Keep the last figures on screen (dimmed) while a new period loads,
  // instead of blanking the whole page on every change.
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

  // The last known connection state shows at once on return visits,
  // instead of "Checking Tally…" every time.
  const [knownStatus] = useState(readTallyStatus)
  const freshStatus = status?.connected
    ? 'connected'
    : (status || statusError ? 'offline' : null)
  useEffect(() => {
    if (!freshStatus) return
    try {
      sessionStorage.setItem(STATUS_KEY, freshStatus)
    } catch {
      // Storage unavailable; the pill just starts at "Checking".
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

  // P&L cards hidden because Tally used other dates get a short hint;
  // the notice above them explains why.
  const PL_KEYS = ['total_sales', 'total_purchases', 'net_profit', 'net_loss']
  const sourceFor = (key) =>
    data.period_verified === false && PL_KEYS.includes(key)
      ? { ...sources[key], message: 'Hidden: Tally used different dates' }
      : sources[key]

  const kpi = (props) => (
    <KpiCard
      loading={loading}
      offline={offline}
      source={sourceFor(props.sourceKey)}
      {...props}
    />
  )

  // The previous period only feeds the comparison lines; failing to
  // read it is not worth a warning.
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
      />

      {usingBackendStaleCache && !offline && (
        <div className="db-alert" role="status">
          <AlertCircle size={16} aria-hidden="true" />
          <span>Tally is unavailable. Showing saved dashboard figures.</span>
          <button type="button" onClick={refresh}>
            <RefreshCw size={14} aria-hidden="true" /> Try again
          </button>
        </div>
      )}

      {offline && (
        <div className="db-alert db-alert--error" role="alert">
          <AlertCircle size={16} aria-hidden="true" />
          <span>
            <strong>{hasDashboardData ? 'Showing saved figures.' : 'Dashboard could not load.'}</strong> {error}
          </span>
          <button type="button" onClick={refresh}>
            <RefreshCw size={14} aria-hidden="true" /> Try again
          </button>
        </div>
      )}

      {!offline && !loading && (
        <PeriodNotice data={data} filter={filter} onFilterChange={changeFilter} />
      )}

      {!offline && failedReports.length > 0 && (
        <div className="db-alert" role="status">
          <AlertCircle size={16} aria-hidden="true" />
          <span>
            Tally did not return: {failedReports.join(', ')}. Figures that depend on
            {failedReports.length === 1 ? ' it' : ' them'} are shown as unavailable.
          </span>
          <button type="button" onClick={refresh} disabled={loading}>
            <RefreshCw size={14} aria-hidden="true" /> Retry
          </button>
        </div>
      )}

      <div className={`db-content${stale ? ' is-stale' : ''}`} aria-busy={loading}>
        <section aria-labelledby="db-pl-heading">
          <h2 id="db-pl-heading" className="db-section-title">
            Profit &amp; loss <span>{periodHint}</span>
          </h2>
          <div className="db-kpi-grid">
            {kpi({
              label: 'Sales', icon: ShoppingCart, tone: 'sales', sourceKey: 'total_sales',
              value: data.total_sales, display: formatAmount(data.total_sales),
              hint: 'Sales Accounts', to: '/reports/profit-loss',
              delta: delta('total_sales', true),
            })}
            {kpi({
              label: 'Purchases', icon: Receipt, tone: 'purchases', sourceKey: 'total_purchases',
              value: data.total_purchases, display: formatAmount(data.total_purchases),
              hint: 'Purchase Accounts', to: '/reports/profit-loss',
              delta: delta('total_purchases', null),
            })}
            {kpi({
              label: net.label, icon: net.icon, tone: net.tone, sourceKey: net.key,
              value: net.value, display: formatAmount(net.value),
              hint: 'As computed by Tally', to: '/reports/profit-loss',
              delta: previous && netChange(data, previous, previousLabel),
            })}
          </div>
        </section>

        <section aria-labelledby="db-position-heading">
          <h2 id="db-position-heading" className="db-section-title">
            Position <span>{asOnHint}</span>
          </h2>
          <div className="db-kpi-grid">
            {kpi({
              label: 'Receivables', icon: ArrowDownLeft, tone: 'neutral', sourceKey: 'receivables',
              value: data.receivables, display: formatAmount(data.receivables),
              hint: 'Pending bills receivable', to: '/reports/receivables',
            })}
            {kpi({
              label: 'Payables', icon: ArrowUpRight, tone: 'neutral', sourceKey: 'payables',
              value: data.payables, display: formatAmount(data.payables),
              hint: 'Pending bills payable', to: '/reports/payables',
            })}
            {kpi({
              label: 'Cash in hand', icon: Wallet, tone: 'neutral', sourceKey: 'cash_in_hand',
              value: data.cash_in_hand, display: formatBalance(data.cash_in_hand),
              hint: 'Cash-in-Hand group', to: '/reports/balance-sheet',
            })}
            {kpi({
              label: 'Bank balance', icon: Landmark, tone: 'neutral', sourceKey: 'bank_balance',
              value: data.bank_balance, display: formatBalance(data.bank_balance),
              hint: 'Bank Accounts group', to: '/reports/balance-sheet',
            })}
            {kpi({
              label: 'GST payable', icon: Percent, tone: 'neutral', sourceKey: 'gst_payable',
              value: data.gst_payable, display: formatAmount(data.gst_payable),
              hint: 'Output GST less input credit', to: '/reports/trial-balance',
            })}
            {kpi({
              label: 'TDS payable', icon: Percent, tone: 'neutral', sourceKey: 'tds_payable',
              value: data.tds_payable, display: formatAmount(data.tds_payable),
              hint: 'TDS ledger credit balances', to: '/reports/trial-balance',
            })}
          </div>
        </section>

        <div className="db-grid db-grid--wide">
          <Panel
            title="Sales vs purchases"
            subtitle={
              unverifiedMonths
                ? `${unverifiedMonths} of ${series.length} months not shown: Tally used different dates`
                : "By month, from Tally's Profit & Loss"
            }
            to="/reports/profit-loss"
            loading={monthlyLoading}
            empty={
              hasSeries ? null
                : monthlyLoading ? 'loading'
                  : offline ? 'Tally could not be reached.'
                    : unverifiedMonths === series.length && series.length
                      ? 'Tally used different dates for every month of this period, so nothing is plotted.'
                      : 'No sales or purchases in Tally for this period.'
            }
          >
            <IncomeExpenseChart points={series} />
          </Panel>

          <Panel
            title="Cash & bank"
            subtitle={asOnHint}
            to="/reports/balance-sheet"
            loading={loading}
            empty={emptyText(
              Array.isArray(accounts) && accounts.length > 0,
              Array.isArray(accounts) ? 'No cash or bank ledgers in Tally.' : sources.cash_in_hand?.message,
            )}
          >
            <CashBankList accounts={accounts || []} />
          </Panel>
        </div>

        <div className="db-grid">
          <Panel
            title="Receivables"
            subtitle="Ageing and largest pending bills from customers"
            to="/reports/receivables"
            linkLabel="View all"
            loading={loading}
            empty={receivablesEmpty}
          >
            <AgeingBar buckets={data.receivables_ageing} label="Receivables" />
            <OutstandingTable bills={data.top_receivables || []} partyLabel="Customer" />
          </Panel>

          <Panel
            title="Payables"
            subtitle="Ageing and largest pending bills to suppliers"
            to="/reports/payables"
            linkLabel="View all"
            loading={loading}
            empty={payablesEmpty}
          >
            <AgeingBar buckets={data.payables_ageing} label="Payables" />
            <OutstandingTable bills={data.top_payables || []} partyLabel="Supplier" />
          </Panel>
        </div>

        <div className="db-grid">
          <Panel
            title="Income"
            subtitle={periodHint}
            to="/reports/profit-loss"
            loading={loading}
            empty={emptyText(Boolean(data.sales_breakdown?.length), 'No income lines in Tally for this period.')}
          >
            <BreakdownList items={data.sales_breakdown} tone="sales" totalLabel="Sales and other income" />
          </Panel>

          <Panel
            title="Expenses"
            subtitle={periodHint}
            to="/reports/profit-loss"
            loading={loading}
            empty={emptyText(Boolean(data.expense_breakdown?.length), 'No direct or indirect expenses in Tally for this period.')}
          >
            <BreakdownList items={data.expense_breakdown} tone="purchases" totalLabel="Direct and indirect expenses" />
          </Panel>
        </div>
      </div>
    </div>
  )
}

export default Dashboard
