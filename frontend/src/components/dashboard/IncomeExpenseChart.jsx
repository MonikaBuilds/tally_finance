import { useState } from 'react'

import { formatAmount, formatCompact, isNumber } from './format'

const SERIES = [
  { key: 'income', label: 'Gross Sales / Inflow', className: 'db-bar--sales' },
  { key: 'expense', label: 'Purchases / Outflow', className: 'db-bar--purchases' },
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

const MISSING_REASON = {
  unverified: 'Tally used different dates for this month',
  no_entries: 'No sales or purchase entries recorded',
  unavailable: 'Could not be read from Tally',
}

function missingReason(point) {
  return point.status === 'available' ? null : MISSING_REASON[point.status] || MISSING_REASON.unavailable
}

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

  const y = (value) => ((value - low) / span) * 100
  const zero = y(0)

  const activePoint = active === null ? null : points[active]

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
      <div className="db-chart-meta">
        <div className="db-legend" aria-hidden="true">
          {SERIES.map((series) => (
            <span key={series.key} className="db-legend-item">
              <span className={`db-legend-swatch ${series.className}`} />
              {series.label}
            </span>
          ))}
          <span className="db-legend-item db-legend-item--spread">
            <span className="db-legend-swatch db-swatch--spread" />
            Net Operating Spread
          </span>
        </div>
        <span className="db-chart-unit">Amounts in INR (₹)</span>
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
            <div
              key={tick}
              className={`db-gridline${tick === 0 ? ' db-gridline--zero' : ''}`}
              style={{ bottom: `${y(tick)}%` }}
              aria-hidden="true"
            >
              {tick === 0 && <span className="db-zero-tag">₹0 Ledger Base</span>}
            </div>
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

              const incomeVal = isNumber(point.income) ? Number(point.income) : null
              const expenseVal = isNumber(point.expense) ? Number(point.expense) : null
              const netMargin = incomeVal !== null && expenseVal !== null ? incomeVal - expenseVal : null

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
                          style={{ bottom: `${bottom}%`, height: `${Math.max(top - bottom, 0.8)}%` }}
                        />
                      )
                    })}
                  </div>

                  <span className="db-chart-x" aria-hidden="true">
                    <strong>{month}</strong>
                    <small>{year}</small>
                  </span>

                  {active === index && (
                    <div className={`db-tooltip${tooltipAlign}`} role="tooltip">
                      <div className="db-tooltip-header">
                        <span className="db-tooltip-title">{point.month}</span>
                        <span className="db-tooltip-badge">Monthly Statement</span>
                      </div>

                      {reason ? (
                        <span className="db-tooltip-note">{reason}</span>
                      ) : (
                        <div className="db-tooltip-grid">
                          {SERIES.map((series) => (
                            <div key={series.key} className="db-tooltip-row">
                              <span className="db-tooltip-label-wrap">
                                <span className={`db-tooltip-key ${series.className}`} />
                                <span>{series.label}</span>
                              </span>
                              <strong>{formatAmount(point[series.key], { missing: 'none' })}</strong>
                            </div>
                          ))}

                          {netMargin !== null && (
                            <div className="db-tooltip-row db-tooltip-row--net">
                              <span className="db-tooltip-label-wrap">
                                <span className="db-tooltip-key db-tooltip-key--net" />
                                <span>Net Operating Spread</span>
                              </span>
                              <strong className={netMargin >= 0 ? 'db-tone--up' : 'db-tone--down'}>
                                {netMargin >= 0 ? '+' : ''}{formatAmount(netMargin)}
                              </strong>
                            </div>
                          )}
                        </div>
                      )}
                    </div>
                  )}
                </div>
              )
            })}
          </div>
        </div>
      </div>
    </div>
  )
}

export default IncomeExpenseChart
