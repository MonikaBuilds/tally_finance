import { useState } from 'react'
import { ShieldAlert, Layers } from 'lucide-react'

import { formatAmount } from './format'

// Pending bills by how long they are overdue, as one stacked bar with a
// legend. Buckets are ordered, so they share a visual aging ramp from safe to critical.
function AgeingBar({ buckets, label }) {
  const [active, setActive] = useState(null)

  const rows = (buckets || []).filter((bucket) => bucket.amount > 0)
  const total = rows.reduce((sum, bucket) => sum + bucket.amount, 0)
  const totalBills = (buckets || []).reduce((sum, b) => sum + (b.count || 0), 0)

  if (!rows.length) return null

  return (
    <div className="db-ageing">
      <div className="db-ageing-head">
        <div className="db-ageing-title-wrap">
          <Layers size={13} className="db-ageing-icon" aria-hidden="true" />
          <span className="db-ageing-head-label">{label} Risk Spectrum</span>
        </div>
        <div className="db-ageing-total-badge">
          <span>Total: <strong>{formatAmount(total)}</strong></span>
          <span className="db-ageing-bill-count">({totalBills} total bills)</span>
        </div>
      </div>

      <div
        className="db-ageing-bar"
        role="img"
        aria-label={`${label} by age: ${rows
          .map((bucket) => `${bucket.label} ${formatAmount(bucket.amount)}`)
          .join(', ')}`}
        onPointerLeave={() => setActive(null)}
      >
        {rows.map((bucket) => (
          <span
            key={bucket.key}
            className={`db-ageing-segment db-age--${bucket.key}${active === bucket.key ? ' is-active' : ''}`}
            style={{ flexGrow: bucket.amount }}
            onPointerEnter={() => setActive(bucket.key)}
            title={`${bucket.label}: ${formatAmount(bucket.amount)}`}
          />
        ))}
      </div>

      <ul className="db-ageing-legend">
        {(buckets || []).map((bucket) => {
          const share = total > 0 ? Math.round((bucket.amount / total) * 100) : 0
          const hasAmount = bucket.amount > 0

          return (
            <li
              key={bucket.key}
              className={`db-ageing-card ${hasAmount ? 'has-data' : 'is-empty'}${active === bucket.key ? ' is-active' : ''}`}
              onPointerEnter={() => hasAmount && setActive(bucket.key)}
              onPointerLeave={() => setActive(null)}
            >
              <div className="db-ageing-card-top">
                <span className={`db-ageing-key db-age--${bucket.key}`} aria-hidden="true" />
                <span className="db-ageing-label" title={bucket.label}>{bucket.label}</span>
              </div>

              <span className="db-ageing-amount">
                {hasAmount ? formatAmount(bucket.amount) : 'Nil'}
              </span>

              {hasAmount ? (
                <div className="db-ageing-meta">
                  <span className="db-ageing-share-pill">{share}%</span>
                  <span className="db-ageing-count-pill">
                    {bucket.count} {bucket.count === 1 ? 'bill' : 'bills'}
                  </span>
                </div>
              ) : (
                <span className="db-ageing-empty-note">No outstanding</span>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default AgeingBar
