import { Link } from 'react-router'
import { ArrowUpRight } from 'lucide-react'

// Card frame shared by every dashboard financial table and chart.
function Panel({
  title,
  subtitle,
  badge,
  icon: Icon,
  to,
  linkLabel = 'View report',
  loading,
  empty,
  children,
  className,
}) {
  let body = children

  if (empty) {
    body = loading ? (
      <div className="db-panel-skeleton" aria-label="Loading financial data">
        <span className="db-skeleton" />
        <span className="db-skeleton" />
        <span className="db-skeleton" />
      </div>
    ) : (
      <p className="db-empty">{empty}</p>
    )
  }

  return (
    <section className={`db-panel${className ? ` ${className}` : ''}`}>
      <header className="db-panel-head">
        <div className="db-panel-title-group">
          <div className="db-panel-meta-row">
            {badge && <span className="db-panel-badge">{badge}</span>}
            {Icon && <Icon size={14} className="db-panel-header-icon" aria-hidden="true" />}
            <h2>{title}</h2>
          </div>
          {subtitle && <p className="db-panel-subtitle">{subtitle}</p>}
        </div>

        {to && (
          <Link to={to} className="db-panel-link">
            <span>{linkLabel}</span>
            <ArrowUpRight size={14} aria-hidden="true" />
          </Link>
        )}
      </header>

      <div className="db-panel-body">{body}</div>
    </section>
  )
}

export default Panel
