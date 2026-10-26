import { Info } from 'lucide-react'

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
        <Info size={16} aria-hidden="true" />
        <span>
          <strong>
            No transactions in Tally for {formatDay(filter.fromDate)} – {formatDay(filter.toDate)}.
          </strong>{' '}
          {hasTallyPeriod ? `Company records are active for ${formatDay(tally.from_date)} – ${formatDay(tally.to_date)}.` : ''}
        </span>
        {tallyUsable && (
          <button
            type="button"
            onClick={() => onFilterChange({
              fromDate: tally.from_date,
              toDate: tally.to_date,
              selectedPreset: null,
            })}
          >
            Show {formatDay(tally.from_date)} – {formatDay(tally.to_date)}
          </button>
        )}
      </div>
    )
  }

  if (hasNoEntries(data)) {
    return (
      <div className="db-alert db-alert--info" role="status">
        <Info size={16} aria-hidden="true" />
        <span>
          <strong>No entries in Tally for this period.</strong> Balances
          below are as on {formatDay(filter.toDate)}.
        </span>
        {offerLastFy && (
          <button type="button" onClick={() => onFilterChange('lfy')}>
            Show FY {lastFy.fromDate.slice(0, 4)}-{lastFy.toDate.slice(2, 4)}
          </button>
        )}
      </div>
    )
  }

  return null
}

export default PeriodNotice
