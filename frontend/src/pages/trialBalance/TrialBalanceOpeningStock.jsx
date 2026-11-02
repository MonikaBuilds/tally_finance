import { useNavigate, useSearchParams } from 'react-router'
import { useFetch } from '../../hooks/useFetch'
import PageHeader from '../../components/layout/PageHeader'
import ExportButtons from '../../components/common/ExportButtons'
import Loader from '../../components/common/Loader'
import ErrorMessage from '../../components/common/ErrorMessage'
import Card from '../../components/common/Card'
import DataTable from '../../components/common/DataTable'
import { formatAmount, formatQuantityWithUnit } from '../../utils/stockFormat'
import { buildQuery, dayBefore, tbPath } from './tbRouting'

// Tally's Opening Stock Summary: Particulars, then the Opening Balance
// as Quantity, Rate and Value. The unit is printed after the quantity
// (15 NOS), not in a column of its own.
const COLUMNS = [
  { key: 'stock_item', label: 'Particulars' },
  {
    key: 'quantity',
    label: 'Quantity',
    align: 'right',
    render: (row) => formatQuantityWithUnit(row.quantity, row.unit),
  },
  {
    key: 'rate',
    label: 'Rate',
    align: 'right',
    render: (row) => formatAmount(row.rate),
  },
  {
    key: 'value',
    label: 'Value',
    align: 'right',
    render: (row) => formatAmount(row.value),
  },
]

/*
 * Trial Balance -> Opening Stock (Tally's F4 on Opening Stock).
 *
 * Opening stock for a period is the closing stock on the day before
 * From Date. We reuse the existing /reports/stock-summary API with
 * ?to_date=<day before From Date>, which matches Tally and matches
 * how the existing Stock Item Monthly Summary computes its own Opening
 * Balance row - so the two screens agree. If no From Date is in play,
 * the items' opening balances as held in Tally are used instead.
 *
 * Clicking an item opens the existing Stock Item Monthly Summary (and
 * from there Stock Item Vouchers), for the same period.
 */
function TrialBalanceOpeningStock() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()

  const fromDate = searchParams.get('from_date') || ''
  const toDate = searchParams.get('to_date') || ''

  const dates = { from_date: fromDate, to_date: toDate }
  const asOn = dayBefore(fromDate)

  const { data: response, loading, error } = useFetch(
    `/reports/stock-summary${buildQuery({ to_date: asOn })}`
  )

  const exportActions = (
    <ExportButtons
      basePath="/reports/trial-balance/opening-stock/export"
      filenameBase="opening_stock_summary"
      params={{ from_date: fromDate, to_date: toDate }}
    />
  )

  const header = (
    <PageHeader
      title="Opening Stock Summary"
      subtitle={fromDate && toDate ? `${fromDate} to ${toDate}` : undefined}
      backFallback={tbPath('', dates)}
      actions={exportActions}
    />
  )

  if (loading) return <>{header}<Loader /></>
  if (error) return <>{header}<ErrorMessage message={error} /></>
  if (!response?.success) {
    return <>{header}<ErrorMessage message={response?.error || response?.message} /></>
  }

  const useClosingAsOn = Boolean(asOn)

  const rows = (response.report || [])
    .map((item) => {
      const quantity = Number(useClosingAsOn ? item.closing_quantity : item.opening_quantity) || 0
      const value = Number(useClosingAsOn ? item.closing_value : item.opening_value) || 0

      // Rate as Tally prints it: the item's closing rate on the day
      // before the period, or the opening value per unit.
      const tallyRate = useClosingAsOn ? Number(item.closing_rate) : 0
      const rate = Number.isFinite(tallyRate) && tallyRate
        ? Math.abs(tallyRate)
        : quantity ? Math.abs(value / quantity) : 0

      return {
        stock_item: item.stock_item || item.name || '',
        unit: item.unit || item.base_units || '',
        quantity,
        rate,
        value,
      }
    })
    .filter((row) => row.value !== 0 || row.quantity !== 0)

  const totalValue = rows.reduce((acc, row) => acc + (row.value || 0), 0)
  const totalQuantity = rows.reduce((acc, row) => acc + (row.quantity || 0), 0)
  const units = new Set(rows.map((row) => row.unit).filter(Boolean))

  return (
    <>
      {header}

      <Card>
        <p className="table-hint">Click a stock item to view its Stock Item Monthly Summary.</p>

        <DataTable
          columns={COLUMNS}
          rows={rows}
          onRowClick={(row) =>
            navigate(
              `/reports/stock-item-monthly${buildQuery({
                item: row.stock_item,
                from: fromDate,
                to: toDate,
              })}`
            )
          }
        />

        <div className="table-footer">
          {units.size === 1 && (
            <span>
              Total Quantity: {formatQuantityWithUnit(totalQuantity, [...units][0])}
            </span>
          )}
          <span>Total Value: {formatAmount(totalValue)}</span>
        </div>
      </Card>
    </>
  )
}

export default TrialBalanceOpeningStock
