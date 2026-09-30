import { useState } from 'react'

import { formatAmount } from './format'

// Pending bills by how long they are overdue, as one stacked bar with a
// legend. Buckets are ordered, so they share one hue that deepens with
// age (an ordinal ramp) rather than unrelated colours.
function AgeingBar({ buckets, label }) {
  const [active, setActive] = useState(null)

  const rows = (buckets || []).filter((bucket) => bucket.amount > 0)
  const total = rows.reduce((sum, bucket) => sum + bucket.amount, 0)

  if (!rows.length) return null

  return (
    <div className="db-ageing">
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

          return (
            <li
              key={bucket.key}
              className={`${bucket.amount > 0 ? '' : 'is-empty'}${active === bucket.key ? ' is-active' : ''}`}
            >
              <span className={`db-ageing-key db-age--${bucket.key}`} aria-hidden="true" />
              <span className="db-ageing-label">{bucket.label}</span>
              <span className="db-ageing-amount">
                {bucket.amount > 0 ? formatAmount(bucket.amount) : '—'}
              </span>
              {bucket.amount > 0 && (
                <span className="db-ageing-share">
                  {share}% · {bucket.count} {bucket.count === 1 ? 'bill' : 'bills'}
                </span>
              )}
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default AgeingBar
