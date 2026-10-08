import { useEffect, useState } from 'react'
import { Routes, Route, Navigate } from 'react-router'

import Layout from './components/layout/Layout'
import Dashboard from './pages/Dashboard'
import Ledger from './pages/Ledger'
import LedgerMonthDetail from './pages/LedgerMonthDetail'
import VoucherDetail from './pages/Voucherdetail'
import ProfitLoss from './pages/ProfitLoss'
import GroupSummary from './pages/GroupSummary'
import Receivables from './pages/Receivables'
import Payables from './pages/Payables'
import PendingInvoices from './pages/PendingInvoices'
import TrialBalance from './pages/TrialBalance'
import TrialBalanceGroup from './pages/trialBalance/TrialBalanceGroup'
import TrialBalanceOpeningStock from './pages/trialBalance/TrialBalanceOpeningStock'
import TrialBalancePurchaseBillsPending from './pages/trialBalance/TrialBalancePurchaseBillsPending'
import BalanceSheet from './pages/BalanceSheet'
import BalanceSheetGroup from './pages/Balancesheet/BalanceSheetGroup'
import ClosingStockSummary from './pages/ClosingStockSummary'
import Inventory from './pages/Inventory'
import StockItemMonthlySummary from './pages/StockItemMonthlySummary'
import StockItemVouchers from './pages/StockItemVouchers'
import InventoryVoucherDetail from './pages/InventoryVoucherDetail'
import StockGroupItems from './pages/StockGroupItems'
import StockSummaryDrill from './pages/StockSummaryDrill'
import RegisterVouchers from './pages/RegisterVouchers'
import LocationSummary from './pages/LocationSummary'
import LocationMonthlySummary from './pages/LocationMonthlySummary'
import LocationVouchers from './pages/LocationVouchers'
import TallyStatus from './pages/TallyStatus'
import Chatbot from './pages/Chatbot'
import Login from './pages/Login'
import UserManagement from './pages/UserManagement'
import ReportsIndex from './pages/ReportsIndex'

import { apiGet, apiPost } from './api/client'
import { clearBrowserCache } from './utils/browserCache'


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


  function handleLogin() {
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
    clearBrowserCache()
    sessionStorage.removeItem('chat_user')
    sessionStorage.removeItem('selected_company')
    sessionStorage.removeItem(
      'tfi.dashboard.date_filter'
    )

    setCurrentUser(null)
    setIsAuthenticated(false)
  }
}


  // Wait until /auth/me has checked the HttpOnly cookie.
  if (authLoading) {
    return null
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


  return (
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

        <Route
          path="/reports/inventory"
          element={<Inventory />}
        />

        <Route
          path="/reports/stock-item-monthly"
          element={<StockItemMonthlySummary />}
        />

        <Route
          path="/reports/stock-item-vouchers"
          element={<StockItemVouchers />}
        />

        <Route
          path="/reports/stock-group-items"
          element={<StockGroupItems />}
        />

        <Route
          path="/reports/location-summary"
          element={<LocationSummary />}
        />

        <Route
          path="/reports/location-monthly"
          element={<LocationMonthlySummary />}
        />

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
  )
}

export default App