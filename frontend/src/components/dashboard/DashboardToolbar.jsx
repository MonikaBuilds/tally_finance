import { useState } from 'react'
import { Calendar, RefreshCw } from 'lucide-react'

import { DASHBOARD_PRESETS, validateDateRange } from '../../utils/dashboardDateFilter'
import { formatDay, formatTime } from './format'

function TallyStatusPill({ status }) {
  const labels = {
    checking: 'Checking Tally…',
    connected: 'Tally connected',
    offline: 'Tally disconnected',
  }

  return (
    <span className={`db-status db-status--${status}`} role="status">
      <span className="db-status-dot" aria-hidden="true" />
      {labels[status]}
    </span>
  )
}

function DashboardToolbar({
  companyName,
  tallyStatus,
  filter,
  onFilterChange,
  onRefresh,
  loading,
  fetchedAt,
}) {
  const [draft, setDraft] = useState({ from: filter.fromDate, to: filter.toDate })
  const [error, setError] = useState(null)

  // Keep the date inputs in step when a preset changes the filter.
  const [shownFilter, setShownFilter] = useState(filter)
  if (shownFilter !== filter) {
    setShownFilter(filter)
    setDraft({ from: filter.fromDate, to: filter.toDate })
    setError(null)
  }

  const draftChanged = draft.from !== filter.fromDate || draft.to !== filter.toDate

  function applyCustomRange(event) {
    event.preventDefault()

    const check = validateDateRange(draft.from, draft.to)
    if (!check.valid) {
      setError(check.error)
      return
    }

    onFilterChange({ fromDate: draft.from, toDate: draft.to, selectedPreset: null })
  }

  return (
    <header className="db-toolbar">
      <div className="db-toolbar-heading">
        <div className="db-title-row">
          <h1>Dashboard</h1>
          <TallyStatusPill status={tallyStatus} />
        </div>
        <p className="db-subtitle">
          {companyName ? <strong>{companyName}</strong> : 'Live figures from Tally'}
          <span aria-hidden="true"> · </span>
          {formatDay(filter.fromDate)} – {formatDay(filter.toDate)}
          {fetchedAt && (
            <>
              <span aria-hidden="true"> · </span>
              Updated {formatTime(fetchedAt)}
            </>
          )}
        </p>
      </div>

      <div className="db-toolbar-controls">
        <div className="db-presets" role="group" aria-label="Period">
          {DASHBOARD_PRESETS.map((preset) => (
            <button
              key={preset.key}
              type="button"
              className="db-preset"
              aria-pressed={filter.selectedPreset === preset.key}
              onClick={() => onFilterChange(preset.key)}
            >
              {preset.label}
            </button>
          ))}
        </div>

        <form className="db-range" onSubmit={applyCustomRange} aria-label="Custom period">
          <Calendar size={14} aria-hidden="true" />
          <input
            type="date"
            value={draft.from}
            max={draft.to || undefined}
            onChange={(event) => setDraft((current) => ({ ...current, from: event.target.value }))}
            aria-label="From date"
          />
          <span aria-hidden="true">–</span>
          <input
            type="date"
            value={draft.to}
            min={draft.from || undefined}
            onChange={(event) => setDraft((current) => ({ ...current, to: event.target.value }))}
            aria-label="To date"
          />
          {draftChanged && (
            <button type="submit" className="db-range-apply">
              Apply
            </button>
          )}
        </form>

        <button
          type="button"
          className="db-refresh"
          onClick={onRefresh}
          disabled={loading}
          title="Fetch the latest figures from Tally"
        >
          <RefreshCw size={14} className={loading ? 'db-spin' : undefined} aria-hidden="true" />
          Refresh
        </button>
      </div>

      {error && (
        <p className="db-range-error" role="alert">
          {error}
        </p>
      )}
    </header>
  )
}

export default DashboardToolbar
