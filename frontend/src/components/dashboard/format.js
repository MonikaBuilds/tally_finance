// Display helpers for dashboard figures. Values arrive exactly as Tally
// reported them; these only change how they are written, never the value.

const inr = new Intl.NumberFormat('en-IN', { maximumFractionDigits: 0 })

export function isNumber(value) {
  return value !== null && value !== undefined && Number.isFinite(Number(value))
}

// ₹ 1,23,456 (Indian digit grouping); a missing value stays visibly missing.
export function formatAmount(value, { missing = '—' } = {}) {
  if (!isNumber(value)) return missing

  const number = Math.round(Number(value))
  const text = `₹ ${inr.format(Math.abs(number))}`

  return number < 0 ? `−${text}` : text
}

// Closing balances follow Tally's signed convention: negative is Dr,
// positive is Cr. Written the way Tally shows them: "₹ 10,000 Dr".
export function formatBalance(value, { missing = '—' } = {}) {
  if (!isNumber(value)) return missing

  const number = Math.round(Number(value))
  if (number === 0) return '₹ 0'

  return `₹ ${inr.format(Math.abs(number))} ${number < 0 ? 'Dr' : 'Cr'}`
}

// Short axis labels: ₹ 4.5L, ₹ 1.2Cr, ₹ 12K.
export function formatCompact(value) {
  if (!isNumber(value)) return ''

  const number = Number(value)
  const sign = number < 0 ? '−' : ''
  const abs = Math.abs(number)

  const scaled = (divisor, suffix) => {
    const result = abs / divisor
    const digits = result >= 100 || Number.isInteger(result) ? 0 : 1
    return `${sign}₹ ${result.toFixed(digits)}${suffix}`
  }

  if (abs >= 1e7) return scaled(1e7, 'Cr')
  if (abs >= 1e5) return scaled(1e5, 'L')
  if (abs >= 1e3) return scaled(1e3, 'K')

  return `${sign}₹ ${inr.format(abs)}`
}

const monthNames = [
  'Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun',
  'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec',
]

// 2026-09-30 -> 30 Sep 2026
export function formatDay(iso) {
  const match = /^(\d{4})-(\d{2})-(\d{2})/.exec(iso || '')
  if (!match) return iso || '—'

  const [, year, month, day] = match
  return `${Number(day)} ${monthNames[Number(month) - 1]} ${year}`
}

export function formatTime(iso) {
  if (!iso) return ''

  const date = new Date(iso)
  if (Number.isNaN(date.getTime())) return ''

  return date.toLocaleTimeString('en-IN', { hour: '2-digit', minute: '2-digit' })
}
