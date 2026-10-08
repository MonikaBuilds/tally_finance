// Formatting helpers for the Stock & Inventory screens.
//
// Tally prints stock amounts and rates to two decimals with Indian
// digit grouping (24,81,681.82), so the whole-rupee formatCurrency used
// elsewhere would hide the paise and make the figures look different
// from Tally. Kept in its own file so shared formatters stay untouched.

const AMOUNT_FORMAT = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

const QUANTITY_FORMAT = new Intl.NumberFormat('en-IN', {
  maximumFractionDigits: 3,
})

// 2481681.82 -> "24,81,681.82". Missing values show as a dash.
export function formatAmount(value) {
  if (value === undefined || value === null || value === '') return '-'
  return AMOUNT_FORMAT.format(Number(value))
}

// (3, 'NOS') -> "3 NOS". Quantity is null when Tally items in the
// roll-up use different units, in which case Tally shows no total.
export function formatQuantityWithUnit(quantity, unit) {
  if (quantity === undefined || quantity === null) return '-'
  return `${QUANTITY_FORMAT.format(Number(quantity))}${unit ? ` ${unit}` : ''}`
}

// Builds "?a=1&b=2" from an object, dropping empty values.
export function toQuery(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(
      ([, value]) => value !== undefined && value !== null && value !== ''
    )
  ).toString()

  return query ? `?${query}` : ''
}
