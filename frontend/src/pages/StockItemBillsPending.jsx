import { useState } from 'react'
import { useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import { formatCurrency, formatDate, formatQuantity } from '../utils/format'
import { formatSignedAmount } from '../utils/stockFormat'

function toQuery(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => (
      value !== undefined && value !== null && value !== ''
    ))
  ).toString()

  return query ? `?${query}` : ''
}

const SUMMARY_COLUMNS = [
  { key: 'date', label: 'Date', render: (row) => formatDate(row.date) },
  { key: 'tracking_number', label: 'Tracking Number' },
  { key: 'party', label: 'Name of Party' },
  { key: 'initial_quantity', label: 'Initial Quantity', align: 'right', render: (row) => formatQuantity(row.initial_quantity) },
  { key: 'pending_quantity', label: 'Pending Quantity', align: 'right', render: (row) => formatQuantity(row.pending_quantity) },
  { key: 'rate', label: 'Rate (Disc %)', align: 'right', render: (row) => formatCurrency(row.rate) },
  { key: 'value', label: 'Value', align: 'right', render: (row) => formatCurrency(row.value) },
]

const DETAIL_COLUMNS = [
  { key: 'date', label: 'Date', render: (row) => formatDate(row.date) },
  { key: 'voucher_type', label: 'Particulars' },
  { key: 'voucher_number', label: 'Vch No.' },
  { key: 'party', label: 'Name of Party' },
  { key: 'quantity', label: 'Quantity', align: 'right', render: (row) => formatQuantity(row.quantity) },
  { key: 'rate', label: 'Rate', align: 'right', render: (row) => formatCurrency(row.rate) },
  { key: 'value', label: 'Value', align: 'right', render: (row) => formatCurrency(row.value) },
  { key: 'reference', label: 'Reference' },
  { key: 'godown', label: 'Godown' },
  { key: 'batch', label: 'Batch' },
]

function StockItemBillsPending() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)

  const itemName = params.get('item') || ''
  const fromDate = params.get('from') || ''
  const toDate = params.get('to') || ''
  const trackingNumber = params.get('tracking_number') || ''
  const party = params.get('party') || ''

  const query = {
    stock_item_name: itemName,
    from_date: fromDate || undefined,
    to_date: toDate || undefined,
    tracking_number: trackingNumber || undefined,
    party: party || undefined,
  }

  const path = itemName
    ? `/reports/stock-item-bills-pending${toQuery(query)}`
    : null

  const { data: response, loading, error } = useFetch(path)

  const detailView = Boolean(trackingNumber)
  const rows = response?.report || []
  const details = response?.details || []

  // Tally opens a bill with Enter / double-click: the delivery and
  // return notes it is made of are listed under it.
  const [expanded, setExpanded] = useState({})

  const billKey = (row) => `${row.tracking_number}|${row.party || ''}`

  // A bill is its tracking number. The party is not compared: a return
  // (Rej In) booked against the bill may carry no party, or another one.
  const notesOf = (row) =>
    details.filter(
      (note) => (note.tracking_number || '') === (row.tracking_number || '')
    )

  const toggle = (row) =>
    setExpanded((current) => ({ ...current, [billKey(row)]: !current[billKey(row)] }))

  // Tally leaves the rate and value blank when the bill carries none.
  const amountOrBlank = (value) => (value ? formatSignedAmount(value) : '')

  const totalOf = (key) => rows.reduce((sum, row) => sum + (row[key] || 0), 0)

  const openVoucher = (note) => {
    if (!note.voucher_type || !note.voucher_number) return

    navigate(`/reports/inventory-voucher${toQuery({
      voucher_type: note.voucher_type,
      voucher_number: note.voucher_number,
      date: note.date,
    })}`)
  }

  return (
    <>
      <PageHeader
        title={detailView ? 'Bills Pending' : 'Sales Bills Pending'}
        subtitle={
          itemName
            ? `${itemName}${party ? ` — ${party}` : ''}${fromDate && toDate ? ` · ${fromDate} to ${toDate}` : ''}`
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

        {itemName && !loading && !error && response?.success && !detailView && (
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
                      {SUMMARY_COLUMNS.map((column) => (
                        <th key={column.key} className={column.align === 'right' ? 'is-numeric' : undefined}>
                          {column.label}
                        </th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((row) => {
                      const open = Boolean(expanded[billKey(row)])

                      return [
                        <tr
                          key={billKey(row)}
                          className="data-table-row--clickable"
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
                          <td className="is-numeric">{formatQuantity(row.initial_quantity)}</td>
                          <td className="is-numeric">{formatQuantity(row.pending_quantity)}</td>
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
                                <td className="is-numeric"><em>{formatQuantity(note.quantity)} @</em></td>
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
                      <td className="is-numeric"><strong>{formatQuantity(totalOf('initial_quantity'))}</strong></td>
                      <td className="is-numeric"><strong>{formatQuantity(totalOf('pending_quantity'))}</strong></td>
                      <td />
                      <td />
                    </tr>
                  </tbody>
                </table>
              </div>
            )}
          </>
        )}

        {itemName && !loading && !error && response?.success && detailView && (
          <>
            <div className="meta-list">
              <div className="meta-item">
                <span>Stock Item</span>
                <strong>{itemName}</strong>
              </div>
              {party && (
                <div className="meta-item">
                  <span>Name of Party</span>
                  <strong>{party}</strong>
                </div>
              )}
              <div className="meta-item">
                <span>Tracking Number</span>
                <strong>{trackingNumber}</strong>
              </div>
            </div>

            <p className="table-hint">
              Pending bill details are read from the Tally inventory voucher response.
            </p>

            <DataTable columns={DETAIL_COLUMNS} rows={details} />
          </>
        )}
      </Card>
    </>
  )
}

export default StockItemBillsPending
