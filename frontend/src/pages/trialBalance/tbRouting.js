// Shared routing helpers for the Trial Balance drill-down.
//
// Every Trial Balance page carries the selected From/To dates in its
// URL (?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD). That is what lets a
// routed page fetch the right period from Tally and lets Back return
// to the exact Trial Balance state the user left.

export const TB_BASE = '/reports/trial-balance'

export function buildQuery(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(
      ([, value]) => value !== undefined && value !== null && value !== ''
    )
  ).toString()

  return query ? `?${query}` : ''
}

export function tbPath(sub, params = {}) {
  return `${TB_BASE}${sub}${buildQuery(params)}`
}

// One day before an ISO date (YYYY-MM-DD). Done in UTC so the result
// never shifts with the browser's timezone.
export function dayBefore(isoDate) {
  if (!isoDate) return ''

  const date = new Date(`${isoDate}T00:00:00Z`)
  if (Number.isNaN(date.getTime())) return ''

  date.setUTCDate(date.getUTCDate() - 1)
  return date.toISOString().slice(0, 10)
}

// Tally's own label lines that are not accounts and cannot be opened.
export function isNonDrillable(name) {
  return /^(difference in opening balances|grand total)$/i.test(
    (name || '').trim()
  )
}

// Tally shows the stock-in-hand line inside Current Assets as
// "Opening Stock"; opening it lands on the Opening Stock Summary
// (item-wise), not on another Group Summary.
export function isOpeningStock(name) {
  return /^(opening stock|stock[- ]in[- ]hand)$/i.test((name || '').trim())
}

// The "Purchase Bills to Come" line under Purchase Accounts opens the
// Purchase Bills Pending report.
export function isPurchaseBillsToCome(name) {
  return /^purchase bills to come$/i.test((name || '').trim())
}

// Where a row of a Group Summary (or of the Trial Balance itself,
// which only ever lists groups) should lead. `row` comes straight from
// the Tally-backed API: { name, is_ledger, is_group, ... }.
export function drillPathForRow(row, { from_date, to_date }) {
  const name = row?.name
  if (!name || isNonDrillable(name)) return null

  const dates = { from_date, to_date }

  if (isOpeningStock(name)) {
    return tbPath('/opening-stock', dates)
  }

  if (isPurchaseBillsToCome(name)) {
    return tbPath('/purchase-bills-pending', dates)
  }

  if (row.is_ledger) {
    return tbPath('/ledger', { ledger: name, ...dates })
  }

  return tbPath('/group', { group: name, ...dates })
}
