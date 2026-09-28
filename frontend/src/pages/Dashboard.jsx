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
  const num = Math.abs(Math.round(Number(val)))
  return '₹ ' + num.toLocaleString('en-IN')
}

function Dashboard() {
  const navigate = useNavigate()
  const outletCtx = useOutletContext()

  // Dynamic user & company info from session
  const storedUser = sessionStorage.getItem('chat_user')
  const currentUser = storedUser ? JSON.parse(storedUser) : null
  const selectedCompany = sessionStorage.getItem('selected_company') || 'Tally'
  const username = currentUser?.username || 'User'
  const userRole = Array.isArray(currentUser?.roles) && currentUser.roles.length > 0
    ? currentUser.roles[0]
    : 'User'
  const userInitial = username.charAt(0).toUpperCase()

  // Dynamic filter state initialized from sessionStorage or FY 2025-2026 default
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

  const queryUrl = `/dashboard/summary?from_date=${fromDate}&to_date=${toDate}&period=${selectedPreset || 'custom'}&t=${refreshKey}`
  const { data: response, loading, error, refetch } = useFetch(queryUrl)

  const handlePeriodChange = (periodKey) => {
    setValidationError(null)
    const newRange = getPresetDateRange(periodKey)
    setDraftFromDate(newRange.fromDate)
    setDraftToDate(newRange.toDate)
    setFilterState(newRange)
    saveDashboardFilter(newRange)
    setRefreshKey((prev) => prev + 1)
  }

  const handleCustomDateChange = (field, val) => {
    setValidationError(null)
    if (field === 'from') {
      setDraftFromDate(val)
    } else {
      setDraftToDate(val)
    }
    // Custom date selection immediately clears preset visual highlight
    setFilterState((prev) => ({ ...prev, selectedPreset: null }))
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
    if (refetch) refetch()
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

  return (
    <div className="dashboard-container">
      {/* Non-blocking top progress bar during background refetches */}
      <div className={`dashboard-top-progress ${loading ? 'active' : ''}`} />

      {/* Unified Executive Dashboard Header */}
      <header className="dashboard-unified-header">
        <div className="dashboard-header-brand">
          <div className="dashboard-title-row">
            <h1>Executive Financial Dashboard</h1>
            {loading && !response?.data ? (
              <span className="live-status-pill loading">
                <span className="pulse-dot loading" />
                Connecting...
              </span>
            ) : isOffline ? (
              <span className="live-status-pill offline" title={error || response?.error || 'Tally server offline'}>
                <span className="pulse-dot offline" />
                Tally Offline
              </span>
            ) : (
              <span className="live-status-pill">
                <span className="pulse-dot" />
                Tally Live
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

      {/* Row 1: Executive KPI Cards (4 Cards) */}
      <div className="kpi-cards-grid">
        <div className="kpi-card">
          <div className="kpi-header">
            <div className="kpi-icon-box sales-icon">
              <TrendingUp size={20} />
            </div>
            <div className="kpi-meta">
              <span className="kpi-label">Total Sales</span>
            </div>
          </div>
          <div className="kpi-value">{formatCurrency(totalSales, isOffline, loading)}</div>
          <div className="kpi-subtext">Selected P&L Period</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-header">
            <div className="kpi-icon-box purchases-icon">
              <TrendingDown size={20} />
            </div>
            <div className="kpi-meta">
              <span className="kpi-label">Total Purchases</span>
            </div>
          </div>
          <div className="kpi-value">{formatCurrency(totalPurchases, isOffline, loading)}</div>
          <div className="kpi-subtext">Selected P&L Period</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-header">
            <div className="kpi-icon-box profit-icon">
              <Wallet size={20} />
            </div>
            <div className="kpi-meta">
              <span className="kpi-label">Net Profit</span>
            </div>
          </div>
          <div className="kpi-value">{formatCurrency(netProfit, isOffline, loading)}</div>
          <div className="kpi-subtext">Selected P&L Period</div>
        </div>

        <div className="kpi-card">
          <div className="kpi-header">
            <div className="kpi-icon-box loss-icon">
              <TrendingDown size={20} />
            </div>
            <div className="kpi-meta">
              <span className="kpi-label">Net Loss</span>
            </div>
          </div>
          <div className="kpi-value">{formatCurrency(netLoss, isOffline, loading)}</div>
          <div className="kpi-subtext">Selected P&L Period</div>
        </div>
      </div>

      {/* Row 2: Quick Stat Cards Grid (6 Cards) */}
      <div className="quick-stats-grid">
        <div className="stat-pill-card">
          <div className="stat-pill-icon green-icon">
            <Wallet size={16} />
          </div>
          <div className="stat-pill-content">
            <span className="stat-pill-label">Cash in Hand</span>
            <span className="stat-pill-value">{formatCurrency(cashInHand, isOffline, loading)}</span>
          </div>
        </div>

        <div className="stat-pill-card">
          <div className="stat-pill-icon blue-icon">
            <Landmark size={16} />
          </div>
          <div className="stat-pill-content">
            <span className="stat-pill-label">Bank Balance</span>
            <span className="stat-pill-value">{formatCurrency(bankBalance, isOffline, loading)}</span>
          </div>
        </div>

        <div className="stat-pill-card">
          <div className="stat-pill-icon orange-icon">
            <UserCheck size={16} />
          </div>
          <div className="stat-pill-content">
            <span className="stat-pill-label">Receivables</span>
            <span className="stat-pill-value">{formatCurrency(receivables, isOffline, loading)}</span>
          </div>
        </div>

        <div className="stat-pill-card">
          <div className="stat-pill-icon purple-icon">
            <ArrowUpRight size={16} />
          </div>
          <div className="stat-pill-content">
            <span className="stat-pill-label">Payables</span>
            <span className="stat-pill-value">{formatCurrency(payables, isOffline, loading)}</span>
          </div>
        </div>

        <div className="stat-pill-card">
          <div className="stat-pill-icon red-icon">
            <Receipt size={16} />
          </div>
          <div className="stat-pill-content">
            <span className="stat-pill-label">TDS Payable</span>
            <span className="stat-pill-value">{formatCurrency(tdsPayable, isOffline, loading)}</span>
          </div>
        </div>

        <div className="stat-pill-card">
          <div className="stat-pill-icon teal-icon">
            <Percent size={16} />
          </div>
          <div className="stat-pill-content">
            <span className="stat-pill-label">GST Payable</span>
            <span className="stat-pill-value">{formatCurrency(gstPayable, isOffline, loading)}</span>
          </div>
        </div>
      </div>

      {/* Row 3: Middle Tables Grid (3 Cards) */}
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

      {/* Row 4: Visual Analytics Charts Grid (3 Cards) */}
      <div className="charts-grid">
        {/* Chart 1: Income vs Expense Bar Chart */}
        <div className="chart-card flex-2">
          <div className="chart-card-header">
            <h3>Income vs Expense</h3>
            {incomeVsExpense && incomeVsExpense.length > 0 && (
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
          {incomeVsExpense && incomeVsExpense.length > 0 ? (
            <div className="bar-chart-container">
              <div className="bars-wrapper">
                {(() => {
                  const maxVal = Math.max(...incomeVsExpense.map(d => Math.max(d.income, d.expense)), 1)
                  return incomeVsExpense.map((item, idx) => {
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
          {expenseBreakdown && expenseBreakdown.length > 0 ? (
            <div className="donut-chart-wrapper">
              <div className="donut-svg-container">
                <svg viewBox="0 0 100 100" className="donut-svg">
                  <circle cx="50" cy="50" r="38" fill="none" stroke="#e4e7ec" strokeWidth="18" />
                </svg>
                <div className="donut-center-text">
                  <strong className="center-value">{formatCurrency(totalPurchases, isOffline, loading)}</strong>
                  <span className="center-label">Total Expenses</span>
                </div>
              </div>
              <div className="donut-legend-list">
                {expenseBreakdown.map((item, idx) => (
                  <div key={idx} className="legend-row">
                    <span className="legend-name">{item.label}</span>
                    <span className="legend-pct">₹ {Number(item.value).toLocaleString('en-IN')}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="unconnected-chart-banner">
              <span>{isOffline ? 'Tally data unavailable' : 'No category breakdown provided by Tally P&L'}</span>
            </div>
          )}
        </div>

        {/* Chart 3: Sales Breakdown Donut Chart */}
        <div className="chart-card">
          <div className="chart-card-header">
            <h3>Sales Breakdown</h3>
          </div>
          {salesBreakdown && salesBreakdown.length > 0 ? (
            <div className="donut-chart-wrapper">
              <div className="donut-svg-container">
                <svg viewBox="0 0 100 100" className="donut-svg">
                  <circle cx="50" cy="50" r="38" fill="none" stroke="#e4e7ec" strokeWidth="18" />
                </svg>
                <div className="donut-center-text">
                  <strong className="center-value">{formatCurrency(totalSales, isOffline, loading)}</strong>
                  <span className="center-label">Total Sales</span>
                </div>
              </div>
              <div className="donut-legend-list">
                {salesBreakdown.map((item, idx) => (
                  <div key={idx} className="legend-row">
                    <span className="legend-name">{item.label}</span>
                    <span className="legend-pct">₹ {Number(item.value).toLocaleString('en-IN')}</span>
                  </div>
                ))}
              </div>
            </div>
          ) : (
            <div className="unconnected-chart-banner">
              <span>{isOffline ? 'Tally data unavailable' : 'No category breakdown provided by Tally P&L'}</span>
            </div>
          )}
        </div>
      </div>
    </div>
  )
}

export default Dashboard
