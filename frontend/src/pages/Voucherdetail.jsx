import { useMemo } from 'react'
import { useSearchParams, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'

import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import { formatCurrency, formatDate } from '../utils/format'

function formatAmount(value) {
  if (value === undefined || value === null || value === '') {
    return formatCurrency(0)
  }

  return formatCurrency(Number(value) || 0)
}

/*
 * The full accounting voucher behind one Ledger row - what Tally
 * shows on its "Accounting Voucher Alteration" screen: the account
 * you drilled in from at the top, every other ledger line as
 * "Particulars" with its amount, and the narration/reference below.
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

  // The ledger line matching where the user drilled in from (marked by
  // the backend via ledger_name) is shown as the "Account" box, the way
  // Tally always puts the ledger you're viewing at the top. Everything
  // else becomes "Particulars", just like the real voucher screen.
  const accountEntry =
    entries.find((entry) => entry.is_selected_ledger) || entries[0] || null

  const particularEntries = entries.filter(
    (entry) => entry !== accountEntry
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
              <strong>{formatDate(voucher.date)}</strong>
            </div>
            {voucher.reference_number && (
              <div className="meta-item">
                <span>Reference</span>
                <strong>{voucher.reference_number}</strong>
              </div>
            )}
            {voucher.is_cancelled && (
              <div className="meta-item">
                <span>Status</span>
                <strong className="status-cancelled">Cancelled</strong>
              </div>
            )}
          </div>

          {accountEntry && (
            <div className="voucher-account-box">
              <div className="voucher-account-label">Account</div>
              <div className="voucher-account-name">
                {accountEntry.ledger_name}
              </div>
              <div className="voucher-account-amount">
                {formatAmount(accountEntry.debit || accountEntry.credit)}{' '}
                {accountEntry.debit ? 'Dr' : 'Cr'}
              </div>
            </div>
          )}

          <div className="voucher-particulars">
            <div className="voucher-particulars-title">Particulars</div>

            {particularEntries.length === 0 && (
              <p className="empty-state">No other ledger lines found.</p>
            )}

            {particularEntries.map((entry, index) => (
              <div className="voucher-particular-row" key={index}>
                <span className="voucher-particular-name">
                  {entry.ledger_name}
                </span>
                <span className="voucher-particular-amount">
                  {formatAmount(entry.debit || entry.credit)}{' '}
                  {entry.debit ? 'Dr' : 'Cr'}
                </span>
              </div>
            ))}
          </div>

          {voucher.narration && (
            <p className="card-note voucher-narration">
              <strong>Narration:</strong> {voucher.narration}
            </p>
          )}

          <div className="table-footer">
            <span>Total Debit: {formatCurrency(voucher.total_debit)}</span>
            <span>Total Credit: {formatCurrency(voucher.total_credit)}</span>
          </div>
        </Card>
      )}
    </>
  )
}

export default VoucherDetail