import { Navigate, useLocation } from 'react-router'

import { toQuery } from '../utils/stockFormat'

/*
 * Legacy route: /reports/stock-group-items?group=<name>
 *
 * Stock Group Summary now lives at /reports/stock-groups/:name (see
 * StockSummaryDrill). This keeps old bookmarks and links working by
 * forwarding them, carrying any period across.
 */
function StockGroupItems() {
  const params = new URLSearchParams(useLocation().search)
  const group = params.get('group')

  if (!group) {
    return <Navigate to="/reports/inventory?tab=stock-group-summary" replace />
  }

  return (
    <Navigate
      to={`/reports/stock-groups/${encodeURIComponent(group)}${toQuery({
        from: params.get('from'),
        to: params.get('to') || params.get('to_date'),
      })}`}
      replace
    />
  )
}

export default StockGroupItems
