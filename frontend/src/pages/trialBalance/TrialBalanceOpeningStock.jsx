import { useNavigate, useSearchParams } from 'react-router'
import { useFetch } from '../../hooks/useFetch'
import PageHeader from '../../components/layout/PageHeader'
import Loader from '../../components/common/Loader'
import ErrorMessage from '../../components/common/ErrorMessage'
import Card from '../../components/common/Card'
import DataTable from '../../components/common/DataTable'
import { formatCurrency, formatQuantity } from '../../utils/format'
import TrialBalanceBackButton from './TrialBalanceBackButton'
import { buildQuery, dayBefore, tbPath } from './tbRouting'

function quantityWithUnit(row) {
  return `${formatQuantity(row.quantity)}${row.unit ? ` ${row.unit}` : ''}`
}

const COLUMNS = [
  { key: 'stock_item', label: 'Particulars' },
  { key: 'quantity', label: 'Quantity', align: 'right', render: quantityWithUnit },
  { key: 'rate', label: 'Rate', align: 'right', render: (row) => formatCurrency(row.rate) },
  { key: 'value', label: 'Value', align: 'right', render: (row) => formatCurrency(row.value) },
]

/*
 * Trial Balance -> Current Assets -> Opening Stock -> Opening Stock
 * Summary. Item-wise opening balance for the selected period.
 *
 * Data: the existing /reports/stock-summary API. The opening balance
 * of a period is the stock as at the day before it starts, which is
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

  const header = (
    <PageHeader
      title="Opening Stock Summary"
      subtitle={fromDate && toDate ? `${fromDate} to ${toDate}` : undefined}
      actions={<TrialBalanceBackButton fallbackTo={tbPath('', dates)} />}
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

      const rate = useClosingAsOn
        ? Number(item.closing_rate) || 0
        : quantity
          ? Math.abs(value / quantity)
          : 0

      return { stock_item: item.stock_item, unit: item.unit, quantity, rate, value }
    })
    .filter((row) => row.quantity !== 0 || row.value !== 0)

  const totalValue = rows.reduce((sum, row) => sum + row.value, 0)
  const units = new Set(rows.map((row) => row.unit))
  const totalQuantity = rows.reduce((sum, row) => sum + row.quantity, 0)

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
              Total Quantity: {formatQuantity(totalQuantity)} {[...units][0] || ''}
            </span>
          )}
          <span>Total Value: {formatCurrency(totalValue)}</span>
        </div>
      </Card>
    </>
  )
}

export default TrialBalanceOpeningStock
