import { Fragment, useState } from 'react'
import { useNavigate } from 'react-router'
import { ChevronDown, ChevronRight, Inbox } from 'lucide-react'
import { useFetch } from '../../hooks/useFetch'
import { formatDate } from '../../utils/format'

// Tally prints these reports to the paisa (35,50,000.00), no currency symbol.
const moneyFormat = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
})

function formatMoney(value) {
  if (value === undefined || value === null || value === '') return ''
  return moneyFormat.format(Number(value) || 0)
}

// Query string for the app's one Voucher page (/reports/voucher), built
// only from what the server returned for that voucher.
function voucherQuery(transaction, party) {
  if (!transaction?.voucher_type || !transaction?.voucher_number) return null

  const params = new URLSearchParams({
    voucher_type: transaction.voucher_type,
    voucher_number: transaction.voucher_number,
  })

  if (transaction.voucher_date) params.set('date', transaction.voucher_date)
  if (party) params.set('ledger_name', party)

  return params.toString()
}

function onEnterOrSpace(event, action) {
  if (event.key === 'Enter' || event.key === ' ') {
    event.preventDefault()
    action()
  }
}

/*
 * One voucher under a bill, plus - for an item voucher - its stock
 * lines ("20 NOS  SmartMind AI- Old Version  10,000.00/NOS"), exactly
 * as Tally lists them under the voucher in Bills Receivable / Payable.
 *
 * The stock lines are read from the same /reports/voucher API the
 * Voucher page uses (cached by the server). A voucher without stock
 * lines, or one the lookup cannot return, simply shows no extra rows.
 */
function VoucherRows({ transaction, party, onOpen }) {
  const query = voucherQuery(transaction, party)
  const { data: response } = useFetch(query ? `/reports/voucher?${query}` : null)

  const items =
    response?.success && Array.isArray(response?.voucher?.items)
      ? response.voucher.items
      : []

  const clickable = Boolean(query)

  return (
    <>
      <tr
        className="bills-voucher-row"
        onDoubleClick={clickable ? () => onOpen(query) : undefined}
        onKeyDown={clickable ? (event) => onEnterOrSpace(event, () => onOpen(query)) : undefined}
        tabIndex={clickable ? 0 : undefined}
        title={clickable ? 'Double-click to open the voucher' : undefined}
      >
        <td>{formatDate(transaction.voucher_date)}</td>
        <td>{transaction.voucher_type}</td>
        <td>{transaction.voucher_number}</td>
        <td className="is-numeric">
          {formatMoney(transaction.display_amount ?? Math.abs(Number(transaction.amount) || 0))}{' '}
          {transaction.side}
        </td>
        <td />
        <td />
      </tr>

      {items.map((item, index) => (
        <tr className="bills-item-row" key={`${item.name}-${index}`}>
          <td />
          <td colSpan={2}>
            <strong>{item.quantity}</strong>
            <span className="bills-item-name">{item.name}</span>
          </td>
          <td className="is-numeric">
            {item.rate !== null && item.rate !== undefined
              ? `${formatMoney(item.rate)}${item.unit ? `/${item.unit}` : ''}`
              : ''}
          </td>
          <td />
          <td />
        </tr>
      ))}
    </>
  )
}

/*
 * Bills Receivable / Bills Payable, laid out like Tally's own report:
 *
 *   Date | Ref. No. | Party's Name | Pending Amount | Due on | Overdue by days
 *
 * Double-click a bill  -> the vouchers that make it up appear directly
 *                         under it (Purchase / Sales / Payment / Receipt
 *                         ... with Cr/Dr), as Tally shows them.
 * Double-click a voucher -> the Accounting Voucher page for that voucher.
 *
 * Every figure comes from the server (/reports/receivables or
 * /reports/payables); nothing is hardcoded here. No new route is added:
 * the drill-down is in-page and the voucher opens on the existing
 * /reports/voucher page.
 */
function BillsOutstandingTable({ bills }) {
  const navigate = useNavigate()
  const [openKey, setOpenKey] = useState(null)

  if (!Array.isArray(bills) || bills.length === 0) {
    return (
      <div className="empty-state">
        <Inbox size={28} strokeWidth={1.5} />
        <span>No records found.</span>
      </div>
    )
  }

  function toggle(key) {
    setOpenKey((current) => (current === key ? null : key))
  }

  function openVoucher(query) {
    navigate(`/reports/voucher?${query}`)
  }

  return (
    <div className="data-table-scroll">
      <table className="data-table bills-table">
        <thead>
          <tr>
            <th>Date</th>
            <th>Ref. No.</th>
            <th>Party&apos;s Name</th>
            <th className="is-numeric">Pending Amount</th>
            <th>Due on</th>
            <th className="is-numeric">Overdue by days</th>
          </tr>
        </thead>

        <tbody>
          {bills.map((bill, index) => {
            const key = `${bill.party}|${bill.bill_reference}|${index}`
            const isOpen = openKey === key
            // One net line per voucher, like Tally. Older cached responses
            // without "vouchers" still render from the raw allocations.
            const transactions = Array.isArray(bill.vouchers)
              ? bill.vouchers
              : Array.isArray(bill.transactions)
                ? bill.transactions
                : []

            return (
              <Fragment key={key}>
                <tr
                  className={`data-table-row--clickable${isOpen ? ' bill-row--focused' : ''}`}
                  onDoubleClick={() => toggle(key)}
                  onKeyDown={(event) => onEnterOrSpace(event, () => toggle(key))}
                  tabIndex={0}
                  aria-expanded={isOpen}
                  title="Double-click to see the vouchers behind this bill"
                >
                  <td>
                    <span className="bills-chevron">
                      {isOpen ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
                    </span>
                    {formatDate(bill.bill_date)}
                  </td>
                  <td>{bill.bill_reference}</td>
                  <td>
                    <strong>{bill.party}</strong>
                  </td>
                  <td className="is-numeric">
                    <strong>{formatMoney(bill.outstanding_amount)}</strong>
                  </td>
                  <td>{formatDate(bill.due_date)}</td>
                  <td className="is-numeric">{bill.overdue_days ?? ''}</td>
                </tr>

                {isOpen && transactions.length === 0 && (
                  <tr className="bills-voucher-row">
                    <td colSpan={6}>
                      <em>Tally returned no vouchers for this bill.</em>
                    </td>
                  </tr>
                )}

                {isOpen &&
                  transactions.map((transaction, txIndex) => (
                    <VoucherRows
                      key={`${transaction.guid || transaction.voucher_number}-${txIndex}`}
                      transaction={transaction}
                      party={bill.party}
                      onOpen={openVoucher}
                    />
                  ))}
              </Fragment>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}

export default BillsOutstandingTable
