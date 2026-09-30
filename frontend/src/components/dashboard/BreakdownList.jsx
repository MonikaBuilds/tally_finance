import { formatAmount, isNumber } from './format'

// Part-to-whole for the few P&L lines behind a total (2-3 rows), drawn
// as share bars rather than a donut: short lists read better as bars.
// Tally reports expense lines as negative (debit); the size of each
// line is what is compared here, and the label says which side it is.
function BreakdownList({ items, tone, totalLabel }) {
  const rows = (items || [])
    .filter((item) => isNumber(item.value))
    .map((item) => ({ ...item, size: Math.abs(Number(item.value)) }))

  const total = rows.reduce((sum, row) => sum + row.size, 0)

  return (
    <div className="db-breakdown">
      <div className="db-breakdown-total">
        <strong>{formatAmount(total)}</strong>
        <span>{totalLabel}</span>
      </div>

      <ul className="db-breakdown-list">
        {rows.map((row) => {
          const share = total > 0 ? (row.size / total) * 100 : 0

          return (
            <li key={row.label}>
              <div className="db-breakdown-row">
                <span className="db-breakdown-label">{row.label}</span>
                <span className="db-breakdown-value">{formatAmount(row.size)}</span>
                <span className="db-breakdown-share">{share.toFixed(share < 10 ? 1 : 0)}%</span>
              </div>
              <span className="db-meter" aria-hidden="true">
                <span className={`db-meter-fill db-meter-fill--${tone}`} style={{ width: `${share}%` }} />
              </span>
            </li>
          )
        })}
      </ul>
    </div>
  )
}

export default BreakdownList
