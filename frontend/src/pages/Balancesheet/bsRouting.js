// Routing helpers for the Balance Sheet drill-down.
//
// Every page reached from the Balance Sheet carries the selected
// From/To dates in its URL (?from_date=YYYY-MM-DD&to_date=YYYY-MM-DD),
// exactly like the Trial Balance drill-down does, so each routed report
// asks Tally for the same period and Back returns to the same state.
//
// Existing routes/pages this connects to (none of them are changed):
//   Group Summary rows  -> /reports/group-summary API (via BalanceSheetGroup)
//   Ledger              -> /reports/ledger?view=monthly   (Ledger Monthly Summary)
//   Opening Stock       -> /reports/trial-balance/opening-stock
//   Purchase Bills      -> /reports/trial-balance/purchase-bills-pending
//   Profit & Loss A/c   -> /reports/profit-loss
//   Closing Stock       -> /reports/closing-stock (Stock Group Summary)

import {
  buildQuery,
  drillPathForRow,
  isNonDrillable,
} from '../trialBalance/tbRouting'

export const BS_BASE = '/reports/balance-sheet'
export const PROFIT_LOSS_PATH = '/reports/profit-loss'
export const CLOSING_STOCK_PATH = '/reports/closing-stock'

const TB_GROUP_BASE = '/reports/trial-balance/group'

export function bsPath(sub = '', params = {}) {
  return `${BS_BASE}${sub}${buildQuery(params)}`
}

export function isProfitLoss(name) {
  return /^profit\s*(&|and)\s*loss(\s*a\/c)?$/i.test((name || '').trim())
}

export function isClosingStock(name) {
  return /^closing stock$/i.test((name || '').trim())
}

// A line on the Balance Sheet itself (Capital Account, Loans (Liability),
// Current Liabilities, Current Assets, Profit & Loss A/c, ...).
// Returns the path it opens, or null when Tally does not open anything.
export function balanceSheetLinePath(row, dates) {
  const name = row?.name
  if (!name || isNonDrillable(name)) return null

  if (isProfitLoss(name)) return PROFIT_LOSS_PATH

  return bsPath('/group', { group: name, ...dates })
}

// The sub-lines Tally prints under Profit & Loss A/c ("Opening Balance",
// "Current Period"). "Current Period" is the P&L result for the period,
// so it opens the Profit & Loss report; the opening balance does not.
export function balanceSheetChildPath(child, parent) {
  if (isProfitLoss(parent?.name) && /^current period$/i.test((child?.name || '').trim())) {
    return PROFIT_LOSS_PATH
  }
  return null
}

// A row of a Group Summary reached from the Balance Sheet. The generic
// Trial Balance rules (sub-group, ledger, Opening Stock, Purchase Bills
// to Come) are reused as they are; the one line those rules do not know
// is Closing Stock, which opens the Stock Group Summary.
export function balanceSheetGroupRowPath(row, dates) {
  const name = row?.name
  if (!name || isNonDrillable(name)) return null

  if (isClosingStock(name)) {
    return `${CLOSING_STOCK_PATH}${buildQuery(dates)}`
  }

  const path = drillPathForRow(row, dates)

  // Keep sub-group drilling inside the Balance Sheet flow.
  if (path && path.startsWith(TB_GROUP_BASE)) {
    return path.replace(TB_GROUP_BASE, `${BS_BASE}/group`)
  }

  return path
}
