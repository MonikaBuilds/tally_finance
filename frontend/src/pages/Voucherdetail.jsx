import { useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'

import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import { formatDate } from '../utils/format'

import './Voucherdetail.css'

const inrFormatter = new Intl.NumberFormat('en-IN', {
  style: 'currency',
  currency: 'INR',
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
})

const numberFormatter = new Intl.NumberFormat('en-IN', {
  minimumFractionDigits: 0,
  maximumFractionDigits: 2,
})

function formatMoney(value) {
  if (value === undefined || value === null || value === '') {
    return inrFormatter.format(0)
  }

  return inrFormatter.format(Number(value) || 0)
}

function formatPlain(value) {
  if (value === undefined || value === null || value === '') return ''

  return numberFormatter.format(Number(value) || 0)
}

// "2025-04-02" -> "Wednesday" (Tally prints the weekday under the date).
function weekdayOf(value) {
  const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})/)
  if (!match) return ''

  const date = new Date(Number(match[1]), Number(match[2]) - 1, Number(match[3]))
  if (Number.isNaN(date.getTime())) return ''

  return date.toLocaleDateString('en-US', { weekday: 'long' })
}

function entryAmount(entry) {
  return Number(entry?.debit) || Number(entry?.credit) || 0
}

function entrySide(entry) {
  return entry?.side || (Number(entry?.debit) ? 'Dr' : 'Cr')
}

function balanceText(entry) {
  if (
    entry?.current_balance === undefined ||
    entry?.current_balance === null
  ) {
    return ''
  }

  return `${formatMoney(entry.current_balance)} ${entry.current_balance_type || ''}`.trim()
}

// Tally's own captions for the invoice reference, per voucher family.
function referenceLabel(voucher) {
  if (!voucher?.is_invoice) return 'Reference'

  if (voucher.base_type === 'purchase' || voucher.base_type === 'debit_note') {
    return 'Supplier Invoice No.'
  }

  return 'Reference No.'
}

function BillAllocations({ allocations }) {
  if (!Array.isArray(allocations) || allocations.length === 0) return null

  return (
    <div className="voucher-bills">
      {allocations.map((bill, index) => (
        <div className="voucher-bill-row" key={`${bill.name}-${index}`}>
          <span className="voucher-bill-type">{bill.bill_type || 'Ref'}</span>
          <span className="voucher-bill-name">{bill.name}</span>
          <span className="voucher-bill-amount">
            {formatMoney(bill.amount)} {bill.side}
          </span>
        </div>
      ))}
    </div>
  )
}

/*
 * The full accounting voucher behind one Ledger row - what Tally
 * shows on its "Accounting Voucher Alteration" screen. The layout
 * follows the voucher itself (not the ledger you drilled in from):
 *
 *   single_entry  Payment / Receipt / Contra -> Account + Particulars
 *   invoice       Sales / Purchase / Credit / Debit Note
 *                 -> Party A/c name + items + Particulars (with tax %)
 *   double_entry  Journal and anything else -> Debit / Credit columns
 *
 * Every figure (amounts, current balances, bill references, tax %)
 * comes from the Tally response; nothing is hardcoded here.
 */
function VoucherDetail() {
  const [searchParams] = useSearchParams()
  const navigate = useNavigate()

  const voucherType = searchParams.get('voucher_type') || ''
  const voucherNumber = searchParams.get('voucher_number') || ''
  const voucherDate = searchParams.get('date') || ''
  const ledgerName = searchParams.get('ledger_name') || ''

  const queryPath = useMemo(() => {
    if (!voucherType || !voucherNumber) return null

    const params = new URLSearchParams({
      voucher_type: voucherType,
      voucher_number: voucherNumber,
    })

    if (voucherDate) params.set('date', voucherDate)
    if (ledgerName) params.set('ledger_name', ledgerName)

    return `/reports/voucher?${params.toString()}`
  }, [voucherType, voucherNumber, voucherDate, ledgerName])

  const { data: response, loading, error } = useFetch(queryPath)

  const voucher =
    response?.success && response?.voucher ? response.voucher : null

  const entries = Array.isArray(voucher?.entries) ? voucher.entries : []
  const items = Array.isArray(voucher?.items) ? voucher.items : []

  // Older cached responses carry no layout/role: fall back to the
  // previous behaviour (drilled-in ledger on top) so nothing breaks.
  const layout = voucher?.layout || 'single_entry'

  const topEntry = voucher?.layout
    ? entries.find(
        (entry) => entry.role === 'account' || entry.role === 'party'
      ) || null
    : entries.find((entry) => entry.is_selected_ledger) || entries[0] || null

  const particularEntries = entries.filter((entry) => entry !== topEntry)

  const showRateColumn =
    layout === 'invoice' &&
    particularEntries.some(
      (entry) => entry.rate !== null && entry.rate !== undefined
    )

  if (!voucherType || !voucherNumber) {
    return (
      <>
        <PageHeader title="Voucher" />
        <Card>
          <ErrorMessage message="Missing voucher reference." />
        </Card>
      </>
    )
  }

  const topLabel = layout === 'invoice' ? 'Party A/c name' : 'Account'
  const weekday = weekdayOf(voucher?.date)

  return (
    <>
      <PageHeader
        title={voucherType ? `${voucherType} Voucher` : 'Voucher'}
        subtitle="Live data from TallyPrime"
      />

      <nav className="breadcrumbs">
        <button
          type="button"
          className="breadcrumb-link"
          onClick={() => navigate(-1)}
        >
          <ArrowLeft size={16} />
          Back
        </button>
      </nav>

      {loading && <Loader />}

      {error && <ErrorMessage message={error} />}

      {response && !response.success && (
        <ErrorMessage
          message={response.error || response.message || 'Voucher not found.'}
        />
      )}

      {voucher && (
        <Card title={`${voucher.voucher_type} No. ${voucher.voucher_number}`}>
          <div className="meta-list">
            <div className="meta-item">
              <span>Date</span>
              <strong>
                {formatDate(voucher.date)}
                {weekday ? ` (${weekday})` : ''}
              </strong>
            </div>
            {voucher.reference_number && (
              <div className="meta-item">
                <span>{referenceLabel(voucher)}</span>
                <strong>{voucher.reference_number}</strong>
              </div>
            )}
            {voucher.reference_number && voucher.reference_date && (
              <div className="meta-item">
                <span>{voucher.is_invoice ? 'Invoice Date' : 'Reference Date'}</span>
                <strong>{formatDate(voucher.reference_date)}</strong>
              </div>
            )}
            {voucher.is_cancelled && (
              <div className="meta-item">
                <span>Status</span>
                <strong className="status-cancelled">Cancelled</strong>
              </div>
            )}
          </div>

          {/* Account (Payment/Receipt/Contra) or Party A/c name (invoices) */}
          {topEntry && layout !== 'double_entry' && (
            <div className="voucher-account-box">
              <div className="voucher-account-label">{topLabel}</div>
              <div className="voucher-account-main">
                <div className="voucher-account-name">
                  {topEntry.ledger_name}
                </div>
                {balanceText(topEntry) && (
                  <div className="voucher-curbal">
                    Current balance: {balanceText(topEntry)}
                  </div>
                )}
                <BillAllocations allocations={topEntry.bill_allocations} />
              </div>
              <div className="voucher-account-amount">
                {formatMoney(entryAmount(topEntry))} {entrySide(topEntry)}
              </div>
            </div>
          )}

          {/* Stock items on an item invoice */}
          {layout === 'invoice' && items.length > 0 && (
            <div className="voucher-particulars">
              <div className="voucher-grid voucher-grid--items voucher-particulars-title">
                <span>Name of Item</span>
                <span className="voucher-num">Quantity</span>
                <span className="voucher-num">Rate</span>
                <span>per</span>
                <span className="voucher-num">Amount</span>
              </div>

              {items.map((item, index) => (
                <div
                  className="voucher-grid voucher-grid--items voucher-particular-row"
                  key={`${item.name}-${index}`}
                >
                  <span className="voucher-particular-name">{item.name}</span>
                  <span className="voucher-num">{item.quantity}</span>
                  <span className="voucher-num">{formatPlain(item.rate)}</span>
                  <span>{item.unit}</span>
                  <span className="voucher-num voucher-particular-amount">
                    {formatMoney(item.amount)}
                  </span>
                </div>
              ))}
            </div>
          )}

          <div className="voucher-particulars">
            {layout === 'double_entry' ? (
              <div className="voucher-grid voucher-grid--double voucher-particulars-title">
                <span>Particulars</span>
                <span className="voucher-num">Debit</span>
                <span className="voucher-num">Credit</span>
              </div>
            ) : (
              <div
                className={`voucher-grid ${
                  showRateColumn ? 'voucher-grid--rate' : 'voucher-grid--single'
                } voucher-particulars-title`}
              >
                <span>Particulars</span>
                {showRateColumn && <span className="voucher-num">Rate</span>}
                <span className="voucher-num">Amount</span>
              </div>
            )}

            {layout === 'double_entry'
              ? entries.map((entry, index) => (
                  <div
                    className="voucher-grid voucher-grid--double voucher-particular-row"
                    key={index}
                  >
                    <span className="voucher-particular-name">
                      <span className="voucher-side">{entrySide(entry)}</span>
                      {entry.ledger_name}
                      {balanceText(entry) && (
                        <span className="voucher-curbal">
                          Cur Bal: {balanceText(entry)}
                        </span>
                      )}
                      <BillAllocations allocations={entry.bill_allocations} />
                    </span>
                    <span className="voucher-num voucher-particular-amount">
                      {entry.debit ? formatMoney(entry.debit) : ''}
                    </span>
                    <span className="voucher-num voucher-particular-amount">
                      {entry.credit ? formatMoney(entry.credit) : ''}
                    </span>
                  </div>
                ))
              : particularEntries.map((entry, index) => (
                  <div
                    className={`voucher-grid ${
                      showRateColumn
                        ? 'voucher-grid--rate'
                        : 'voucher-grid--single'
                    } voucher-particular-row`}
                    key={index}
                  >
                    <span className="voucher-particular-name">
                      {entry.ledger_name}
                      {layout === 'single_entry' && balanceText(entry) && (
                        <span className="voucher-curbal">
                          Cur Bal: {balanceText(entry)}
                        </span>
                      )}
                      <BillAllocations allocations={entry.bill_allocations} />
                    </span>
                    {showRateColumn && (
                      <span className="voucher-num">
                        {entry.rate !== null && entry.rate !== undefined
                          ? `${formatPlain(entry.rate)} %`
                          : ''}
                      </span>
                    )}
                    <span className="voucher-num voucher-particular-amount">
                      {formatMoney(entryAmount(entry))} {entrySide(entry)}
                    </span>
                  </div>
                ))}

            {entries.length === 0 && (
              <p className="empty-state">No ledger lines found.</p>
            )}

            {layout !== 'double_entry' &&
              entries.length > 0 &&
              particularEntries.length === 0 && (
                <p className="empty-state">No other ledger lines found.</p>
              )}
          </div>

          {voucher.narration && (
            <p className="card-note voucher-narration">
              <strong>Narration:</strong> {voucher.narration}
            </p>
          )}

          <div className="table-footer">
            <span>Total Debit: {formatMoney(voucher.total_debit)}</span>
            <span>Total Credit: {formatMoney(voucher.total_credit)}</span>
          </div>
        </Card>
      )}
    </>
  )
}

export default VoucherDetail
