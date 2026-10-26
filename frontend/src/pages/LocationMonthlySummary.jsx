import StockItemMonthlySummary from './StockItemMonthlySummary'

/*
 * Godown Monthly Summary: /reports/location-monthly?location=&item=
 *
 * The same twelve-month screen as the Stock Item Monthly Summary,
 * scoped to one godown (the `location` query parameter switches it on).
 */
function LocationMonthlySummary() {
  return <StockItemMonthlySummary />
}

export default LocationMonthlySummary
