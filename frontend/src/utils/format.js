export function formatCurrency(value) {
  if (value === undefined || value === null) return '-'

  return new Intl.NumberFormat('en-IN', {
    style: 'currency',
    currency: 'INR',
    maximumFractionDigits: 0,
  }).format(value)
}

export function formatNumber(value) {
  if (value === undefined || value === null) return '-'

  return new Intl.NumberFormat('en-IN').format(value)
}

// Stock quantities can be fractional (kg, ltr, etc.) - keep up to 2 decimals
// instead of the integer-only formatting used for plain counts.
export function formatQuantity(value) {
  if (value === undefined || value === null) return '-'

  return new Intl.NumberFormat('en-IN', {
    maximumFractionDigits: 2,
  }).format(value)
}

/*
 * Date / month helpers shared by the Ledger, Ledger Month Detail
 * and Voucher Detail pages. The API returns dates as YYYY-MM-DD
 * (or occasionally DD-MM-YYYY from older parsers) - these helpers
 * normalize that for display and for building month/FY query ranges.
 */

// YYYY-MM-DD / DD-MM-YYYY / DD/MM/YYYY -> "3-Sep-2025" (Tally-style).
export function formatDate(value) {
  if (!value) return '-'

  const text = String(value).trim()
  let year, month, day

  const iso = text.match(/^(\d{4})-(\d{2})-(\d{2})/)
  const dash = text.match(/^(\d{2})-(\d{2})-(\d{4})$/)
  const slash = text.match(/^(\d{2})\/(\d{2})\/(\d{4})$/)

  if (iso) {
    ;[, year, month, day] = iso
  } else if (dash) {
    ;[, day, month, year] = dash
  } else if (slash) {
    ;[, day, month, year] = slash
  } else {
    return text
  }

  const monthNames = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ]

  const monthIndex = Number(month) - 1
  if (monthIndex < 0 || monthIndex > 11) return text

  return `${Number(day)}-${monthNames[monthIndex]}-${year}`
}

// "2025-04" -> "Apr-2025"
export function formatMonthKey(key) {
  if (!key) return ''

  const [year, month] = key.split('-')
  const monthNames = [
    'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
    'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
  ]

  const monthNumber = Number(month)
  if (!year || !monthNumber || monthNumber < 1 || monthNumber > 12) {
    return key
  }

  return `${monthNames[monthNumber - 1]}-${year}`
}

// "2025-04" -> { from: "2025-04-01", to: "2025-04-30" }
export function monthKeyToRange(key) {
  if (!key || !/^\d{4}-\d{2}$/.test(key)) return null

  const [yearStr, monthStr] = key.split('-')
  const year = Number(yearStr)
  const month = Number(monthStr)

  const from = `${yearStr}-${monthStr}-01`

  // Day 0 of next month = last day of this month.
  const lastDay = new Date(year, month, 0).getDate()
  const to = `${yearStr}-${monthStr}-${String(lastDay).padStart(2, '0')}`

  return { from, to }
}

// Indian financial year (1-Apr to 31-Mar) containing `refDate` (a Date,
// defaults to today). offset -1 gives the previous FY, 0 the current one.
export function financialYearRange(offset = 0, refDate = new Date()) {
  const year = refDate.getFullYear()
  const month = refDate.getMonth() // 0-indexed, Apr = 3

  // FY start year is the current year if we're on/after 1-Apr, else last year.
  const fyStartYear = (month >= 3 ? year : year - 1) + offset

  const pad = (n) => String(n).padStart(2, '0')

  return {
    from: `${fyStartYear}-04-01`,
    to: `${fyStartYear + 1}-03-31`,
    label: `FY ${fyStartYear}-${String(fyStartYear + 1).slice(-2)}`,
    pad,
  }
}