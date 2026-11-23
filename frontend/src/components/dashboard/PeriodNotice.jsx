import { Info, Calendar, ArrowRight } from 'lucide-react'

import { getPresetDateRange } from '../../utils/dashboardDateFilter'
import { formatDay, isNumber } from './format'

function hasNoEntries(data) {
  return (
    data.period_verified &&
    !isNumber(data.total_sales) &&
    !isNumber(data.total_purchases) &&
    !data.net_profit &&
    !data.net_loss
  )
}

/**
 * Enterprise Period Notice
 * Informs the user when no transactions exist for the selected dates in Tally,
 * and provides a clear one-click button to view the active financial records.
 */
function PeriodNotice({ data, filter, onFilterChange }) {
  const lastFy = getPresetDateRange('lfy')
  const offerLastFy = filter.selectedPreset !== 'lfy'

  if (data.period_verified === false) {
    const tally = data.tally_report_period || {}
    const hasTallyPeriod = Boolean(tally.from_date && tally.to_date)
    const tallyUsable =
      hasTallyPeriod &&
      tally.to_date > tally.from_date &&
      (tally.from_date !== filter.fromDate || tally.to_date !== filter.toDate)

    return (
      <div className="db-alert db-alert--info" role="status">
        <Info size={16} className="db-alert-icon" aria-hidden="true" />
        <div className="db-alert-content">
          <p className="db-alert-title">
            No Transactions Found for Period ({formatDay(filter.fromDate)} – {formatDay(filter.toDate)})
          </p>
          <p className="db-alert-desc">
            {hasTallyPeriod
              ? `Tally Prime indicates active transaction records exist for ${formatDay(tally.from_date)} – ${formatDay(tally.to_date)}.`
              : 'Try selecting a different fiscal period to view financial reports.'}
          </p>
        </div>
        {tallyUsable && (
          <button
            type="button"
            className="db-alert-btn"
            onClick={() => onFilterChange({
              fromDate: tally.from_date,
              toDate: tally.to_date,
              selectedPreset: null,
            })}
          >
            <span>Switch to Active Period ({formatDay(tally.from_date)} – {formatDay(tally.to_date)})</span>
            <ArrowRight size={14} aria-hidden="true" />
          </button>
        )}
      </div>
    )
  }

  if (hasNoEntries(data)) {
    return (
      <div className="db-alert db-alert--info" role="status">
        <Info size={16} className="db-alert-icon" aria-hidden="true" />
        <div className="db-alert-content">
          <p className="db-alert-title">No Vouchers Recorded in Selected Period</p>
          <p className="db-alert-desc">
            Balance sheet and position values below reflect balances as on {formatDay(filter.toDate)}.
          </p>
        </div>
        {offerLastFy && (
          <button
            type="button"
            className="db-alert-btn"
            onClick={() => onFilterChange('lfy')}
          >
            <Calendar size={13} aria-hidden="true" />
            <span>Show FY {lastFy.fromDate.slice(0, 4)}-{lastFy.toDate.slice(2, 4)}</span>
          </button>
        )}
      </div>
    )
  }

  return null
}

export default PeriodNotice
