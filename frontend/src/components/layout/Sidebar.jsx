import { NavLink } from 'react-router'
import {
  BarChart3,
  Building2,
  LogOut,
  PanelLeftClose,
  PanelLeftOpen,
  X,
} from 'lucide-react'

import { NAV_SECTIONS } from './navConfig'


function getCurrentUser() {
  try {
    const storedUser =
      sessionStorage.getItem('chat_user')

    if (!storedUser) {
      return null
    }

    return JSON.parse(storedUser)
  } catch {
    return null
  }
}


function getInitial(username) {
  if (!username) {
    return 'U'
  }

  return username
    .trim()
    .charAt(0)
    .toUpperCase()
}


function formatRole(role) {
  return role
    .split('_')
    .map(
      (part) =>
        part.charAt(0).toUpperCase() +
        part.slice(1)
    )
    .join(' ')
}


function Sidebar({
  collapsed,
  isMobile,
  onToggle,
  onNavigate,
  onCloseMobile,
  onLogout,
  companies = [],
  selectedCompany,
  onCompanyChange,
}) {
  const user = getCurrentUser()

  const hasWildcard =
    Array.isArray(user?.companies) &&
    user.companies.includes('*')

  const companyLabel =
    selectedCompany ||
    (hasWildcard
      ? 'All companies'
      : 'No company')

  const canSwitchCompany =
    companies.length > 1 && !collapsed

  const roles = Array.isArray(user?.roles)
    ? user.roles
    : []

  const roleLabel = roles.length
    ? roles.map(formatRole).join(', ')
    : 'Authorized user'

  const canManageUsers =
    roles.includes('superadmin') ||
    roles.includes('admin')

  // Tooltips are only needed when labels are hidden.
  const tooltip = (label) =>
    collapsed ? label : undefined

  return (
    <aside
      className="sidebar"
      aria-label="Sidebar"
    >
      <div className="sidebar-brand">
        <div className="sidebar-brand-logo">
          <BarChart3 size={18} />
        </div>

        <div className="sidebar-brand-copy">
          <strong>Tally Financial</strong>
          <span>Intelligence</span>
        </div>

        {isMobile ? (
          <button
            type="button"
            className="sidebar-icon-button sidebar-close"
            onClick={onCloseMobile}
            aria-label="Close navigation"
          >
            <X size={18} />
          </button>
        ) : (
          <button
            type="button"
            className="sidebar-top-toggle"
            onClick={onToggle}
            aria-label={
              collapsed
                ? 'Expand sidebar'
                : 'Collapse sidebar'
            }
            aria-expanded={!collapsed}
            title={
              collapsed
                ? 'Expand sidebar'
                : 'Collapse sidebar'
            }
          >
            {collapsed ? (
              <PanelLeftOpen size={16} />
            ) : (
              <PanelLeftClose size={16} />
            )}
          </button>
        )}
      </div>

      <div
        className="sidebar-company"
        data-tooltip={tooltip(companyLabel)}
      >
        <Building2 size={16} />

        <div className="sidebar-company-copy">
          <span>Company</span>

          {canSwitchCompany ? (
            <select
              className="sidebar-company-select"
              value={selectedCompany || ''}
              onChange={(event) =>
                onCompanyChange?.(
                  event.target.value
                )
              }
              aria-label="Select company"
              title={companyLabel}
            >
              {companies.map((company) => (
                <option
                  key={company}
                  value={company}
                >
                  {company}
                </option>
              ))}
            </select>
          ) : (
            <strong title={companyLabel}>
              {companyLabel}
            </strong>
          )}
        </div>
      </div>

      <nav
        className="sidebar-nav"
        aria-label="Main navigation"
      >
        {NAV_SECTIONS.map((section) => (
          <div
            className="sidebar-section"
            key={section.label}
          >
            <span className="sidebar-section-label">
              {section.label}
            </span>

            {section.links
              .filter(
                (link) =>
                  link.to !== '/admin/users' ||
                  canManageUsers
              )
              .map((link) => {
                const Icon = link.icon

                return (
                  <NavLink
                    key={link.to}
                    to={link.to}
                    end={link.end}
                    onClick={onNavigate}
                    aria-label={
                      collapsed
                        ? link.label
                        : undefined
                    }
                    data-tooltip={tooltip(
                      link.label
                    )}
                    className={({
                      isActive,
                    }) =>
                      isActive
                        ? 'sidebar-link sidebar-link--active'
                        : 'sidebar-link'
                    }
                  >
                    <Icon
                      size={18}
                      strokeWidth={1.9}
                    />

                    <span className="sidebar-link-label">
                      {link.label}
                    </span>
                  </NavLink>
                )
              })}
          </div>
        ))}
      </nav>

      <div className="sidebar-footer">
        <div
          className="sidebar-user"
          data-tooltip={tooltip(
            user?.username || 'User'
          )}
        >
          <div className="sidebar-avatar">
            {getInitial(user?.username)}
          </div>

          <div className="sidebar-user-info">
            <strong title={user?.username}>
              {user?.username || 'User'}
            </strong>

            <span>{roleLabel}</span>
          </div>
        </div>

        {!collapsed ? (
          <button
            type="button"
            className="sidebar-industrial-logout"
            onClick={onLogout}
            aria-label="Sign out"
            title="Sign out of account"
          >
            <LogOut size={16} />
            <span>Sign Out</span>
          </button>
        ) : (
          <button
            type="button"
            className="sidebar-toggle sidebar-logout-collapsed"
            onClick={onLogout}
            aria-label="Sign out"
            data-tooltip="Sign out"
          >
            <LogOut size={18} />
          </button>
        )}
      </div>
    </aside>
  )
}


export default Sidebar