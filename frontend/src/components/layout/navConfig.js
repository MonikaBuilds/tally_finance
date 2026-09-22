import {
  Activity,
  ArrowDownLeft,
  ArrowUpRight,
  BookOpen,
  FileClock,
  LayoutDashboard,
  ListChecks,
  Package,
  Scale,
  Sparkles,
  TrendingUp,
  Users,
} from 'lucide-react'

import { ALL_REPORTS } from '../../reportsConfig'

// One icon per report route. Keyed by path so reportsConfig.js stays the
// single source of truth for which reports exist and where they live.
export const REPORT_ICONS = {
  '/reports/profit-loss': TrendingUp,
  '/reports/balance-sheet': Scale,
  '/reports/trial-balance': ListChecks,
  '/reports/ledger': BookOpen,
  '/reports/receivables': ArrowDownLeft,
  '/reports/payables': ArrowUpRight,
  '/reports/pending-invoices': FileClock,
  '/reports/inventory': Package,
}

export const NAV_SECTIONS = [
  {
    label: 'Overview',
    links: [
      { to: '/', label: 'Dashboard', icon: LayoutDashboard, end: true },
      { to: '/chatbot', label: 'AI Assistant', icon: Sparkles },
    ],
  },
  {
    label: 'Reports',
    links: ALL_REPORTS.map((report) => ({
      to: report.to,
      label: report.label,
      icon: REPORT_ICONS[report.to] || BookOpen,
    })),
  },
  {
    label: 'System',
    links: [
      { to: '/tally-status', label: 'Tally Status', icon: Activity },
      { to: '/admin/users', label: 'User Management', icon: Users },
    ],
  },
]
