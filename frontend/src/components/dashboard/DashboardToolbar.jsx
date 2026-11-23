import { useState } from 'react'
import { Calendar, RefreshCw, Radio, Building2 } from 'lucide-react'

import { DASHBOARD_PRESETS, getRuntimeTodayISO, validateDateRange } from '../../utils/dashboardDateFilter'
import { formatDay, formatTime } from './format'

function TallyStatusPill({ status }) {
  const config = {
    checking: { label: 'Checking Tally…', className: 'db-status--checking' },
    connected: { label: 'Tally Prime Live', className: 'db-status--connected' },
    offline: { label: 'Tally Offline', className: 'db-status--offline' },
  }

  const current = config[status] || config.checking

  return (
    <span className={`db-status ${current.className}`} role="status">
      <span className="db-status-ping" aria-hidden="true" />
      <span className="db-status-dot" aria-hidden="true" />
      <span className="db-status-text">{current.label}</span>
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
  exportButtons,
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
      <div className="db-toolbar-header">
        <div className="db-toolbar-brand">
          <div className="db-company-badge">
            <Building2 size={15} className="db-company-icon" aria-hidden="true" />
            <span className="db-company-name">
              {companyName || 'Tally Financial Intelligence'}
            </span>
            <span className="db-company-tag">Primary Ledger</span>
          </div>

          <div className="db-title-row">
            <h1>Executive Financial Dashboard</h1>
            <TallyStatusPill status={tallyStatus} />
          </div>

          <p className="db-subtitle">
            <span className="db-period-indicator">
              <Calendar size={13} aria-hidden="true" />
              <span>{formatDay(filter.fromDate)} – {formatDay(filter.toDate)}</span>
            </span>
            {fetchedAt && (
              <>
                <span className="db-sub-sep" aria-hidden="true">•</span>
                <span className="db-sync-time">Books synced at {formatTime(fetchedAt)}</span>
              </>
            )}
          </p>
        </div>

        {exportButtons && (
          <div className="db-toolbar-actions">
            {exportButtons}
          </div>
        )}
      </div>

      <div className="db-toolbar-controls">
        <div className="db-presets-wrap">
          <span className="db-control-label">Fiscal Period:</span>
          <div className="db-presets" role="group" aria-label="Fiscal Period Presets">
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
        </div>

        <div className="db-controls-right">
          <form className="db-range" onSubmit={applyCustomRange} aria-label="Custom accounting date range">
            <Calendar size={14} className="db-range-icon" aria-hidden="true" />
            <input
              type="date"
              value={draft.from}
              max={draft.to || getRuntimeTodayISO()}
              onChange={(event) => setDraft((current) => ({ ...current, from: event.target.value }))}
              aria-label="From date"
            />
            <span className="db-range-sep" aria-hidden="true">to</span>
            <input
              type="date"
              value={draft.to}
              min={draft.from || undefined}
              max={getRuntimeTodayISO()}
              onChange={(event) => setDraft((current) => ({ ...current, to: event.target.value }))}
              aria-label="To date"
            />
            {draftChanged && (
              <button type="submit" className="db-range-apply">
                Apply Range
              </button>
            )}
          </form>

          <button
            type="button"
            className="db-refresh"
            onClick={onRefresh}
            disabled={loading}
            title="Fetch the latest live figures from Tally Prime"
          >
            <RefreshCw size={14} className={loading ? 'db-spin' : undefined} aria-hidden="true" />
            <span>{loading ? 'Syncing…' : 'Sync Tally'}</span>
          </button>
        </div>
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
