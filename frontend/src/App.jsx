import { useState } from 'react'
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
import BalanceSheet from './pages/BalanceSheet'
import Inventory from './pages/Inventory'
import TallyStatus from './pages/TallyStatus'
import Chatbot from './pages/Chatbot'
import Login from './pages/Login'
import UserManagement from './pages/UserManagement'
import ReportsIndex from './pages/ReportsIndex'

import {
  getAccessToken,
  clearAccessToken,
} from './api/client'

// Old paths that no longer have their own route. The other old
// top-level report paths (/ledger, /profit-loss, ...) still render
// directly above, so they are not redirected.
const LEGACY_REPORT_REDIRECTS = [
  ['/inventory', '/reports/inventory'],
]


function App() {
  const [isAuthenticated, setIsAuthenticated] = useState(
    () => Boolean(getAccessToken())
  )

  function handleLogin() {
    setIsAuthenticated(true)
  }

  function handleLogout() {
    clearAccessToken()

    sessionStorage.removeItem('chat_user')
    sessionStorage.removeItem('selected_company')

    setIsAuthenticated(false)
  }

  if (!isAuthenticated) {
    return <Login onLogin={handleLogin} />
  }

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
        <Route path="/chatbot" element={<Chatbot />} />
        <Route path="/admin/users" element={<UserManagement />} />
        <Route path="/tally-status" element={<TallyStatus />} />

        <Route path="/reports" element={<ReportsIndex />} />
        {/* Financial Reports */}
        <Route path="/reports/profit-loss" element={<ProfitLoss />} />
        <Route path="/reports/group-summary" element={<GroupSummary />} />
        <Route path="/reports/balance-sheet" element={<BalanceSheet />} />
        <Route path="/reports/trial-balance" element={<TrialBalance />} />
        {/* Ledger Reports */}
        <Route path="/reports/ledger" element={<Ledger />} />
        <Route path="/reports/ledger/month" element={<LedgerMonthDetail />} />
        <Route path="/reports/voucher" element={<VoucherDetail />} />
        {/* Outstanding Reports */}
        <Route path="/reports/receivables" element={<Receivables />} />
        <Route path="/reports/payables" element={<Payables />} />
        <Route path="/reports/pending-invoices" element={<PendingInvoices />} />
        {/* Stock Reports */}
        <Route path="/reports/inventory" element={<Inventory />} />

        {LEGACY_REPORT_REDIRECTS.map(([from, to]) => (
          <Route key={from} path={from} element={<Navigate to={to} replace />} />
        ))}
      </Route>
    </Routes>
  )
}

export default App