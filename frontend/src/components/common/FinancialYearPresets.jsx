import { financialYearRange } from '../../utils/format'

/*
 * "This FY" / "Last FY" quick-range buttons shared by the report pages.
 *
 * The Indian financial year (1 Apr - 31 Mar) is worked out from today's
 * date, nothing is hardcoded. Clicking a button hands the full-year
 * { from, to } (ISO dates) to `onSelect`; the page then fetches that
 * period from Tally exactly as if the user had typed the dates.
 *
 * `from` / `to` are the dates currently applied, only used to mark the
 * button that matches them.
 */
export function financialYearPresets(refDate = new Date()) {
  const thisFy = financialYearRange(0, refDate)
  const lastFy = financialYearRange(-1, refDate)

  return [
    { key: 'this-fy', label: 'This FY', title: thisFy.label, from: thisFy.from, to: thisFy.to },
    { key: 'last-fy', label: 'Last FY', title: lastFy.label, from: lastFy.from, to: lastFy.to },
  ]
}

function FinancialYearPresets({ from, to, onSelect, className = 'form-field form-field--quick-range' }) {
  const presets = financialYearPresets()

  return (
    <div className={className} role="group" aria-label="Financial year">
      {presets.map((preset) => {
        const active = from === preset.from && to === preset.to

        return (
          <button
            key={preset.key}
            type="button"
            className={active ? 'btn' : 'btn btn-secondary'}
            title={`${preset.title}: ${preset.from} to ${preset.to}`}
            aria-pressed={active}
            onClick={() => onSelect({ from: preset.from, to: preset.to })}
          >
            {preset.label}
          </button>
        )
      })}
    </div>
  )
}

export default FinancialYearPresets
