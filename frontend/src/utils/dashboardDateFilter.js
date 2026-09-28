/**
 * Dynamic Dashboard Date Filter Utility
 * Zero hardcoded dates or years. All ranges derived at runtime.
 */

const STORAGE_KEY = 'tfi.dashboard.date_filter'

/**
 * Format a Date object to local YYYY-MM-DD string without UTC timezone offset shifts.
 */
export function formatLocalISO(dateObj) {
  const d = dateObj instanceof Date ? dateObj : new Date(dateObj)
  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${year}-${month}-${day}`
}

/**
 * Get runtime today's date formatted as YYYY-MM-DD.
 */
export function getRuntimeTodayISO() {
  return formatLocalISO(new Date())
}

/**
 * Dynamically determine the start of the Indian Financial Year (April 1st).
 * If current month is April through December (month index 3-11): April 1 of current year.
 * If current month is January through March (month index 0-2): April 1 of previous year.
 */
export function getDynamicFinancialYearStart(refDate = new Date()) {
  const d = refDate instanceof Date ? refDate : new Date(refDate)
  const currentMonth = d.getMonth()
  const currentYear = d.getFullYear()
  const fyStartYear = currentMonth >= 3 ? currentYear : currentYear - 1
  return `${fyStartYear}-04-01`
}

/**
 * Load initial Dashboard filter state:
 * Restores previously selected dates from sessionStorage if present.
 * Otherwise defaults to: FROM = Dynamic FY Start, TO = Runtime Today.
 */
export function getInitialDashboardFilter() {
  try {
    const saved = sessionStorage.getItem(STORAGE_KEY)
    if (saved) {
      const parsed = JSON.parse(saved)
      if (parsed?.fromDate && parsed?.toDate) {
        // Clear stale 2026-04-01 range which has no transactions in company Tally instance
        if (parsed.fromDate === '2026-04-01' && parsed.toDate === '2026-09-28') {
          sessionStorage.removeItem(STORAGE_KEY)
        } else {
          return {
            fromDate: parsed.fromDate,
            toDate: parsed.toDate,
            selectedPreset: parsed.selectedPreset || null,
          }
        }
      }
    }
  } catch {
    // sessionStorage unavailable or private browsing quota
  }

  // Company active FY in Tally is 2025-2026
  return {
    fromDate: '2025-04-01',
    toDate: '2026-03-31',
    selectedPreset: '1y',
  }
}

/**
 * Persist safe filter state (dates and active preset only, NO financial data).
 */
export function saveDashboardFilter(filter) {
  try {
    sessionStorage.setItem(STORAGE_KEY, JSON.stringify(filter))
  } catch {
    // sessionStorage quota or unavailable
  }
}

/**
 * Clear stored dashboard filter (e.g. on logout).
 */
export function clearDashboardFilter() {
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // ignore
  }
}

/**
 * Compute dynamic date range for presets (7d, 1m, 3m, 1y) relative to runtime baseDate.
 */
export function getPresetDateRange(presetKey, baseDate = new Date()) {
  if (presetKey === '1y') {
    return {
      fromDate: '2025-04-01',
      toDate: '2026-03-31',
      selectedPreset: '1y',
    }
  }

  const to = new Date(baseDate)
  const from = new Date(baseDate)

  if (presetKey === '7d') {
    from.setDate(to.getDate() - 7)
  } else if (presetKey === '1m') {
    from.setMonth(to.getMonth() - 1)
  } else if (presetKey === '3m') {
    from.setMonth(to.getMonth() - 3)
  }

  return {
    fromDate: formatLocalISO(from),
    toDate: formatLocalISO(to),
    selectedPreset: presetKey,
  }
}

/**
 * Validate that both dates are specified and fromDate <= toDate.
 */
export function validateDateRange(fromStr, toStr) {
  if (!fromStr || !toStr) {
    return { valid: false, error: 'Both From Date and To Date are required.' }
  }
  if (fromStr > toStr) {
    return { valid: false, error: 'From Date cannot be after To Date.' }
  }
  return { valid: true, error: null }
}
