import { Suspense, lazy, useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router'
import { BarChart3, Loader2 } from 'lucide-react'

import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
const Ledger = lazy(() => import('./pages/Ledger'))
const LedgerMonthDetail = lazy(() => import('./pages/LedgerMonthDetail'))
const VoucherDetail = lazy(() => import('./pages/Voucherdetail'))
const ProfitLoss = lazy(() => import('./pages/ProfitLoss'))
const GroupSummary = lazy(() => import('./pages/GroupSummary'))
const DayBook = lazy(() => import('./pages/DayBook'))
const Receivables = lazy(() => import('./pages/Receivables'))
const Payables = lazy(() => import('./pages/Payables'))
const PendingInvoices = lazy(() => import('./pages/PendingInvoices'))
const TrialBalance = lazy(() => import('./pages/TrialBalance'))
const TrialBalanceGroup = lazy(() => import('./pages/trialBalance/TrialBalanceGroup'))
const TrialBalanceOpeningStock = lazy(() => import('./pages/trialBalance/TrialBalanceOpeningStock'))
const TrialBalancePurchaseBillsPending = lazy(() => import('./pages/trialBalance/TrialBalancePurchaseBillsPending'))
const BalanceSheet = lazy(() => import('./pages/BalanceSheet'))
const BalanceSheetGroup = lazy(() => import('./pages/Balancesheet/BalanceSheetGroup'))
const ClosingStockSummary = lazy(() => import('./pages/ClosingStockSummary'))
const Inventory = lazy(() => import('./pages/Inventory'))
const StockItemMonthlySummary = lazy(() => import('./pages/StockItemMonthlySummary'))
const StockItemVouchers = lazy(() => import('./pages/StockItemVouchers'))
const StockItemBillsPending = lazy(() => import('./pages/StockItemBillsPending'))
const InventoryVoucherDetail = lazy(() => import('./pages/InventoryVoucherDetail'))
const StockGroupItems = lazy(() => import('./pages/StockGroupItems'))
const StockSummaryDrill = lazy(() => import('./pages/StockSummaryDrill'))
const RegisterVouchers = lazy(() => import('./pages/RegisterVouchers'))
const LocationSummary = lazy(() => import('./pages/LocationSummary'))
const LocationMonthlySummary = lazy(() => import('./pages/LocationMonthlySummary'))
const LocationVouchers = lazy(() => import('./pages/LocationVouchers'))
const TallyStatus = lazy(() => import('./pages/TallyStatus'))
const Chatbot = lazy(() => import('./pages/Chatbot'))
import Login from './pages/Login'
const UserManagement = lazy(() => import('./pages/UserManagement'))
const ReportsIndex = lazy(() => import('./pages/ReportsIndex'))

import { apiGet, apiPost } from './api/client'
import { clearBrowserCache } from './utils/browserCache'
import { clearChatHistory } from './utils/chatHistory'


// Old paths that no longer have their own route. The other old
// top-level report paths (/ledger, /profit-loss, ...) still render
// directly above, so they are not redirected.
const LEGACY_REPORT_REDIRECTS = [
  ['/inventory', '/reports/inventory'],
]


function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(false)
  const [authLoading, setAuthLoading] = useState(true)

  const [currentUser, setCurrentUser] = useState(() => {
    try {
      const storedUser = sessionStorage.getItem('chat_user')

      return storedUser
        ? JSON.parse(storedUser)
        : null
    } catch {
      return null
    }
  })


  // Verify authentication with the backend when the application starts.
  // The browser automatically sends the HttpOnly access-token cookie.
  useEffect(() => {
    let cancelled = false

    async function verifyAuthentication() {
      try {
        const user = await apiGet('/auth/me')

        if (cancelled) {
          return
        }

        setCurrentUser(user)

        sessionStorage.setItem(
          'chat_user',
          JSON.stringify(user),
        )

        setIsAuthenticated(true)
      } catch {
        if (cancelled) {
          return
        }

        sessionStorage.removeItem('chat_user')
        sessionStorage.removeItem('selected_company')
        // Explicitly clear non-HttpOnly CSRF cookie on client side as well
    document.cookie = 'csrf_token=; Max-Age=0; path=/; SameSite=Lax'
    clearBrowserCache()

        setCurrentUser(null)
        setIsAuthenticated(false)
      } finally {
        if (!cancelled) {
          setAuthLoading(false)
        }
      }
    }

    verifyAuthentication()

    return () => {
      cancelled = true
    }
  }, [])


  // Listen for session expiration events dispatched when token refresh fails
  useEffect(() => {
    function handleSessionExpired() {
      sessionStorage.removeItem('chat_user')
      sessionStorage.removeItem('selected_company')
      sessionStorage.removeItem('tfi.dashboard.date_filter')
      // Explicitly clear non-HttpOnly CSRF cookie on client side as well
    document.cookie = 'csrf_token=; Max-Age=0; path=/; SameSite=Lax'
    clearBrowserCache()
      setCurrentUser(null)
      setIsAuthenticated(false)
    }

    window.addEventListener('tfi:session-expired', handleSessionExpired)
    return () => {
      window.removeEventListener('tfi:session-expired', handleSessionExpired)
    }
  }, [])


  function handleLogin(user) {
    if (user) {
      setCurrentUser(user)
      setIsAuthenticated(true)
      return
    }

    try {
      const storedUser = sessionStorage.getItem('chat_user')

      setCurrentUser(
        storedUser
          ? JSON.parse(storedUser)
          : null
      )
    } catch {
      setCurrentUser(null)
    }

    setIsAuthenticated(true)
  }


  // Temporary frontend logout.
  // The next step will add /auth/logout so the backend
  // can delete the HttpOnly authentication cookie.
  async function handleLogout() {
  try {
    await apiPost('/auth/logout')
  } catch (error) {
    console.error(
      'Backend logout failed:',
      error
    )
  } finally {
    // Explicitly clear non-HttpOnly CSRF cookie on client side as well
    document.cookie = 'csrf_token=; Max-Age=0; path=/; SameSite=Lax'
    clearBrowserCache()
    sessionStorage.removeItem('chat_user')
    sessionStorage.removeItem('selected_company')
    sessionStorage.removeItem(
      'tfi.dashboard.date_filter'
    )
    clearChatHistory()

    setCurrentUser(null)
    setIsAuthenticated(false)
  }
}


  // Wait until /auth/me has checked the HttpOnly cookie.
  if (authLoading) {
    return (
      <div className="login-page">
        <main className="login-main">
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', gap: '12px' }}>
            <div className="login-logo" style={{ width: '48px', height: '48px' }}>
              <BarChart3 size={24} />
            </div>
            <Loader2 size={24} className="spin" style={{ color: 'var(--accent)', marginTop: '8px' }} />
          </div>
        </main>
      </div>
    )
  }


  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />
  }


  const roles = Array.isArray(currentUser?.roles)
    ? currentUser.roles
    : []

  const canManageUsers =
    roles.includes('superadmin') ||
    roles.includes('admin')


  // Report pages are loaded on first visit instead of all at sign-in.
  return (
    <Suspense
      fallback={
        <div className="loader" role="status">
          <Loader2 size={20} className="spin" /> Loading…
        </div>
      }
    >
    <Routes>
      <Route element={<Layout onLogout={handleLogout} />}>
        <Route
          path="/"
          element={<Dashboard />}
        />

        <Route
          path="/ledger"
          element={<Ledger />}
        />

        <Route
          path="/profit-loss"
          element={<ProfitLoss />}
        />

        <Route
          path="/receivables"
          element={<Receivables />}
        />

        <Route
          path="/payables"
          element={<Payables />}
        />

        <Route
          path="/pending-invoices"
          element={<PendingInvoices />}
        />

        <Route
          path="/trial-balance"
          element={<TrialBalance />}
        />

        <Route
          path="/balance-sheet"
          element={<BalanceSheet />}
        />

        <Route
          path="/tally-status"
          element={<TallyStatus />}
        />

        <Route
          path="/chatbot"
          element={<Chatbot />}
        />

        <Route
          path="/admin/users"
          element={
            canManageUsers
              ? <UserManagement />
              : <Navigate to="/" replace />
          }
        />

        <Route
          path="/reports"
          element={<ReportsIndex />}
        />

        {/* Financial Reports */}

        <Route
          path="/reports/profit-loss"
          element={<ProfitLoss />}
        />

        <Route
          path="/reports/group-summary"
          element={<GroupSummary />}
        />

        <Route
          path="/reports/balance-sheet"
          element={<BalanceSheet />}
        />

        <Route
          path="/reports/balance-sheet/group"
          element={<BalanceSheetGroup />}
        />

        <Route
          path="/reports/closing-stock"
          element={<ClosingStockSummary />}
        />

        <Route
          path="/reports/trial-balance"
          element={<TrialBalance />}
        />

        <Route
          path="/reports/trial-balance/group"
          element={<TrialBalanceGroup />}
        />

        <Route
          path="/reports/trial-balance/opening-stock"
          element={<TrialBalanceOpeningStock />}
        />

        <Route
          path="/reports/trial-balance/purchase-bills-pending"
          element={<TrialBalancePurchaseBillsPending />}
        />

        {/* Day Book */}

        <Route
          path="/reports/day-book"
          element={<DayBook />}
        />

        {/* Ledger Reports */}

        <Route
          path="/reports/ledger"
          element={<Ledger />}
        />

        <Route
          path="/reports/ledger/month"
          element={<LedgerMonthDetail />}
        />

        <Route
          path="/reports/voucher"
          element={<VoucherDetail />}
        />

        {/* Outstanding Reports */}

        <Route
          path="/reports/receivables"
          element={<Receivables />}
        />

        <Route
          path="/reports/payables"
          element={<Payables />}
        />

        <Route
          path="/reports/pending-invoices"
          element={<PendingInvoices />}
        />

        {/* Stock Reports */}
        <Route path="/reports/inventory" element={<Inventory />} />
        <Route path="/reports/stock-item-monthly" element={<StockItemMonthlySummary />} />
        <Route path="/reports/stock-item-vouchers" element={<StockItemVouchers />} />
        <Route path="/reports/stock-item-bills-pending" element={<StockItemBillsPending />} />
        <Route path="/reports/inventory-voucher" element={<InventoryVoucherDetail />} />
        <Route path="/reports/registers/:key/vouchers" element={<RegisterVouchers />} />
        <Route path="/reports/stock-groups/:name" element={<StockSummaryDrill kind="group" />} />
        <Route path="/reports/stock-categories/:name" element={<StockSummaryDrill kind="category" />} />
        <Route path="/reports/godowns/:name" element={<StockSummaryDrill kind="godown" />} />
        {/* Old query-string links; both redirect to the dynamic routes above. */}
        <Route path="/reports/stock-group-items" element={<StockGroupItems />} />
        <Route path="/reports/location-summary" element={<LocationSummary />} />
        <Route path="/reports/location-monthly" element={<LocationMonthlySummary />} />
        <Route path="/reports/location-vouchers" element={<LocationVouchers />} />

        {LEGACY_REPORT_REDIRECTS.map(([from, to]) => (
          <Route
            key={from}
            path={from}
            element={
              <Navigate
                to={to}
                replace
              />
            }
          />
        ))}
      </Route>
    </Routes>
    </Suspense>
  )
}

export default App