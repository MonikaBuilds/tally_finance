import { useState, useEffect } from 'react'
import { Link, useNavigate, useOutletContext } from 'react-router'
import {
  AlertCircle,
  ArrowUpRight,
  BarChart3,
  Calendar,
  ChevronDown,
  Landmark,
  LogOut,
  Percent,
  PieChart,
  Receipt,
  RefreshCw,
  TrendingDown,
  TrendingUp,
  UserCheck,
  Wallet,
} from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import { clearAccessToken } from '../api/client'
import {
  getInitialDashboardFilter,
  saveDashboardFilter,
  clearDashboardFilter,
  getPresetDateRange,
  validateDateRange,
} from '../utils/dashboardDateFilter'

// Format currency displaying exact Tally values with Indian numbering
function formatCurrency(val, isOffline = false, isLoading = false) {
  if (isLoading && (val === null || val === undefined)) return '—'
  if (isOffline && (val === null || val === undefined)) return '—'
  if (val === null || val === undefined) return 'Unavailable'

  const num = Math.round(Number(val))

  return num < 0
    ? `-₹ ${Math.abs(num).toLocaleString('en-IN')}`
    : `₹ ${num.toLocaleString('en-IN')}`
}

// Color palettes for refined segmented donut charts
const EXPENSE_PALETTE = ['#ef4444', '#f59e0b', '#8b5cf6', '#06b6d4', '#ec4899', '#64748b']
const SALES_PALETTE = ['#10b981', '#3b82f6', '#8b5cf6', '#06b6d4', '#f59e0b', '#ec4899']

function RefinedDonutChart({ items, centerTotal, centerLabel, palette = EXPENSE_PALETTE, isOffline, loading }) {
  if (!items || items.length === 0) {
    return (
      <div className="unconnected-chart-banner">
        <span>{isOffline ? 'Tally data unavailable' : 'No breakdown data available from Tally'}</span>
      </div>
    )
  }

  const validItems = items.filter((item) => {
    if (!item || item.value === null || item.value === undefined) {
      return false
    }

    return Number.isFinite(Number(item.value))
  })

  const total = validItems.reduce(
    (sum, item) => sum + Math.abs(Number(item.value)),
    0
  )
  if (total === 0) {
    return (
      <div className="refined-donut-wrapper">
        <div className="donut-visual-row">
          <div className="donut-svg-container">
            <svg viewBox="0 0 100 100" className="donut-svg">
              <circle cx="50" cy="50" r="38" fill="none" stroke="var(--border)" strokeWidth="14" />
            </svg>
            <div className="donut-center-text">
              <strong className="center-value">{centerTotal}</strong>
              <span className="center-label">{centerLabel}</span>
            </div>
          </div>
        </div>
        <div className="donut-legend-card-list">
          {validItems.map((item, idx) => (
            <div key={idx} className="legend-item-card">
              <div className="legend-card-top">
                <div className="legend-card-identity">
                  <span className="legend-color-dot" style={{ background: '#94a3b8' }} />
                  <span className="legend-item-title">{item.label}</span>
                </div>
                <div className="legend-card-stats">
                  <span className="legend-card-amount">₹ 0</span>
                  <span className="legend-card-pct">0%</span>
                </div>
              </div>
            </div>
          ))}
        </div>
      </div>
    )
  }

  const circumference = 2 * Math.PI * 38
  let cumulative = 0

  const segments = validItems.map((item, idx) => {
    // Magnitude is used only to draw the donut segment.
    // The authoritative Tally value itself is not modified.
    const val = Math.abs(Number(item.value))
    const pct = (val / total) * 100
    const arcLen = (pct / 100) * circumference
    const strokeDash = Math.max(arcLen - 1.5, 0.5)
    const offset = -cumulative
    cumulative += arcLen
    const color = palette[idx % palette.length]

    return {
      ...item,
      val,
      pct: pct.toFixed(1),
      strokeDasharray: `${strokeDash} ${circumference}`,
      strokeDashoffset: offset,
      color,
    }
  })

  return (
    <div className="refined-donut-wrapper">
      <div className="donut-visual-row">
        <div className="donut-svg-container">
          <svg viewBox="0 0 100 100" className="donut-svg">
            <circle cx="50" cy="50" r="38" fill="none" stroke="var(--surface-2)" strokeWidth="14" />
            {segments.map((seg, idx) => (
              <circle
                key={idx}
                cx="50"
                cy="50"
                r="38"
                fill="none"
                stroke={seg.color}
                strokeWidth="14"
                strokeDasharray={seg.strokeDasharray}
                strokeDashoffset={seg.strokeDashoffset}
                strokeLinecap="round"
                className="donut-segment"
              >
                <title>{`${seg.label}: ₹ ${Math.round(seg.val).toLocaleString('en-IN')} (${seg.pct}%)`}</title>
              </circle>
            ))}
          </svg>
          <div className="donut-center-text">
            <strong className="center-value">{centerTotal}</strong>
            <span className="center-label">{centerLabel}</span>
          </div>
        </div>
      </div>

      <div className="donut-legend-card-list">
        {segments.map((seg, idx) => (
          <div key={idx} className="legend-item-card">
            <div className="legend-card-top">
              <div className="legend-card-identity">
                <span className="legend-color-dot" style={{ background: seg.color }} />
                <span className="legend-item-title" title={seg.label}>{seg.label}</span>
                {seg.type && <span className="legend-tag-badge">{seg.type}</span>}
              </div>
              <div className="legend-card-stats">
                <span className="legend-card-amount">₹ {Math.round(seg.val).toLocaleString('en-IN')}</span>
                <span className="legend-card-pct">{seg.pct}%</span>
              </div>
            </div>
            <div className="legend-progress-bar">
              <div
                className="legend-progress-fill"
                style={{ width: `${seg.pct}%`, background: seg.color }}
              />
            </div>
          </div>
        ))}
      </div>
    </div>
  )
}

function Dashboard() {
  const navigate = useNavigate()
  const outletCtx = useOutletContext()

  // Dynamic user & company info from session
  const storedUser = sessionStorage.getItem('chat_user')
  const currentUser = storedUser ? JSON.parse(storedUser) : null
  const selectedCompany = sessionStorage.getItem('selected_company') || 'Tally'
  const username = currentUser?.username || 'User'

  const userRole =
    Array.isArray(currentUser?.roles) && currentUser.roles.length > 0
      ? currentUser.roles[0]
      : 'User'

  const userInitial = username.charAt(0).toUpperCase()

  // Dynamic filter state
  const [filterState, setFilterState] = useState(getInitialDashboardFilter)
  const [draftFromDate, setDraftFromDate] = useState(filterState.fromDate)
  const [draftToDate, setDraftToDate] = useState(filterState.toDate)
  const [validationError, setValidationError] = useState(null)
  const [refreshKey, setRefreshKey] = useState(0)
  const [showUserMenu, setShowUserMenu] = useState(false)

  const { fromDate, toDate, selectedPreset } = filterState

  const handleLogout = () => {
    clearDashboardFilter()

    if (outletCtx?.onLogout) {
      outletCtx.onLogout()
    } else {
      clearAccessToken()
      sessionStorage.removeItem('chat_user')
      sessionStorage.removeItem('selected_company')
      window.location.href = '/'
    }
  }

  // Dashboard financial-data request
  const queryUrl =
    `/dashboard/summary?from_date=${fromDate}` +
    `&to_date=${toDate}` +
    `&period=${selectedPreset || 'custom'}` +
    `&t=${refreshKey}`

  const {
    data: response,
    loading,
    error,
  } = useFetch(queryUrl, {
    timeoutMs: 45000,
  })

  // Tally connection-status request
  // This is independent from dashboard financial-data loading.
  const {
    data: tallyStatus,
    loading: tallyStatusLoading,
    error: tallyStatusError,
  } = useFetch('/tally/status', {
    timeoutMs: 10000,
  })

  const isTallyConnected = tallyStatus?.connected === true

  const isTallyDisconnected =
    tallyStatus?.connected === false || Boolean(tallyStatusError)

  // Preset period change.
  // Changing the dates already changes queryUrl, so refreshKey
  // does NOT need to be incremented here.
  const handlePeriodChange = (periodKey) => {
    setValidationError(null)

    const newRange = getPresetDateRange(periodKey)

    setDraftFromDate(newRange.fromDate)
    setDraftToDate(newRange.toDate)
    setFilterState(newRange)
    saveDashboardFilter(newRange)
  }

  const handleCustomDateChange = (field, val) => {
    setValidationError(null)

    if (field === 'from') {
      setDraftFromDate(val)
    } else {
      setDraftToDate(val)
    }

    // Custom date selection clears preset visual highlight
    setFilterState((prev) => ({
      ...prev,
      selectedPreset: null,
    }))
  }

  const handleApplyCustomDates = () => {
    const check = validateDateRange(draftFromDate, draftToDate)

    if (!check.valid) {
      setValidationError(check.error)
      return
    }

    setValidationError(null)

    const nextFilter = {
      fromDate: draftFromDate,
      toDate: draftToDate,
      selectedPreset: null,
    }

    setFilterState(nextFilter)
    saveDashboardFilter(nextFilter)
    setRefreshKey((prev) => prev + 1)
  }

  // Explicit Refresh button.
  // refreshKey is intentionally changed here because the user
  // specifically requested fresh data for the same date range.
  const handleRefresh = () => {
    const check = validateDateRange(draftFromDate, draftToDate)

    if (!check.valid) {
      setValidationError(check.error)
      return
    }

    setValidationError(null)

    const nextFilter = {
      fromDate: draftFromDate,
      toDate: draftToDate,
      selectedPreset: filterState.selectedPreset,
    }

    setFilterState(nextFilter)
    saveDashboardFilter(nextFilter)

    setRefreshKey((prev) => prev + 1)
  }

  const [cachedData, setCachedData] = useState(null)

  useEffect(() => {
    if (response?.data) {
      setCachedData(response.data)
    }
  }, [response])

  // NEVER hide whole dashboard: determine offline/error state safely
  const isOffline = Boolean(error || (response && !response.success))
  const data = response?.data || (isOffline ? null : cachedData) || {}

  // Exact Tally fields without estimates or fallbacks
  const totalSales = isOffline ? null : (data.total_sales ?? null)
  const totalPurchases = isOffline ? null : (data.total_purchases ?? null)
  const netProfit = isOffline ? null : (data.net_profit ?? null)
  const netLoss = isOffline ? null : (data.net_loss ?? null)

  const cashInHand = isOffline ? null : (data.cash_in_hand ?? null)
  const bankBalance = isOffline ? null : (data.bank_balance ?? null)
  const receivables = isOffline ? null : (data.receivables ?? null)
  const payables = isOffline ? null : (data.payables ?? null)

  // Live statutory fields from Tally Duties & Taxes
  const tdsPayable = isOffline ? null : (data.tds_payable ?? null)
  const gstPayable = isOffline ? null : (data.gst_payable ?? null)

  const topReceivables = isOffline ? [] : (data.top_receivables || [])
  const topPayables = isOffline ? [] : (data.top_payables || [])
  const cashBankAccounts = isOffline ? [] : (data.cash_bank_accounts || [])

  const expenseBreakdown = isOffline ? null : (data.expense_breakdown || null)
  const salesBreakdown = isOffline ? null : (data.sales_breakdown || null)
  const incomeVsExpense = isOffline ? null : (data.income_vs_expense || null)

  const availableIncomeVsExpense = Array.isArray(incomeVsExpense)
    ? incomeVsExpense.filter(
        (item) =>
          item?.status === 'available' &&
          (item.income !== null || item.expense !== null)
      )
    : []
  return (
    <div className="dashboard-container">
      {/* Non-blocking top progress bar during background refetches */}
      <div className={`dashboard-top-progress ${loading ? 'active' : ''}`} />

      {/* Unified Executive Dashboard Header */}
      <header className="dashboard-unified-header">
        <div className="dashboard-header-brand">
          <div className="dashboard-title-row">
            <h1>Executive Financial Dashboard</h1>
            {tallyStatusLoading && !tallyStatus ? (
              <span className="live-status-pill loading">
                <span className="pulse-dot loading" />
                Checking Tally...
              </span>
            ) : isTallyDisconnected ? (
              <span
                className="live-status-pill offline"
                title={
                  tallyStatusError ||
                  tallyStatus?.message ||
                  'Tally server unavailable'
                }
              >
                <span className="pulse-dot offline" />
                Tally Disconnected
              </span>
            ) : isTallyConnected ? (
              <span className="live-status-pill">
                <span className="pulse-dot" />
                Tally Connected
              </span>
            ) : (
              <span className="live-status-pill loading">
                <span className="pulse-dot loading" />
                Checking Tally...
              </span>
            )}
          </div>
          <p className="dashboard-header-sub">Direct real-time financial reporting from Tally ERP / Prime</p>
        </div>

        <div className="dashboard-header-controls">
          <div className="period-pills-group">
            <button
              type="button"
              className={`period-pill ${selectedPreset === '7d' ? 'active' : ''}`}
              onClick={() => handlePeriodChange('7d')}
            >
              7 Days
            </button>
            <button
              type="button"
              className={`period-pill ${selectedPreset === '1m' ? 'active' : ''}`}
              onClick={() => handlePeriodChange('1m')}
            >
              1 Month
            </button>
            <button
              type="button"
              className={`period-pill ${selectedPreset === '3m' ? 'active' : ''}`}
              onClick={() => handlePeriodChange('3m')}
            >
              3 Months
            </button>
            <button
              type="button"
              className={`period-pill ${selectedPreset === '1y' ? 'active' : ''}`}
              onClick={() => handlePeriodChange('1y')}
            >
              1 Year
            </button>
          </div>

          <div className={`date-picker-box ${validationError ? 'has-error' : ''}`}>
            <Calendar size={14} />
            <input
              type="date"
              value={draftFromDate}
              onChange={(e) => handleCustomDateChange('from', e.target.value)}
              onBlur={handleApplyCustomDates}
              className="date-input"
              title="From Date"
            />
            <span className="date-sep">-</span>
            <input
              type="date"
              value={draftToDate}
              onChange={(e) => handleCustomDateChange('to', e.target.value)}
              onBlur={handleApplyCustomDates}
              className="date-input"
              title="To Date"
            />
          </div>

          <button
            type="button"
            className="refresh-btn"
            onClick={handleRefresh}
            title="Refresh data from Tally"
            disabled={loading}
          >
            <RefreshCw size={14} className={loading ? 'spin' : ''} />
            <span>Refresh</span>
          </button>

          <div className="user-profile-badge-wrapper">
            <button
              type="button"
              className="user-profile-badge"
              onClick={() => setShowUserMenu((prev) => !prev)}
              aria-expanded={showUserMenu}
              title="Account Menu"
            >
              <div className="avatar-circle">{userInitial}</div>
              <div className="user-details">
                <span className="user-name">{username}</span>
                <span className="user-role">{userRole}</span>
              </div>
              <ChevronDown size={14} className={`dropdown-arrow ${showUserMenu ? 'open' : ''}`} />
            </button>

            {showUserMenu && (
              <div className="user-dropdown-menu">
                <div className="user-dropdown-header">
                  <strong>{username}</strong>
                  <span>{userRole} • {selectedCompany}</span>
                </div>
                <div className="dropdown-divider" />
                <button
                  type="button"
                  className="dropdown-logout-item"
                  onClick={handleLogout}
                >
                  <LogOut size={15} />
                  <span>Sign Out</span>
                </button>
              </div>
            )}
          </div>
        </div>
      </header>

      {/* Date Validation Notice */}
      {validationError && (
        <div className="date-validation-banner" role="alert">
          <AlertCircle size={15} />
          <span>{validationError}</span>
        </div>
      )}

      {/* Key Financial Indicators & Operational Balances (10 Equal Cards: 5x2 Grid) */}
      <div className="dashboard-section-title">
        <span className="section-icon-badge"><BarChart3 size={14} /></span>
        <span>Key Financial Indicators & Operational Balances</span>
      </div>

      <div className="unified-kpi-grid">
        {/* Card 1: Total Sales */}
        <div className="unified-kpi-card">
          <div className="unified-kpi-header">
            <div className="unified-kpi-icon sales-icon">
              <TrendingUp size={18} />
            </div>
            <span className="unified-kpi-label">Total Sales</span>
          </div>
          <div className="unified-kpi-value">{formatCurrency(totalSales, isOffline, loading)}</div>
          <div className="unified-kpi-subtext">
            <span>Selected P&L Period</span>
          </div>
        </div>

        {/* Card 2: Total Purchases */}
        <div className="unified-kpi-card">
          <div className="unified-kpi-header">
            <div className="unified-kpi-icon purchases-icon">
              <TrendingDown size={18} />
            </div>
            <span className="unified-kpi-label">Total Purchases</span>
          </div>
          <div className="unified-kpi-value">{formatCurrency(totalPurchases, isOffline, loading)}</div>
          <div className="unified-kpi-subtext">
            <span>Selected P&L Period</span>
          </div>
        </div>

        {/* Card 3: Net Profit */}
        <div className="unified-kpi-card">
          <div className="unified-kpi-header">
            <div className="unified-kpi-icon profit-icon">
              <Wallet size={18} />
            </div>
            <span className="unified-kpi-label">Net Profit</span>
          </div>
          <div className="unified-kpi-value">{formatCurrency(netProfit, isOffline, loading)}</div>
          <div className="unified-kpi-subtext">
            <span>After Tax & Overheads</span>
          </div>
        </div>

        {/* Card 4: Net Loss */}
        <div className="unified-kpi-card">
          <div className="unified-kpi-header">
            <div className="unified-kpi-icon loss-icon">
              <TrendingDown size={18} />
            </div>
            <span className="unified-kpi-label">Net Loss</span>
          </div>
          <div className="unified-kpi-value">{formatCurrency(netLoss, isOffline, loading)}</div>
          <div className="unified-kpi-subtext">
            <span>Operational Deficit</span>
          </div>
        </div>

        {/* Card 5: Cash in Hand */}
        <div className="unified-kpi-card">
          <div className="unified-kpi-header">
            <div className="unified-kpi-icon green-icon">
              <Wallet size={18} />
            </div>
            <span className="unified-kpi-label">Cash in Hand</span>
          </div>
          <div className="unified-kpi-value">{formatCurrency(cashInHand, isOffline, loading)}</div>
          <div className="unified-kpi-subtext">
            <span>Liquid Cash Ledger</span>
          </div>
        </div>

        {/* Card 6: Bank Balance */}
        <div className="unified-kpi-card">
          <div className="unified-kpi-header">
            <div className="unified-kpi-icon blue-icon">
              <Landmark size={18} />
            </div>
            <span className="unified-kpi-label">Bank Balance</span>
          </div>
          <div className="unified-kpi-value">{formatCurrency(bankBalance, isOffline, loading)}</div>
          <div className="unified-kpi-subtext">
            <span>Bank Accounts</span>
          </div>
        </div>

        {/* Card 7: Receivables */}
        <div className="unified-kpi-card">
          <div className="unified-kpi-header">
            <div className="unified-kpi-icon orange-icon">
              <UserCheck size={18} />
            </div>
            <span className="unified-kpi-label">Receivables</span>
          </div>
          <div className="unified-kpi-value">{formatCurrency(receivables, isOffline, loading)}</div>
          <div className="unified-kpi-subtext">
            <span>Debtors Due</span>
          </div>
        </div>

        {/* Card 8: Payables */}
        <div className="unified-kpi-card">
          <div className="unified-kpi-header">
            <div className="unified-kpi-icon purple-icon">
              <ArrowUpRight size={18} />
            </div>
            <span className="unified-kpi-label">Payables</span>
          </div>
          <div className="unified-kpi-value">{formatCurrency(payables, isOffline, loading)}</div>
          <div className="unified-kpi-subtext">
            <span>Creditors Due</span>
          </div>
        </div>

        {/* Card 9: TDS Payable */}
        <div className="unified-kpi-card" title={tdsPayable === 0 ? 'No TDS liabilities recorded in Tally' : undefined}>
          <div className="unified-kpi-header">
            <div className="unified-kpi-icon red-icon">
              <Receipt size={18} />
            </div>
            <span className="unified-kpi-label">TDS Payable</span>
          </div>
          <div className="unified-kpi-value">{formatCurrency(tdsPayable, isOffline, loading)}</div>
          <div className="unified-kpi-subtext">
            <span>{tdsPayable === 0 ? 'No Dues Recorded' : 'Statutory Liability'}</span>
          </div>
        </div>

        {/* Card 10: GST Payable */}
        <div className="unified-kpi-card" title="Net GST Payable (Output Tax minus Input Tax Credit)">
          <div className="unified-kpi-header">
            <div className="unified-kpi-icon teal-icon">
              <Percent size={18} />
            </div>
            <span className="unified-kpi-label">GST Payable</span>
          </div>
          <div className="unified-kpi-value">{formatCurrency(gstPayable, isOffline, loading)}</div>
          <div className="unified-kpi-subtext">
            <span>{gstPayable !== null ? 'Net Payable (Output - ITC)' : 'Tax Provision'}</span>
          </div>
        </div>
      </div>

      {/* Operational Balances & Ledger Outstandings */}
      <div className="dashboard-section-title">
        <span className="section-icon-badge"><Receipt size={14} /></span>
        <span>Operational Balances & Ledger Outstandings</span>
      </div>

      <div className="middle-tables-grid">
        {/* Card 1: Top Receivables (Debtors) */}
        <div className="table-card">
          <div className="table-card-header">
            <h3>Top Receivables (Debtors)</h3>
            <Link to="/reports/receivables" className="view-all-link">View All →</Link>
          </div>
          <div className="table-wrapper">
            {topReceivables.length > 0 ? (
              <table className="dashboard-table">
                <thead>
                  <tr>
                    <th>Party Name</th>
                    <th className="text-right">Outstanding (₹)</th>
                    <th className="text-center">Days Overdue</th>
                    <th className="text-center">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {topReceivables.map((row, idx) => (
                    <tr key={idx}>
                      <td className="party-name">{row.party}</td>
                      <td className="text-right font-semibold">{Number(row.amount).toLocaleString('en-IN')}</td>
                      <td className="text-center">{row.days_overdue ?? 'N/A'}</td>
                      <td className="text-center">
                        <span className={`status-badge ${(row.status || 'normal').toLowerCase().replace(' ', '-')}`}>
                          {row.status || 'Normal'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="no-data-banner">
                {isOffline ? 'Tally data unavailable' : 'No receivables outstanding in Tally'}
              </div>
            )}
          </div>
        </div>

        {/* Card 2: Top Payables (Creditors) */}
        <div className="table-card">
          <div className="table-card-header">
            <h3>Top Payables (Creditors)</h3>
            <Link to="/reports/payables" className="view-all-link">View All →</Link>
          </div>
          <div className="table-wrapper">
            {topPayables.length > 0 ? (
              <table className="dashboard-table">
                <thead>
                  <tr>
                    <th>Party Name</th>
                    <th className="text-right">Outstanding (₹)</th>
                    <th className="text-center">Due Date</th>
                    <th className="text-center">Status</th>
                  </tr>
                </thead>
                <tbody>
                  {topPayables.map((row, idx) => (
                    <tr key={idx}>
                      <td className="party-name">{row.party}</td>
                      <td className="text-right font-semibold">{Number(row.amount).toLocaleString('en-IN')}</td>
                      <td className="text-center">{row.due_date || 'N/A'}</td>
                      <td className="text-center">
                        <span className={`status-badge ${(row.status || 'normal').toLowerCase().replace(' ', '-')}`}>
                          {row.status || 'Normal'}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <div className="no-data-banner">
                {isOffline ? 'Tally data unavailable' : 'No payables outstanding in Tally'}
              </div>
            )}
          </div>
        </div>

        {/* Card 3: Cash / Bank Balances */}
        <div className="table-card">
          <div className="table-card-header">
            <h3>Cash / Bank Balances</h3>
            <Link to="/reports/ledger" className="view-all-link">View All →</Link>
          </div>
          <div className="table-wrapper">
            {cashBankAccounts.length > 0 ? (
              <table className="dashboard-table">
                <thead>
                  <tr>
                    <th>Account Name</th>
                    <th className="text-right">Balance (₹)</th>
                  </tr>
                </thead>
                <tbody>
                  {cashBankAccounts.map((acc, idx) => (
                    <tr key={idx}>
                      <td className="party-name">{acc.name}</td>
                      <td className="text-right font-semibold">{Number(acc.balance).toLocaleString('en-IN')}</td>
                    </tr>
                  ))}
                </tbody>
                {bankBalance !== null && bankBalance !== undefined && (
                  <tfoot>
                    <tr className="total-row">
                      <td><strong>Total Bank</strong></td>
                      <td className="text-right"><strong>{formatCurrency(bankBalance, isOffline, loading)}</strong></td>
                    </tr>
                  </tfoot>
                )}
              </table>
            ) : (
              <div className="no-data-banner">
                {isOffline ? 'Tally data unavailable' : 'No cash/bank accounts found in Tally'}
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Visual Analytics & Breakdown */}
      <div className="dashboard-section-title">
        <span className="section-icon-badge"><PieChart size={14} /></span>
        <span>Financial Analytics & Expense Distributions</span>
      </div>

      <div className="charts-grid">
        {/* Chart 1: Income vs Expense Bar Chart */}
        <div className="chart-card flex-2">
          <div className="chart-card-header">
            <h3>Income vs Expense</h3>
            {availableIncomeVsExpense.length > 0 && (
              <div className="chart-legend">
                <div className="legend-item">
                  <span className="legend-dot sales-dot" />
                  <span>Sales</span>
                </div>
                <div className="legend-item">
                  <span className="legend-dot purchases-dot" />
                  <span>Purchases</span>
                </div>
              </div>
            )}
          </div>
          {availableIncomeVsExpense.length > 0 ? (
            <div className="bar-chart-container">
              <div className="bars-wrapper">
                {(() => {
                  const maxVal = Math.max(
                    ...availableIncomeVsExpense.map((d) =>
                      Math.max(d.income ?? 0, d.expense ?? 0)
                    ),
                    1
                  )
                  return availableIncomeVsExpense.map((item, idx) => {
                    const incomeHeight = Math.max(Math.round((item.income / maxVal) * 160), item.income > 0 ? 6 : 0)
                    const expenseHeight = Math.max(Math.round((item.expense / maxVal) * 160), item.expense > 0 ? 6 : 0)
                    return (
                      <div key={idx} className="bar-group">
                        <div className="bars-pair">
                          <div
                            className="bar sales-bar"
                            style={{ height: `${incomeHeight}px` }}
                            title={`Sales (${item.month}): ₹ ${Number(item.income).toLocaleString('en-IN')}`}
                          />
                          <div
                            className="bar purchases-bar"
                            style={{ height: `${expenseHeight}px` }}
                            title={`Purchases (${item.month}): ₹ ${Number(item.expense).toLocaleString('en-IN')}`}
                          />
                        </div>
                        <span className="x-label">{item.month}</span>
                      </div>
                    )
                  })
                })()}
              </div>
            </div>
          ) : (
            <div className="unconnected-chart-banner">
              <span>{isOffline ? 'Tally data unavailable' : 'No period trend series available from Tally'}</span>
            </div>
          )}
        </div>

        {/* Chart 2: Expense Breakdown Donut Chart */}
        <div className="chart-card">
          <div className="chart-card-header">
            <h3>Expense Breakdown</h3>
          </div>
          <RefinedDonutChart
            items={expenseBreakdown}
            centerTotal={formatCurrency(totalPurchases, isOffline, loading)}
            centerLabel="Total Expenses"
            palette={EXPENSE_PALETTE}
            isOffline={isOffline}
            loading={loading}
          />
        </div>

        {/* Chart 3: Sales Breakdown Donut Chart */}
        <div className="chart-card">
          <div className="chart-card-header">
            <h3>Sales & Revenue Breakdown</h3>
          </div>
          {salesBreakdown && salesBreakdown.length > 0 && (
            <div className="sales-breakdown-summary">
              <span>Gross Operating Turnover:</span>
              <strong>{formatCurrency(totalSales, isOffline, loading)}</strong>
            </div>
          )}
          <RefinedDonutChart
            items={salesBreakdown}
            centerTotal={formatCurrency(totalSales, isOffline, loading)}
            centerLabel="Total Inflow"
            palette={SALES_PALETTE}
            isOffline={isOffline}
            loading={loading}
          />
        </div>
      </div>
    </div>
  )
}

export default Dashboard
