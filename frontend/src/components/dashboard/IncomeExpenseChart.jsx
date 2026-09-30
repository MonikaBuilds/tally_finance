import { useState } from 'react'

import { formatAmount, formatCompact, isNumber } from './format'

const SERIES = [
  { key: 'income', label: 'Sales', className: 'db-bar--sales' },
  { key: 'expense', label: 'Purchases', className: 'db-bar--purchases' },
]

// Round the axis to clean steps: 1, 2, 2.5 or 5 × a power of ten.
function niceTicks(min, max, count = 4) {
  const span = max - min || 1
  const rough = span / count
  const power = 10 ** Math.floor(Math.log10(rough))
  const step = [1, 2, 2.5, 5, 10].map((m) => m * power).find((s) => s >= rough)

  const low = Math.floor(min / step) * step
  const high = Math.ceil(max / step) * step
  const ticks = []

  for (let tick = low; tick <= high + step / 2; tick += step) {
    ticks.push(Math.round(tick))
  }

  return ticks
}

// Why a month has no bars, shown in its tooltip and screen-reader text.
const MISSING_REASON = {
  unverified: 'Tally used different dates for this month',
  no_entries: 'No sales or purchase entries',
  unavailable: 'Could not be read from Tally',
}

function missingReason(point) {
  return point.status === 'available' ? null : MISSING_REASON[point.status] || MISSING_REASON.unavailable
}

// "Apr 2025" -> ["Apr", "'25"]
function monthParts(label) {
  const [month, year] = (label || '').split(' ')
  return [month, year ? `’${year.slice(-2)}` : '']
}

function IncomeExpenseChart({ points }) {
  const [active, setActive] = useState(null)

  const values = points.flatMap((point) =>
    SERIES.map((series) => point[series.key]).filter(isNumber).map(Number)
  )

  const ticks = niceTicks(Math.min(0, ...values), Math.max(0, ...values))
  const low = ticks[0]
  const high = ticks[ticks.length - 1]
  const span = high - low || 1

  // Vertical position, as % from the bottom of the plot.
  const y = (value) => ((value - low) / span) * 100
  const zero = y(0)

  const activePoint = active === null ? null : points[active]

  // Centre the tooltip over its month, but keep it inside the plot at
  // the edges: anchor it to the group's left or right edge there.
  let tooltipLeft = ((active + 0.5) / points.length) * 100
  let tooltipAlign = ''
  if (tooltipLeft < 20) {
    tooltipLeft = (active / points.length) * 100
    tooltipAlign = ' db-tooltip--start'
  } else if (tooltipLeft > 80) {
    tooltipLeft = ((active + 1) / points.length) * 100
    tooltipAlign = ' db-tooltip--end'
  }

  return (
    <div className="db-chart">
      <div className="db-legend" aria-hidden="true">
        {SERIES.map((series) => (
          <span key={series.key} className="db-legend-item">
            <span className={`db-legend-swatch ${series.className}`} />
            {series.label}
          </span>
        ))}
      </div>

      <div className="db-chart-body">
        <div className="db-chart-axis" aria-hidden="true">
          {ticks.map((tick) => (
            <span key={tick} style={{ bottom: `${y(tick)}%` }}>
              {formatCompact(tick)}
            </span>
          ))}
        </div>

        <div className="db-chart-plot" onPointerLeave={() => setActive(null)}>
          {ticks.map((tick) => (
            <span
              key={tick}
              className={`db-gridline${tick === 0 ? ' db-gridline--zero' : ''}`}
              style={{ bottom: `${y(tick)}%` }}
              aria-hidden="true"
            />
          ))}

          <div className="db-chart-columns">
            {points.map((point, index) => {
              const [month, year] = monthParts(point.month)
              const reason = missingReason(point)
              const description = reason
                ? `${point.month}: ${reason}`
                : `${point.month}: ${SERIES.map(
                  (series) => `${series.label} ${formatAmount(point[series.key], { missing: 'none' })}`
                ).join(', ')}`

              return (
                <div
                  key={point.from_date}
                  className={`db-chart-group${active === index ? ' is-active' : ''}`}
                  tabIndex={0}
                  aria-label={description}
                  onPointerEnter={() => setActive(index)}
                  onFocus={() => setActive(index)}
                  onBlur={() => setActive(null)}
                >
                  {point.status === 'unverified' && (
                    <span className="db-chart-gap" style={{ bottom: `${zero}%` }} aria-hidden="true" />
                  )}
                  <div className="db-chart-bars">
                    {SERIES.map((series) => {
                      const value = point[series.key]
                      if (!isNumber(value)) {
                        return <span key={series.key} className="db-bar db-bar--empty" />
                      }

                      const top = Math.max(y(Number(value)), zero)
                      const bottom = Math.min(y(Number(value)), zero)

                      return (
                        <span
                          key={series.key}
                          className={`db-bar ${series.className}${Number(value) < 0 ? ' db-bar--negative' : ''}`}
                          style={{ bottom: `${bottom}%`, height: `${Math.max(top - bottom, 0.6)}%` }}
                        />
                      )
                    })}
                  </div>
                  <span className="db-chart-x" aria-hidden="true">
                    {month}
                    <small>{year}</small>
                  </span>
                </div>
              )
            })}
          </div>

          {activePoint && (
            <div
              className={`db-tooltip${tooltipAlign}`}
              style={{ left: `${tooltipLeft}%` }}
              role="presentation"
            >
              <span className="db-tooltip-title">{activePoint.month}</span>
              {missingReason(activePoint) ? (
                <span className="db-tooltip-note">{missingReason(activePoint)}</span>
              ) : SERIES.map((series) => (
                <span key={series.key} className="db-tooltip-row">
                  <span className={`db-tooltip-key ${series.className}`} />
                  <strong>{formatAmount(activePoint[series.key], { missing: '—' })}</strong>
                  <span>{series.label}</span>
                </span>
              ))}
            </div>
          )}
        </div>
      </div>

      <table className="visually-hidden">
        <caption>Sales and purchases by month</caption>
        <thead>
          <tr>
            <th scope="col">Month</th>
            {SERIES.map((series) => <th key={series.key} scope="col">{series.label}</th>)}
          </tr>
        </thead>
        <tbody>
          {points.map((point) => (
            <tr key={point.from_date}>
              <th scope="row">{point.month}</th>
              {missingReason(point)
                ? <td colSpan={SERIES.length}>{missingReason(point)}</td>
                : SERIES.map((series) => (
                  <td key={series.key}>{formatAmount(point[series.key], { missing: '—' })}</td>
                ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

export default IncomeExpenseChart
