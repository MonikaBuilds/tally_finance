import { useNavigate, useSearchParams } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import ExportButtons from '../components/common/ExportButtons'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import { formatMonthKey } from '../utils/format'
import { formatSignedAmount, formatQuantityWithUnit, toQuery } from '../utils/stockFormat'

/*
 * Stock Item Monthly Summary - every month of the period, like Tally.
 *
 * The backend (/reports/stock-item-monthly) builds one running balance
 * from the item's opening balance and its vouchers: Opening Balance,
 * then Inwards / Outwards / Closing for each month. The only things
 * done here are laying the rows out and adding up the Grand Total line.
 *
 * Period: ?from / ?to when given (drill-downs always pass them).
 * Otherwise the backend picks the latest financial year that has stock
 * activity in Tally and returns it as from / to.
 */
function StockItemMonthlySummary() {
  const navigate = useNavigate()
  const [searchParams] = useSearchParams()
  const itemName = searchParams.get('item') || ''

  // ?location=<godown> turns this into Tally's Godown Monthly Summary
  // (same screen, scoped to one godown).
  const godown = searchParams.get('location') || ''

  const path = itemName
    ? `/reports/stock-item-monthly${toQuery({
        stock_item_name: itemName,
        godown_name: godown,
        from_date: searchParams.get('from'),
        to_date: searchParams.get('to'),
      })}`
    : null

  const { data: response, loading, error } = useFetch(path)

  const from = response?.from || searchParams.get('from')
  const to = response?.to || searchParams.get('to')

  const unit = response?.unit
  const months = Array.isArray(response?.report) ? response.report : []
  const qty = (value) => formatQuantityWithUnit(value, unit)

  const total = (key) => months.reduce((sum, r) => sum + (r[key] || 0), 0)
  const last = months[months.length - 1]
  const opening = response?.opening

  // Tally's layout: an Opening Balance line (shown under Closing
  // Balance), the twelve months, then a Grand Total line.
  const rows = months.length
    ? [
        {
          kind: 'opening',
          closing_quantity: opening?.quantity,
          closing_value: opening?.value,
        },
        ...months.map((month) => ({ kind: 'month', ...month })),
        {
          kind: 'total',
          inward_quantity: total('inward_quantity'),
          inward_value: total('inward_value'),
          outward_quantity: total('outward_quantity'),
          outward_value: total('outward_value'),
          closing_quantity: last?.closing_quantity,
          closing_value: last?.closing_value,
        },
      ]
    : []

  const emphasis = (row, content) =>
    row.kind === 'month' ? content : <strong>{content}</strong>

  const amountCell = (row, key) => {
    const value = row[key]

    // A month with no movement leaves the column blank, as Tally does.
    if (row.kind === 'month' && !value) return ''
    if (row.kind !== 'month' && (value === undefined || value === null)) return ''

    return emphasis(row, formatSignedAmount(value))
  }

  const qtyCell = (row, key) => {
    const value = row[key]

    if (row.kind === 'month' && !value) return ''
    if (row.kind !== 'month' && (value === undefined || value === null)) return ''

    return emphasis(row, qty(value))
  }

  const columns = [
    {
      key: 'month',
      label: 'Particulars',
      render: (r) => {
        if (r.kind === 'opening') return <em>Opening Balance</em>
        if (r.kind === 'total') return <strong>Grand Total</strong>
        return formatMonthKey(r.month)
      },
    },
    { key: 'inward_quantity', label: 'Inwards Qty', align: 'right', render: (r) => qtyCell(r, 'inward_quantity') },
    { key: 'inward_value', label: 'Inwards Value', align: 'right', render: (r) => amountCell(r, 'inward_value') },
    { key: 'outward_quantity', label: 'Outwards Qty', align: 'right', render: (r) => qtyCell(r, 'outward_quantity') },
    { key: 'outward_value', label: 'Outwards Value', align: 'right', render: (r) => amountCell(r, 'outward_value') },
    { key: 'closing_quantity', label: 'Closing Qty', align: 'right', render: (r) => qtyCell(r, 'closing_quantity') },
    { key: 'closing_value', label: 'Closing Value', align: 'right', render: (r) => amountCell(r, 'closing_value') },
  ]

  return (
    <>
      <PageHeader
        title={
          godown
            ? `Godown Monthly Summary: ${godown}${itemName ? ` — ${itemName}` : ''}`
            : `Stock Item Monthly Summary${itemName ? `: ${itemName}` : ''}`
        }
        subtitle={from && to ? `${from} to ${to}` : undefined}
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} /> Back
          </button>
        }
      />
      <div className="export-bar">
        <ExportButtons basePath="/reports/stock-item-monthly/export" filenameBase={`monthly_${itemName}`} params={{ stock_item_name: itemName, godown_name: godown, from_date: from, to_date: to }} />
      </div>

      <Card>
        {!itemName && <ErrorMessage message="No stock item was specified." />}
        {itemName && loading && <Loader />}
        {itemName && error && <ErrorMessage message={error} />}
        {itemName && !loading && !error && response && !response.success && (
          <ErrorMessage message={response.error || response.message || 'Unable to load the monthly summary.'} />
        )}

        {itemName && !loading && !error && response?.success && (
          <>
            <p className="table-hint">
              Click a month to view that month's {godown ? 'godown' : 'stock item'} vouchers.
            </p>
            {response.approximate && (
              <p className="table-hint">
                This item is held in more than one godown, so this godown's closing figures are worked
                out from its opening allocation and vouchers at Tally's closing rate.
              </p>
            )}

            <DataTable
              columns={columns}
              rows={rows}
              isRowClickable={(row) => row.kind === 'month'}
              onRowClick={(row) =>
                navigate(
                  godown
                    ? `/reports/location-vouchers${toQuery({ location: godown, item: itemName, from: row.from, to: row.to })}`
                    : `/reports/stock-item-vouchers${toQuery({ item: itemName, from: row.from, to: row.to })}`
                )
              }
            />

            {months.some((r) => r.pending_bills_quantity) && (
              <p className="table-hint">
                Inwards / Outwards include Tally's Sale / Purchase Bills Pending (goods delivered or
                received but not yet billed).
              </p>
            )}

            {response.reconciled === false && !godown && (
              <p className="table-hint">
                The closing quantity differs from the figure Tally reports for {to}. Check that the
                period ends on a date Tally has data for.
              </p>
            )}
          </>
        )}
      </Card>
    </>
  )
}

export default StockItemMonthlySummary
