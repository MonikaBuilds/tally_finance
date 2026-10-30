import { useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import ExportButtons from '../components/common/ExportButtons'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import { formatDate } from '../utils/format'
import { formatAmount, formatQuantityWithUnit } from '../utils/stockFormat'

function toQuery(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, value]) => (
      value !== undefined && value !== null && value !== ''
    ))
  ).toString()

  return query ? `?${query}` : ''
}

/*
 * Inventory Voucher Alteration (Secondary) - Tally's voucher screen,
 * read from the voucher itself (/reports/inventory-voucher):
 *
 *   voucher type + No.                                  date, weekday
 *   Reference No / Party A/c name (+ current balance) /
 *   Purchase or Sales ledger (+ current balance) / delivery details
 *   Name of Item | Quantity | Rate | per | Amount        + total
 *   - a Stock Journal prints two panels, Source (Consumption) and
 *     Destination (Production)
 *   Narration
 *
 * Every value comes from the Tally response; a field Tally did not
 * return is not printed.
 */

// A Dr / Cr balance the way Tally prints it: "6,16,200.00 Cr".
const balanceText = (balance) =>
  balance ? `${formatAmount(balance.amount)} ${balance.side}` : ''

// Tally's own amounts for stock entries are signed (Dr/Cr); the voucher
// screen prints the magnitude.
const entryAmount = (entry) => {
  if (entry.amount_value !== undefined && entry.amount_value !== null) {
    return formatAmount(entry.amount_value)
  }

  const number = Math.abs(parseFloat(String(entry.amount ?? '').replace(/,/g, '')))
  return Number.isFinite(number) ? formatAmount(number) : ''
}

const entryRate = (entry) =>
  entry.rate_value !== undefined && entry.rate_value !== null
    ? formatAmount(Math.abs(entry.rate_value))
    : ''

const trimmed = (value) => String(value ?? '').trim()

const weekdayOf = (isoDate) => {
  if (!isoDate) return ''

  const date = new Date(`${isoDate}T00:00:00`)

  return Number.isNaN(date.getTime())
    ? ''
    : date.toLocaleDateString('en-IN', { weekday: 'long' })
}

// "Main Location" / "Primary Batch" under the item, like the godown and
// batch allocations Tally lists below an item.
function ItemCell({ entry }) {
  const allocations = (entry.allocations || []).filter(
    (allocation) => allocation.godown || allocation.batch
  )

  return (
    <div className="voucher-item">
      <strong>{entry.stock_item}</strong>

      {allocations.length > 1
        ? allocations.map((allocation, index) => (
            <span className="voucher-item-sub" key={index}>
              {[allocation.godown, allocation.batch].filter(Boolean).join(' · ')}
              {allocation.quantity ? ` — ${trimmed(allocation.quantity)}` : ''}
            </span>
          ))
        : batchText(entry) && (
            // One godown / the default batch is not printed by Tally;
            // a real batch name is.
            <span className="voucher-item-sub">{batchText(entry)}</span>
          )}

      {entry.tracking_number && (
        <span className="voucher-item-sub">Tracking No.: {entry.tracking_number}</span>
      )}
    </div>
  )
}

// Physical Stock vouchers record counted quantities only: Tally prints
// Batch/Lot No., Mfg Dt., Expiry Date, Quantity and Amount - no rate.
const isPhysicalStock = (voucherType) =>
  trimmed(voucherType).toLowerCase().includes('physical stock')

// "Primary Batch" is Tally's name for "no batch".
const batchText = (entry) =>
  /^primary batch$/i.test(trimmed(entry.batch)) ? '' : trimmed(entry.batch)

function physicalColumns() {
  return [
    {
      key: 'stock_item',
      label: 'Name of Item',
      render: (entry) => (
        <div className="voucher-item"><strong>{entry.stock_item}</strong></div>
      ),
    },
    { key: 'batch', label: 'Batch/Lot No.', align: 'right', render: batchText },
    { key: 'mfg_date', label: 'Mfg Dt.', align: 'right', render: (entry) => trimmed(entry.mfg_date) },
    { key: 'expiry_date', label: 'Expiry Date', align: 'right', render: (entry) => trimmed(entry.expiry_date) },
    {
      key: 'quantity',
      label: 'Quantity',
      align: 'right',
      render: (entry) => trimmed(entry.actual_quantity) || trimmed(entry.billed_quantity),
    },
    {
      key: 'amount',
      label: 'Amount',
      align: 'right',
      render: (entry) => (entry.amount_value ? entryAmount(entry) : ''),
    },
  ]
}

function entryColumns(entries, isOrder) {
  const billedDiffers = entries.some(
    (entry) =>
      trimmed(entry.billed_quantity) &&
      trimmed(entry.actual_quantity) &&
      trimmed(entry.billed_quantity) !== trimmed(entry.actual_quantity)
  )

  const columns = [
    { key: 'stock_item', label: 'Name of Item', render: (entry) => <ItemCell entry={entry} /> },
  ]

  if (billedDiffers) {
    columns.push(
      { key: 'actual_quantity', label: 'Actual Qty', align: 'right', render: (entry) => trimmed(entry.actual_quantity) },
      { key: 'billed_quantity', label: 'Billed Qty', align: 'right', render: (entry) => trimmed(entry.billed_quantity) }
    )
  } else {
    columns.push({
      key: 'quantity',
      label: 'Quantity',
      align: 'right',
      render: (entry) => trimmed(entry.billed_quantity) || trimmed(entry.actual_quantity),
    })
  }

  columns.push(
    { key: 'rate', label: 'Rate', align: 'right', render: entryRate },
    { key: 'unit', label: 'per', render: (entry) => entry.unit || '' }
  )

  if (isOrder && entries.some((entry) => trimmed(entry.order_due_date))) {
    columns.push({ key: 'order_due_date', label: 'Due on', render: (entry) => entry.order_due_date || '' })
  }

  columns.push({ key: 'amount', label: 'Amount', align: 'right', render: entryAmount })

  return columns
}

function TotalLine({ total, hideZeroAmount = false }) {
  if (!total) return null

  return (
    <div className="voucher-total">
      <span>Total</span>
      <span>{total.quantity !== null && total.quantity !== undefined ? formatQuantityWithUnit(total.quantity, total.unit) : ''}</span>
      <strong>{total.amount || !hideZeroAmount ? formatAmount(total.amount) : ''}</strong>
    </div>
  )
}

function Field({ label, value, note, aside }) {
  if (!value) return null

  return (
    <div className={aside ? 'voucher-field voucher-field-with-aside' : 'voucher-field'}>
      <span className="voucher-field-label">{label}</span>
      <div>
        <strong>{value}</strong>
        {note && <span className="voucher-field-note">Current balance: {note}</span>}
      </div>
      {aside && <div className="voucher-field-aside">{aside}</div>}
    </div>
  )
}

// Material In / Material Out print only the party and the godown on the
// other side of the movement (no reference). Tally names the godown
// field after the voucher type and prints "Not Applicable" when the
// voucher names none.
const materialMovement = (voucherType) => {
  const key = trimmed(voucherType).toLowerCase()

  if (key.includes('material in')) return 'Source Godown'
  if (key.includes('material out')) return 'Destination Godown'

  return ''
}

function InventoryVoucherDetail() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)

  const voucherType = params.get('voucher_type') || ''
  const voucherNumber = params.get('voucher_number') || ''
  const voucherDate = params.get('date') || ''

  const query = {
    voucher_type: voucherType,
    voucher_number: voucherNumber,
    voucher_date: voucherDate || undefined,
  }

  const path = voucherType && voucherNumber
    ? `/reports/inventory-voucher${toQuery(query)}`
    : null

  const { data: response, loading, error } = useFetch(path)
  const voucher = response?.voucher || null

  const entries = voucher?.inventory_entries || []
  const physical = voucher ? isPhysicalStock(voucher.voucher_type) : false
  const columns = voucher
    ? physical
      ? physicalColumns()
      : entryColumns(entries, voucher.is_order)
    : []

  // The party is printed on its own line; the other ledgers of the
  // voucher (the purchase / sales ledger) follow it.
  const ledgers = (voucher?.ledger_entries || []).filter((entry) => !entry.is_party)
  const ledgerLabel = voucher?.ledger_label ? `${voucher.ledger_label} ledger` : 'Ledger'

  // A voucher that carries the party's mailing details prints them in
  // a Ledger Account / Name and Address block instead of the plain
  // "Party A/c name" line.
  // Tally prints this block for vouchers entered in invoice mode (e.g.
  // Rejections Out); the others show the plain "Party A/c name" line
  // with its balance.
  const partyDetails = voucher?.is_invoice ? voucher?.party_details || null : null
  const movementLabel = voucher ? materialMovement(voucher.voucher_type) : ''
  // Tally asks this on Material Out (the voucher types that move goods
  // out under GST).
  const showGstEway = voucher
    ? /material out/.test(trimmed(voucher.voucher_type).toLowerCase())
    : false
  const voucherGodowns = voucher?.voucher_godowns || {}
  const typeKey = trimmed(voucher?.voucher_type).toLowerCase()
  const addressTitle =
    voucher?.ledger_label === 'Purchase'
      ? "Supplier's Name and Address"
      : voucher?.ledger_label === 'Sales'
        ? /rejections in|delivery note/.test(typeKey)
          ? "Customer's Name and Address"
          : "Buyer's Name and Address"
        : 'Name and Address'

  return (
    <>
      <PageHeader
        title={
          voucher?.is_order
            ? 'Order Voucher Alteration (Secondary)'
            : 'Inventory Voucher Alteration (Secondary)'
        }
        subtitle={voucher ? `${voucher.voucher_type} No. ${voucher.voucher_number}` : 'Live data from Tally'}
        backFallback="/reports/inventory"
        actions={
          <ExportButtons basePath="/reports/inventory-voucher/export" filenameBase={`${voucherType}_${voucherNumber}`} params={query} />
        }
      />

      <Card>
        {!voucherType || !voucherNumber ? (
          <ErrorMessage message="Missing inventory voucher reference." />
        ) : loading ? (
          <Loader />
        ) : error ? (
          <ErrorMessage message={error} />
        ) : !response?.success ? (
          <ErrorMessage message={response?.error || response?.message || 'Voucher not found.'} />
        ) : !voucher ? (
          <div className="empty-state">This voucher was not returned by Tally.</div>
        ) : (
          <div className="voucher-sheet">
            <div className="voucher-sheet-head">
              <div className="voucher-sheet-title">
                <span className="voucher-type-tag">{voucher.voucher_type}</span>
                <span>No. <strong>{voucher.voucher_number}</strong></span>
                {voucher.is_cancelled && <span className="status-cancelled">Cancelled</span>}
                {voucher.is_optional && <span className="voucher-optional">Optional</span>}
              </div>

              <div className="voucher-sheet-date">
                <strong>{formatDate(voucher.date)}</strong>
                <span>{weekdayOf(voucher.date)}</span>
              </div>
            </div>

            <div className="voucher-fields">
              {!movementLabel && !voucher.is_order && !partyDetails && (
                <Field
                  label="Reference No"
                  value={voucher.reference}
                  aside={
                    voucher.reference_date
                      ? <>Date <strong>{formatDate(voucher.reference_date)}</strong></>
                      : null
                  }
                />
              )}

              {!partyDetails && (
                <Field
                  label="Party A/c name"
                  value={voucher.party}
                  note={balanceText(voucher.party_balance)}
                  aside={
                    voucher.is_order && voucher.reference
                      ? <>Order no. <strong>{voucher.reference}</strong></>
                      : null
                  }
                />
              )}

              {Object.entries(voucherGodowns)
                .filter(([name]) => name !== movementLabel)
                .map(([name, value]) => (
                  <Field key={name} label={name} value={value} />
                ))}

              {movementLabel && (
                <Field
                  label={movementLabel}
                  value={voucherGodowns[movementLabel] || 'Not Applicable'}
                />
              )}

              {ledgers.map((entry) => (
                <Field
                  key={entry.ledger}
                  label={ledgerLabel}
                  value={entry.ledger}
                  note={balanceText(entry.balance)}
                />
              ))}

              {(voucher.is_order ? [] : voucher.details || []).map((detail) => (
                <Field key={detail.label} label={detail.label} value={detail.value} />
              ))}
            </div>

            {partyDetails && (
              <div className="voucher-panels voucher-party-panels">
                <div className="voucher-panel">
                  <h3 className="voucher-panel-title">Ledger Account</h3>
                  <p className="voucher-panel-body"><strong>{voucher.party}</strong></p>
                </div>

                <div className="voucher-panel">
                  <h3 className="voucher-panel-title">{addressTitle}</h3>
                  <p className="voucher-panel-body">
                    <strong>{partyDetails.name}</strong>
                    {partyDetails.address.map((line, index) => (
                      <span className="voucher-address-line" key={index}>{line}</span>
                    ))}
                  </p>
                </div>
              </div>
            )}

            {voucher.is_transfer ? (
              <>
                <p className="voucher-heading">Transfer of Materials</p>

                <div className="voucher-panels">
                  {[
                    ['source', 'Source (Consumption)'],
                    ['destination', 'Destination (Production)'],
                  ].map(([role, title]) => (
                    <div className="voucher-panel" key={role}>
                      <h3 className="voucher-panel-title">{title}</h3>
                      <DataTable
                        columns={columns}
                        rows={entries.filter((entry) => entry.role === role)}
                      />
                      <TotalLine total={voucher.totals?.[role]} />
                    </div>
                  ))}
                </div>
              </>
            ) : (
              <>
                {physical && (
                  <p className="voucher-heading">Physical Stock Verification</p>
                )}
                <DataTable columns={columns} rows={entries} />
                <TotalLine total={voucher.totals?.all} hideZeroAmount={physical} />
              </>
            )}

            {showGstEway && (
              <div className="voucher-fields">
                <Field label="Provide GST/e-Way Bill details" value={voucher.gst_eway_details} />
              </div>
            )}

            <p className="card-note voucher-narration">
              <strong>Narration:</strong> {voucher.narration}
            </p>

            <div className="table-footer">
              <span>Inventory Entries: {voucher.inventory_entry_count ?? 0}</span>
            </div>

            {params.get('debug') === '1' && (
              <pre className="card-note" style={{ whiteSpace: 'pre-wrap' }}>
                {JSON.stringify(
                  {
                    is_invoice: voucher.is_invoice,
                    party: voucher.party,
                    has_party_details: Boolean(voucher.party_details),
                    fields: Object.fromEntries(
                      Object.entries(voucher.fields || {}).filter(
                        ([key]) => !/^(ALLINVENTORY|INVENTORYENTRIES|ALLLEDGER|LEDGERENTRIES)/i.test(key)
                      )
                    ),
                  },
                  null,
                  2
                )}
              </pre>
            )}
          </div>
        )}
      </Card>
    </>
  )
}

export default InventoryVoucherDetail
