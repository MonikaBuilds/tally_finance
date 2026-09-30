import { Link } from 'react-router'

// Card frame shared by every dashboard table and chart. While loading
// without any earlier data it shows a skeleton; with nothing to show it
// explains why instead of rendering an empty frame.
function Panel({ title, subtitle, to, linkLabel = 'View report', loading, empty, children, className }) {
  let body = children

  if (empty) {
    body = loading
      ? (
        <div className="db-panel-skeleton" aria-label="Loading">
          <span className="db-skeleton" />
          <span className="db-skeleton" />
          <span className="db-skeleton" />
        </div>
      )
      : <p className="db-empty">{empty}</p>
  }

  return (
    <section className={`db-panel${className ? ` ${className}` : ''}`}>
      <header className="db-panel-head">
        <div>
          <h2>{title}</h2>
          {subtitle && <p>{subtitle}</p>}
        </div>
        {to && (
          <Link to={to} className="db-panel-link">
            {linkLabel}
          </Link>
        )}
      </header>
      {body}
    </section>
  )
}

export default Panel
