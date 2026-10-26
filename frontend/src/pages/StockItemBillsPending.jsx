import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import { formatDate } from '../utils/format'
import { formatSignedAmount, formatQuantityWithUnit, toQuery } from '../utils/stockFormat'

const COLUMNS = [
  { key: 'date', label: 'Date' },
  { key: 'tracking_number', label: 'Tracking Number' },
  { key: 'party', label: 'Name of Party' },
  { key: 'initial_quantity', label: 'Initial Quantity', align: 'right' },
  { key: 'pending_quantity', label: 'Pending Quantity', align: 'right' },
  { key: 'rate', label: 'Rate (Disc %)', align: 'right' },
  { key: 'value', label: 'Value', align: 'right' },
]

/*
 * Tally's Sales Bills Pending: "Bills Made but Goods not Delivered".
 *
 * One page for both ways in - the (Sale Bills Pending) line of Godown /
 * Stock Item Vouchers, and a bill under it. A bill under it arrives with
 * its tracking number (and party) and is opened and highlighted here;
 * the page still lists every pending bill, as Tally does.
 */
function StockItemBillsPending() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)

  const itemName = params.get('item') || ''
  const fromDate = params.get('from') || ''
  const toDate = params.get('to') || ''
  const focusTracking = params.get('tracking_number') || ''
  const focusParty = params.get('party') || ''

  const query = {
    stock_item_name: itemName,
    from_date: fromDate || undefined,
    to_date: toDate || undefined,
  }

  const path = itemName
    ? `/reports/stock-item-bills-pending${toQuery(query)}`
    : null

  const { data: response, loading, error } = useFetch(path)

  const rows = response?.report || []
  const details = response?.details || []
  const unit = response?.unit || ''

  const qty = (value) => formatQuantityWithUnit(value, unit)

  // Tally opens a bill with Enter / double-click: the delivery and
  // return notes it is made of are listed under it.
  const [expanded, setExpanded] = useState({})

  const billKey = (row) => `${row.tracking_number}|${row.party || ''}`

  // The bill the user came from: its tracking number, and its party
  // when several bills share the number.
  const sameTracking = rows.filter(
    (row) => focusTracking && (row.tracking_number || '') === focusTracking
  )
  const focusedBill =
    sameTracking.find((row) => (row.party || '') === focusParty) || sameTracking[0]
  const focusKey = focusedBill ? billKey(focusedBill) : ''

  const isOpen = (row) => expanded[billKey(row)] ?? billKey(row) === focusKey

  // A bill is its tracking number. The party is not compared: a return
  // (Rej In) booked against the bill may carry no party, or another one.
  const notesOf = (row) =>
    details.filter(
      (note) => (note.tracking_number || '') === (row.tracking_number || '')
    )

  const toggle = (row) =>
    setExpanded((current) => ({ ...current, [billKey(row)]: !isOpen(row) }))

  // Tally leaves the rate and value blank when the bill carries none.
  const amountOrBlank = (value) => (value ? formatSignedAmount(value) : '')

  const totalOf = (key) => rows.reduce((sum, row) => sum + (row[key] || 0), 0)

  const openVoucher = (note) => {
    if (!note.voucher_type || !note.voucher_number) return

    navigate(`/reports/inventory-voucher${toQuery({
      voucher_type: note.voucher_type,
      voucher_number: note.voucher_number,
      date: note.date,
      item: itemName,
    })}`)
  }

  return (
    <>
      <PageHeader
        title="Sales Bills Pending"
        subtitle={
          itemName
            ? `${itemName}${fromDate && toDate ? ` · ${fromDate} to ${toDate}` : ''}`
            : undefined
        }
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} /> Back
          </button>
        }
      />

      <Card>
        {!itemName && <ErrorMessage message="No stock item was specified." />}
        {itemName && loading && <Loader />}
        {itemName && error && <ErrorMessage message={error} />}

        {itemName && !loading && !error && response?.success && (
          <>
            <p className="table-hint">
              Bills Made but Goods not Delivered — double-click a bill to see the notes it is made of.
            </p>

            {rows.length === 0 ? (
              <div className="empty-state">
                <span>No records found.</span>
              </div>
            ) : (
              <div className="data-table-scroll">
                <table className="data-table">
                  <thead>
                    <tr>
                      {COLUMNS.map((column) => (
                        <th key={column.key} className={column.align === 'right' ? 'is-numeric' : undefined}>
                          {column.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const open = isOpen(row)

                      return [
                        <tr
                          key={billKey(row)}
                          className={`data-table-row--clickable${billKey(row) === focusKey ? ' bill-row--focused' : ''}`}
                          onDoubleClick={() => toggle(row)}
                          onKeyDown={(event) => {
                            if (event.key === 'Enter') toggle(row)
                          }}
                          tabIndex={0}
                          role="button"
                          aria-expanded={open}
                        >
                          <td>{formatDate(row.date)}</td>
                          <td>{row.tracking_number}</td>
                          <td>{row.party}</td>
                          <td className="is-numeric">{qty(row.initial_quantity)}</td>
                          <td className="is-numeric">{qty(row.pending_quantity)}</td>
                          <td className="is-numeric">{amountOrBlank(row.rate)}</td>
                          <td className="is-numeric">{amountOrBlank(row.rate ? row.value : 0)}</td>
                        </tr>,
                        ...(open
                          ? notesOf(row).map((note, noteIndex) => (
                              <tr
                                key={`${billKey(row)}-${noteIndex}`}
                                className={note.voucher_number ? 'data-table-row--clickable' : undefined}
                                onClick={() => openVoucher(note)}
                              >
                                <td><em>{formatDate(note.date)}</em></td>
                                <td><em>{note.voucher_type} {note.voucher_number}</em></td>
                                <td />
                                <td className="is-numeric"><em>{qty(Math.abs(note.quantity || 0))} @</em></td>
                                <td />
                                <td className="is-numeric"><em>{amountOrBlank(note.rate)}</em></td>
                                <td />
                              </tr>
                            ))
                          : []),
                      ]
                    })}
                    <tr>
                      <td colSpan={3}><strong>Total</strong></td>
                      <td className="is-numeric"><strong>{qty(totalOf('initial_quantity'))}</strong></td>
                      <td className="is-numeric"><strong>{qty(totalOf('pending_quantity'))}</strong></td>
                      <td />
                      <td />
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}
      </Card>
    </>
  )
}

export default StockItemBillsPending
