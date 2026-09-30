import { useState } from 'react'
import { Outlet, Link, useLocation } from 'react-router'
import { Menu, Sparkles } from 'lucide-react'

import Sidebar from './Sidebar'
import { useMediaQuery } from '../../hooks/useMediaQuery'
import { getSelectedCompany, setSelectedCompany } from '../../api/client'

const SIDEBAR_STORAGE_KEY = 'tfi.sidebar.expanded'

// Collapsed is the default; the user's choice is remembered per browser.
function readSidebarExpanded() {
  try {
    return localStorage.getItem(SIDEBAR_STORAGE_KEY) === 'true'
  } catch {
    return false
  }
}

function writeSidebarExpanded(expanded) {
  try {
    localStorage.setItem(SIDEBAR_STORAGE_KEY, String(expanded))
  } catch {
    // Storage can be unavailable (private mode) - the toggle still works.
  }
}

// Real company names assigned to the user; the "*" wildcard is excluded.
function readUserCompanies() {
  try {
    const user = JSON.parse(sessionStorage.getItem('chat_user') || 'null')

    return Array.isArray(user?.companies)
      ? user.companies.filter((company) => company && company !== '*')
      : []
  } catch {
    return []
  }
}

// Keep a previously chosen company if it is still assigned, otherwise
// default to the first one. Stored before any page renders, so the
// first report requests already carry the company.
function initialCompany(companies) {
  const stored = getSelectedCompany()
  const company = companies.includes(stored) ? stored : companies[0] || null

  setSelectedCompany(company)

  return company
}

function Layout({ onLogout }) {
  const location = useLocation()
  const onChatPage = location.pathname === '/chatbot'

  const isMobile = useMediaQuery('(max-width: 900px)')
  const [expanded, setExpanded] = useState(readSidebarExpanded)
  const [mobileOpen, setMobileOpen] = useState(false)
  const [companies] = useState(readUserCompanies)
  const [company, setCompany] = useState(() => initialCompany(companies))

  function changeCompany(next) {
    setSelectedCompany(next)
    setCompany(next)
  }

  function toggleSidebar() {
    setExpanded((current) => {
      writeSidebarExpanded(!current)
      return !current
    })
  }

  // The mobile drawer always shows labels, whatever the desktop setting.
  const sidebarState = isMobile || expanded ? 'expanded' : 'collapsed'

  return (
    <div
      className="app-shell"
      data-sidebar={sidebarState}
      data-mobile-open={isMobile && mobileOpen ? 'true' : 'false'}
    >
      <Sidebar
        collapsed={sidebarState === 'collapsed'}
        isMobile={isMobile}
        onToggle={toggleSidebar}
        onNavigate={() => setMobileOpen(false)}
        onCloseMobile={() => setMobileOpen(false)}
        onLogout={onLogout}
        companies={companies}
        selectedCompany={company}
        onCompanyChange={changeCompany}
      />

      <div
        className="sidebar-backdrop"
        onClick={() => setMobileOpen(false)}
        aria-hidden="true"
      />

      <div className="app-main">
        <header className="topbar">
          <button
            type="button"
            className="sidebar-icon-button"
            onClick={() => setMobileOpen(true)}
            aria-label="Open navigation"
          >
            <Menu size={20} />
          </button>

          <span className="topbar-title">Tally Financial Intelligence</span>
        </header>

        <main className="app-content">
          <div className="content-inner">
            {/* Remount the page on company change so it refetches. */}
            <Outlet key={company || 'default'} context={{ onLogout }} />
          </div>
        </main>
      </div>

      {!onChatPage && (
        <Link
          to="/chatbot"
          className="chat-fab"
          aria-label="Open AI Assistant"
          title="AI Assistant"
        >
          <Sparkles size={22} />
        </Link>
      )}
    </div>
  )
}

export default Layout
