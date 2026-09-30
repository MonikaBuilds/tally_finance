import { CalendarX2, Info } from 'lucide-react'

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

// Explains an empty or unusable period and offers one that works:
// - Tally answered with different dates than the selected ones, so the
//   P&L figures were withheld (see verified_period on the backend);
// - or Tally confirmed the period but it has no entries at all.
function PeriodNotice({ data, filter, onFilterChange }) {
  const lastFy = getPresetDateRange('lfy')
  const offerLastFy = filter.selectedPreset !== 'lfy'

  if (data.period_verified === false) {
    const tally = data.tally_report_period || {}
    const tallyUsable =
      tally.from_date &&
      tally.to_date &&
      tally.to_date > tally.from_date &&
      (tally.from_date !== filter.fromDate || tally.to_date !== filter.toDate)

    return (
      <div className="db-alert db-alert--info" role="status">
        <CalendarX2 size={16} aria-hidden="true" />
        <span>
          <strong>Profit &amp; loss figures are hidden for these dates.</strong>{' '}
          {tally.from_date
            ? `Tally answered for ${formatDay(tally.from_date)} – ${formatDay(tally.to_date)} instead. `
            : 'Tally did not confirm which dates it used. '}
          This happens when Tally cannot use the selected dates; TallyPrime
          Educational mode, for example, only accepts the 1st, 2nd and 31st of a month.
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
        {offerLastFy && (
          <button type="button" onClick={() => onFilterChange('lfy')}>
            Last FY
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
