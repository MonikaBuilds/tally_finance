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
 * Otherwise default to the current Indian Financial Year to date:
 * FROM = Dynamic FY Start
 * TO   = Today
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

  return getPresetDateRange('fy')
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

export const DASHBOARD_PRESETS = [
  { key: '7d', label: '7 days' },
  { key: '1m', label: '1 month' },
  { key: '3m', label: '3 months' },
  { key: 'fy', label: 'This FY' },
  { key: 'lfy', label: 'Last FY' },
]

/**
 * Compute date ranges for Dashboard presets.
 *
 * 7d  = previous 7 days
 * 1m  = previous 1 month
 * 3m  = previous 3 months
 * fy  = current Indian Financial Year, up to today
 * lfy = the whole previous Indian Financial Year
 *
 * Ranges stop at today: later dates have no vouchers in Tally yet.
 */
export function getPresetDateRange(
  presetKey,
  baseDate = new Date()
) {
  const to = new Date(baseDate)

  if (presetKey === 'fy') {
    return {
      fromDate: getDynamicFinancialYearStart(to),
      toDate: formatLocalISO(to),
      selectedPreset: 'fy',
    }
  }

  if (presetKey === 'lfy') {
    const fyStart = new Date(`${getDynamicFinancialYearStart(to)}T00:00:00`)
    const lastYearDay = new Date(fyStart)
    lastYearDay.setDate(fyStart.getDate() - 1)

    return {
      fromDate: getDynamicFinancialYearStart(lastYearDay),
      toDate: formatLocalISO(lastYearDay),
      selectedPreset: 'lfy',
    }
  }

  // Safely subtract months without JavaScript 31-day rollover bugs
  // (e.g. subtracting 1 month from Oct 31 should give Sep 30, not Oct 1)
  function subtractMonthsSafe(dateObj, monthsToSubtract) {
    const year = dateObj.getFullYear()
    const month = dateObj.getMonth()
    const day = dateObj.getDate()

    // Create target date at the 1st of the target month
    const targetDate = new Date(year, month - monthsToSubtract, 1)
    const targetYear = targetDate.getFullYear()
    const targetMonth = targetDate.getMonth()

    // Find the maximum valid days in the target month
    const maxDaysInTargetMonth = new Date(targetYear, targetMonth + 1, 0).getDate()

    // Clamp the day so 31st becomes 30th or 28th
    const safeDay = Math.min(day, maxDaysInTargetMonth)

    return new Date(targetYear, targetMonth, safeDay)
  }

  let from = new Date(to)

  if (presetKey === '7d') {
    from.setDate(to.getDate() - 7)
  } else if (presetKey === '1m') {
    from = subtractMonthsSafe(to, 1)
  } else if (presetKey === '3m') {
    from = subtractMonthsSafe(to, 3)
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

  const today = getRuntimeTodayISO()
  if (toStr > today) {
    return {
      valid: false,
      error: 'To Date cannot be in the future.',
    }
  }

  return {
    valid: true,
    error: null,
  }
}