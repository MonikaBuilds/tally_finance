/**
 * Dynamic Dashboard Date Filter Utility
 * Zero hardcoded dates or years. All ranges are derived at runtime.
 */

const STORAGE_KEY = 'tfi.dashboard.date_filter'

/**
 * Format a Date object to local YYYY-MM-DD without UTC timezone shifts.
 */
export function formatLocalISO(dateObj) {
  const d = dateObj instanceof Date ? dateObj : new Date(dateObj)

  const year = d.getFullYear()
  const month = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')

  return `${year}-${month}-${day}`
}

/**
 * Get today's runtime date as YYYY-MM-DD.
 */
export function getRuntimeTodayISO() {
  return formatLocalISO(new Date())
}

/**
 * Dynamically determine the start of the Indian Financial Year.
 *
 * April–December:
 *   FY starts April 1 of the current year.
 *
 * January–March:
 *   FY starts April 1 of the previous year.
 */
export function getDynamicFinancialYearStart(refDate = new Date()) {
  const d = refDate instanceof Date ? refDate : new Date(refDate)

  const currentMonth = d.getMonth()
  const currentYear = d.getFullYear()

  const fyStartYear =
    currentMonth >= 3
      ? currentYear
      : currentYear - 1

  return `${fyStartYear}-04-01`
}

/**
 * Dynamically determine the end of the Indian Financial Year.
 *
 * Example:
 * FY start: 2026-04-01
 * FY end:   2027-03-31
 */
export function getDynamicFinancialYearEnd(refDate = new Date()) {
  const d = refDate instanceof Date ? refDate : new Date(refDate)

  const currentMonth = d.getMonth()
  const currentYear = d.getFullYear()

  const fyEndYear =
    currentMonth >= 3
      ? currentYear + 1
      : currentYear

  return `${fyEndYear}-03-31`
}

/**
 * Load initial Dashboard filter state.
 *
 * If a valid filter exists in sessionStorage, restore it.
 *
 * Otherwise default to the current Indian Financial Year:
 * FROM = Dynamic FY Start
 * TO   = Dynamic FY End
 */
export function getInitialDashboardFilter() {
  try {
    const saved = sessionStorage.getItem(STORAGE_KEY)

    if (saved) {
      const parsed = JSON.parse(saved)

      if (parsed?.fromDate && parsed?.toDate) {
        return {
          fromDate: parsed.fromDate,
          toDate: parsed.toDate,
          selectedPreset: parsed.selectedPreset || null,
        }
      }
    }
  } catch {
    // sessionStorage unavailable or invalid stored value.
  }

  const now = new Date()

  return {
    fromDate: getDynamicFinancialYearStart(now),
    toDate: getDynamicFinancialYearEnd(now),
    selectedPreset: '1y',
  }
}

/**
 * Persist dashboard filter state.
 *
 * Only date/filter information is stored.
 * No financial data is stored here.
 */
export function saveDashboardFilter(filter) {
  try {
    sessionStorage.setItem(
      STORAGE_KEY,
      JSON.stringify(filter)
    )
  } catch {
    // sessionStorage quota exceeded or unavailable.
  }
}

/**
 * Clear stored dashboard filter.
 *
 * Used during logout.
 */
export function clearDashboardFilter() {
  try {
    sessionStorage.removeItem(STORAGE_KEY)
  } catch {
    // Ignore storage errors.
  }
}

/**
 * Compute date ranges for Dashboard presets.
 *
 * 7d  = previous 7 days
 * 1m  = previous 1 month
 * 3m  = previous 3 months
 * 1y  = current Indian Financial Year
 */
export function getPresetDateRange(
  presetKey,
  baseDate = new Date()
) {
  const to = new Date(baseDate)

  /**
   * 1 Year represents the current Indian Financial Year.
   */
  if (presetKey === '1y') {
    return {
      fromDate: getDynamicFinancialYearStart(to),
      toDate: getDynamicFinancialYearEnd(to),
      selectedPreset: '1y',
    }
  }

  const from = new Date(to)

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
 * Validate Dashboard custom date range.
 */
export function validateDateRange(fromStr, toStr) {
  if (!fromStr || !toStr) {
    return {
      valid: false,
      error: 'Both From Date and To Date are required.',
    }
  }

  if (fromStr > toStr) {
    return {
      valid: false,
      error: 'From Date cannot be after To Date.',
    }
  }

  return {
    valid: true,
    error: null,
  }
}