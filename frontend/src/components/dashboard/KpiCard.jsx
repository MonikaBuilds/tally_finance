import { Link } from 'react-router'
import { ChevronRight } from 'lucide-react'

import { isNumber } from './format'

// One headline figure. `source` is the backend's metric_sources entry:
// it names the Tally report behind the value and, when Tally could not
// provide one, why - which is shown instead of an unexplained blank.
// `delta`, when given, compares with the previous period:
// { text: '▲ 12% vs FY 2024-25', tone: 'up' | 'down' | 'flat' }.
function KpiCard({ label, icon: Icon, tone, value, display, hint, source, to, loading, offline, delta }) {
  const available = isNumber(value)

  let body
  if (available) {
    body = <span className="db-kpi-value">{display}</span>
  } else if (loading) {
    body = <span className="db-skeleton db-skeleton--value" aria-label="Loading" />
  } else if (source?.status === 'none') {
    // Tally confirmed the period and has no such entries.
    body = <span className="db-kpi-value db-kpi-value--missing">Nil</span>
  } else {
    body = <span className="db-kpi-value db-kpi-value--missing">Unavailable</span>
  }

  const reason = !available && !loading
    ? (offline ? 'Tally could not be reached.' : source?.message)
    : null

  const sourceNote = source?.report
    ? `From Tally: ${source.report}${source.label ? ` — ${source.label}` : ''}`
    : undefined

  const content = (
    <>
      <div className="db-kpi-head">
        <span className={`db-kpi-icon db-tone--${tone}`} aria-hidden="true">
          <Icon size={16} />
        </span>
        <span className="db-kpi-label">{label}</span>
        {to && <ChevronRight size={14} className="db-kpi-chevron" aria-hidden="true" />}
      </div>
      {body}
      {available && delta && (
        <span className={`db-delta db-delta--${delta.tone}`}>{delta.text}</span>
      )}
      <span className="db-kpi-hint">{reason || hint}</span>
    </>
  )

  if (to) {
    return (
      <Link to={to} className="db-kpi db-kpi--link" title={sourceNote}>
        {content}
      </Link>
    )
  }

  return (
    <div className="db-kpi" title={sourceNote}>
      {content}
    </div>
  )
}

export default KpiCard
