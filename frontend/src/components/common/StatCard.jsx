import { formatCurrency, formatNumber } from '../../utils/format'

function StatCard({ label, value, tone = 'default', format = 'currency', icon: Icon }) {
  const displayValue = format === 'number' ? formatNumber(value) : formatCurrency(value)

  return (
    <div className={`stat-card stat-card--${tone}`}>
      <div className="stat-card-top">
        <span className="stat-card-label">{label}</span>
        {Icon && (
          <span className="stat-card-icon">
            <Icon size={16} />
          </span>
        )}
      </div>
      <span className="stat-card-value">{displayValue}</span>
    </div>
  )
}

export default StatCard
