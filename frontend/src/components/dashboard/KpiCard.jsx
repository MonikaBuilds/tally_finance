import { Link } from 'react-router'
import { ArrowUpRight, TrendingDown, TrendingUp } from 'lucide-react'

import { isNumber } from './format'

// One headline financial metric card.
// `source` is the backend's metric_sources entry: it names the Tally report behind
// the value and, when Tally could not provide one, why - shown clearly instead of blank.
// `delta`, when given, compares with previous period:
// { text: '▲ 12% vs FY 2024-25', tone: 'up' | 'down' | 'flat' }.
function KpiCard({
  label,
  icon: Icon,
  tone,
  value,
  display,
  hint,
  source,
  to,
  loading,
  offline,
  delta,
  tag,
}) {
  const available = isNumber(value)

  let body
  if (available) {
    body = <span className="db-kpi-value">{display}</span>
  } else if (loading) {
    body = <span className="db-skeleton db-skeleton--value" aria-label="Loading metric" />
  } else if (source?.status === 'none') {
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

  const deltaIcon = delta?.tone === 'up'
    ? <TrendingUp size={12} aria-hidden="true" />
    : delta?.tone === 'down'
      ? <TrendingDown size={12} aria-hidden="true" />
      : null

  const content = (
    <div className="db-kpi-inner">
      <div className="db-kpi-top">
        <div className="db-kpi-tag-row">
          {tag && <span className="db-kpi-tag">{tag}</span>}
          {to && (
            <span className="db-kpi-action" aria-hidden="true">
              <ArrowUpRight size={13} />
            </span>
          )}
        </div>

        <div className="db-kpi-head">
          <span className={`db-kpi-icon db-tone--${tone}`} aria-hidden="true">
            <Icon size={16} />
          </span>
          <span className="db-kpi-label">{label}</span>
        </div>
      </div>

      <div className="db-kpi-body">
        {body}
        {available && delta && (
          <div className={`db-delta db-delta--${delta.tone}`}>
            {deltaIcon}
            <span>{delta.text}</span>
          </div>
        )}
      </div>

      <div className="db-kpi-foot">
        <span className="db-kpi-hint" title={reason || hint}>
          {reason || hint}
        </span>
        {source?.report && (
          <span className="db-kpi-source-chip" title={sourceNote}>
            {source.report}
          </span>
        )}
      </div>
    </div>
  )

  if (to) {
    return (
      <Link to={to} className={`db-kpi db-kpi--link db-kpi-tone--${tone}`} title={sourceNote}>
        <span className="db-kpi-accent-bar" aria-hidden="true" />
        {content}
      </Link>
    )
  }

  return (
    <div className={`db-kpi db-kpi-tone--${tone}`} title={sourceNote}>
      <span className="db-kpi-accent-bar" aria-hidden="true" />
      {content}
    </div>
  )
}

export default KpiCard
