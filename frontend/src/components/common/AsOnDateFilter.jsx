import { useState } from 'react'
import { AlertCircle } from 'lucide-react'

import Card from '../common/Card'
import FinancialYearPresets from '../common/FinancialYearPresets'

/*
 * "As on" date filter shared by Receivables and Payables.
 *
 * Tally's Bills Receivable / Bills Payable are point-in-time reports: a
 * single date decides which bills are still open, their amounts, and the
 * overdue days shown against each one. A period (From - To) is therefore
 * meaningless here - Tally ignores SVFROMDATE on these reports - so this
 * control offers one date instead of two.
 *
 * The chosen date lives in the page URL (?as_on=YYYY-MM-DD), exactly the
 * way the other report pages keep their period in the URL, so the view is
 * linkable, survives a reload, and the export buttons can reuse it.
 */
function AsOnDateFilter({ asOn, onApply, onReset, idPrefix = 'as-on', showFyPresets = false }) {
  const [draft, setDraft] = useState(null)
  const [error, setError] = useState(null)

  const inputValue = draft ?? asOn ?? ''

  function applyDate(event) {
    event.preventDefault()

    if (!inputValue) {
      setError('Select a date.')
      return
    }

    setError(null)
    setDraft(null)
    onApply(inputValue)
  }

  function reset() {
    setError(null)
    setDraft(null)
    onReset()
  }

  return (
    <Card title="As on date">
      <form className="ledger-filters" onSubmit={applyDate}>
        <div className="form-field form-field--date">
          <label htmlFor={`${idPrefix}-date`}>As on</label>
          <input
            id={`${idPrefix}-date`}
            type="date"
            value={inputValue}
            onChange={(event) => setDraft(event.target.value)}
          />
        </div>

        <button type="submit" className="btn">
          Apply
        </button>

        {showFyPresets && (
          <FinancialYearPresets
            from={asOn}
            to={asOn}
            onSelect={({ to }) => {
              setError(null)
              setDraft(null)
              onApply(to)
            }}
          />
        )}

        {asOn && (
          <button type="button" className="btn btn-secondary" onClick={reset}>
            Tally&apos;s own date
          </button>
        )}
      </form>

      {error && (
        <p className="selection-error">
          <AlertCircle size={16} />
          {error}
        </p>
      )}
    </Card>
  )
}

export default AsOnDateFilter
