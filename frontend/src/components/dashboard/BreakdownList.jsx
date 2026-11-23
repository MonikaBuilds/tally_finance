import { formatAmount, isNumber } from './format'
import { PieChart } from 'lucide-react'

// Part-to-whole for the few P&L lines behind a total (2-3 rows), drawn
// as financial schedule share meters.
function BreakdownList({ items, tone, totalLabel }) {
  const rows = (items || [])
    .filter((item) => isNumber(item.value))
    .map((item) => ({ ...item, size: Math.abs(Number(item.value)) }))

  const total = rows.reduce((sum, row) => sum + row.size, 0)

  return (
    <div className="db-breakdown">
      <div className="db-breakdown-total">
        <div className="db-breakdown-total-top">
          <PieChart size={14} className="db-breakdown-icon" aria-hidden="true" />
          <span className="db-breakdown-caption">{totalLabel}</span>
        </div>
        <strong className="db-breakdown-sum">{formatAmount(total)}</strong>
      </div>

      <ul className="db-breakdown-list">
        {rows.map((row) => {
          const share = total > 0 ? (row.size / total) * 100 : 0
          const shareFormatted = share.toFixed(share < 10 ? 1 : 0)

          return (
            <li key={row.label} className="db-breakdown-item">
              <div className="db-breakdown-row">
                <div className="db-breakdown-info">
                  <span className="db-breakdown-dot" aria-hidden="true" />
                  <span className="db-breakdown-label" title={row.label}>{row.label}</span>
                </div>
                <div className="db-breakdown-values">
                  <span className="db-breakdown-value">{formatAmount(row.size)}</span>
                  <span className="db-breakdown-share-badge">{shareFormatted}%</span>
                </div>
              </div>

              <div className="db-meter" aria-hidden="true">
                <div
                  className={`db-meter-fill db-meter-fill--${tone}`}
                  style={{ width: `${share}%` }}
                />
              </div>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default BreakdownList
