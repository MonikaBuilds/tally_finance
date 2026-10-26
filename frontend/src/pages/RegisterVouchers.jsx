import { useNavigate, useParams, useSearchParams } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import { formatDate } from '../utils/format'
import { formatAmount, formatQuantityWithUnit, toQuery } from '../utils/stockFormat'

/*
 * "List of All <X> Vouchers" - the screen Tally opens when a month is
 * clicked in an Inventory Books register.
 *
 *   /reports/registers/:key/vouchers?from=YYYY-MM-DD&to=YYYY-MM-DD
 *
 * Order books (Sales / Purchase Orders) show Order Ref No and Order
 * Amount; every other register shows Inwards / Outwards quantity.
 * Clicking a voucher opens its alteration screen
 * (/reports/inventory-voucher). Rows come from /reports/inventory-
 * register/:key/vouchers, i.e. straight from Tally.
 */
function RegisterVouchers() {
  const navigate = useNavigate()
  const { key } = useParams()
  const [searchParams] = useSearchParams()
  const from = searchParams.get('from')
  const to = searchParams.get('to')

  const path =
    from && to
      ? `/reports/inventory-register/${key}/vouchers${toQuery({ from_date: from, to_date: to })}`
      : null

  const { data: response, loading, error } = useFetch(path)

  const rows = Array.isArray(response?.report) ? response.report : []
  const isOrder = response?.kind === 'order'
  const totals = response?.totals || {}

  const baseColumns = [
    { key: 'date', label: 'Date', render: (r) => formatDate(r.date) },
    {
      key: 'particulars',
      label: 'Particulars',
      render: (r) => (
        <>
          {r.particulars}
          {r.is_cancelled ? ' (cancelled)' : ''}
          {r.is_optional ? ' (optional)' : ''}
        </>
      ),
    },
    { key: 'voucher_type', label: 'Vch Type' },
    { key: 'voucher_number', label: 'Vch No.' },
  ]

  const columns = isOrder
    ? [
        ...baseColumns,
        { key: 'order_ref_no', label: 'Order Ref No' },
        { key: 'order_amount', label: 'Order Amount', align: 'right', render: (r) => formatAmount(r.order_amount) },
      ]
    : [
        ...baseColumns,
        {
          key: 'inward_quantity',
          label: 'Inwards Qty',
          align: 'right',
          render: (r) => (r.inward_quantity ? formatQuantityWithUnit(r.inward_quantity, r.unit) : ''),
        },
        {
          key: 'outward_quantity',
          label: 'Outwards Qty',
          align: 'right',
          render: (r) => (r.outward_quantity ? formatQuantityWithUnit(r.outward_quantity, r.unit) : ''),
        },
      ]

  return (
    <>
      <PageHeader
        title={`List of All ${response?.voucher_type || ''} Vouchers`.replace('  ', ' ')}
        subtitle={from && to ? `${response?.report_name || ''} · ${from} to ${to}` : undefined}
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} /> Back
          </button>
        }
      />

      <Card>
        {!from || !to ? <ErrorMessage message="No period was specified." /> : null}
        {path && loading && <Loader />}
        {path && error && <ErrorMessage message={error} />}
        {path && !loading && !error && response && !response.success && (
          <ErrorMessage message={response.error || response.message || 'Unable to load vouchers.'} />
        )}

        {path && !loading && !error && response?.success && (
          <>
            {rows.length === 0 ? (
              <div className="empty-state">No vouchers in this period.</div>
            ) : (
              <>
                <p className="table-hint">Click a voucher to open it.</p>
                <DataTable
                  columns={columns}
                  rows={rows}
                  onRowClick={(row) =>
                    navigate(
                      `/reports/inventory-voucher${toQuery({
                        voucher_type: row.voucher_type,
                        voucher_number: row.voucher_number,
                        date: row.date,
                      })}`
                    )
                  }
                />
                <div className="table-footer">
                  <span>
                    Total:{' '}
                    {isOrder
                      ? formatAmount(totals.order_amount)
                      : `Inwards ${totals.inward_quantity || 0} · Outwards ${totals.outward_quantity || 0}`}
                  </span>
                </div>
              </>
            )}
          </>
        )}
      </Card>
    </>
  )
}

export default RegisterVouchers
