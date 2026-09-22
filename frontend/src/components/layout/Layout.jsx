import { useState } from 'react'
import { Outlet, Link, useLocation } from 'react-router'
import { Menu, Sparkles } from 'lucide-react'

import Sidebar from './Sidebar'
import { useMediaQuery } from '../../hooks/useMediaQuery'

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

function Layout({ onLogout }) {
  const location = useLocation()
  const onChatPage = location.pathname === '/chatbot'

  const isMobile = useMediaQuery('(max-width: 900px)')
  const [expanded, setExpanded] = useState(readSidebarExpanded)
  const [mobileOpen, setMobileOpen] = useState(false)

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
            <Outlet />
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
