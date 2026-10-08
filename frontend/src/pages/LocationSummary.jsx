import { Navigate, useLocation } from 'react-router'

import { toQuery } from '../utils/stockFormat'

/*
 * Legacy route: /reports/location-summary?location=<name>
 *
 * Tally calls these "Godowns", and the Godown Summary now lives at
 * /reports/godowns/:name (see StockSummaryDrill), showing closing
 * quantity, rate and value like Tally does. This forwards old links.
 */
function LocationSummary() {
  const params = new URLSearchParams(useLocation().search)
  const godown = params.get('location')

  if (!godown) {
    return <Navigate to="/reports/inventory?tab=godowns" replace />
  }

  return (
    <Navigate
      to={`/reports/godowns/${encodeURIComponent(godown)}${toQuery({
        from: params.get('from'),
        to: params.get('to'),
      })}`}
      replace
    />
  )
}

export default LocationSummary
