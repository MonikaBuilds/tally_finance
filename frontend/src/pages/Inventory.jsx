import { Fragment, useMemo, useState } from 'react'
import { AlertCircle, PackageSearch } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'

import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import ExportButtons from '../components/common/ExportButtons'
import { formatCurrency, formatQuantity } from '../utils/format'

// ------------------------------------------------------------------
// Shared bits
// ------------------------------------------------------------------

// Builds a query string from a params object, dropping empty values -
// mirrors the pattern used by ExportButtons for the GET report calls.
function toQuery(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(
      ([, value]) => value !== undefined && value !== null && value !== ''
    )
  ).toString()

  return query ? `?${query}` : ''
}

function ReportBody({ path, columns, exportBasePath, exportParams, filenameBase, footer }) {
  const { data: response, loading, error } = useFetch(path)

  if (loading) return <Loader />
  if (error) return <ErrorMessage message={error} />
  if (!response?.success) {
    return <ErrorMessage message={response?.error || response?.message} />
  }

  const report = response.report || []

  return (
    <>
      <div className="card-toolbar">
        <ExportButtons
          basePath={exportBasePath}
          params={exportParams}
          filenameBase={filenameBase}
        />
      </div>

      <DataTable columns={columns} rows={report} />

      {footer && footer(report)}
    </>
  )
}

// ------------------------------------------------------------------
// Registers (Sales Orders Book, Purchase Orders Book, Delivery Note
// Register, Receipt Note Register, Rejections In/Out Register, Stock
// Transfer Journal Register, Physical Stock Register, Material
// In/Out Register) - the exact "Registers" list Tally shows under
// Gateway of Tally > Display More Reports > Inventory Books.
// ------------------------------------------------------------------

const REGISTER_COLUMNS = [
  { key: 'month', label: 'Particulars' },
  { key: 'total_vouchers', label: 'Total Vouchers', align: 'right' },
]

function RegisterTab({ registerKey }) {
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const params = {
    from_date: fromDate || undefined,
    to_date: toDate || undefined,
  }

  const path = `/reports/inventory-register/${registerKey}${toQuery(params)}`
  const { data: response, loading, error } = useFetch(path)

  return (
    <>
      <div className="ledger-filters filter-bar">
        <div className="form-field form-field--date">
          <label htmlFor={`${registerKey}-from`}>From Date</label>
          <input
            id={`${registerKey}-from`}
            type="date"
            value={fromDate}
            onChange={(event) => setFromDate(event.target.value)}
          />
        </div>
        <div className="form-field form-field--date">
          <label htmlFor={`${registerKey}-to`}>To Date</label>
          <input
            id={`${registerKey}-to`}
            type="date"
            value={toDate}
            onChange={(event) => setToDate(event.target.value)}
          />
        </div>
      </div>

      {loading && <Loader />}
      {error && <ErrorMessage message={error} />}

      {!loading && !error && response && !response.success && (
        <ErrorMessage message={response.error || response.message} />
      )}

      {!loading && !error && response?.success && (
        <>
          <div className="card-toolbar">
            <ExportButtons
              basePath={`/reports/inventory-register/${registerKey}/export`}
              params={params}
              filenameBase={registerKey.replace(/-/g, '_')}
            />
          </div>

          <DataTable columns={REGISTER_COLUMNS} rows={response.report || []} />

          <div className="table-footer">
            <span>Grand Total: {response.grand_total ?? 0}</span>
            {response.grand_total_cancelled > 0 && (
              <span> &nbsp;({response.grand_total_cancelled} cancelled)</span>
            )}
          </div>
        </>
      )}
    </>
  )
}

// Tally's exact register names -> the backend's URL key.
const REGISTERS = [
  { key: 'sales-orders', label: 'Sales Orders Book' },
  { key: 'purchase-orders', label: 'Purchase Orders Book' },
  { key: 'delivery-note', label: 'Delivery Note Register' },
  { key: 'receipt-note', label: 'Receipt Note Register' },
  { key: 'rejections-in', label: 'Rejections In Register' },
  { key: 'rejections-out', label: 'Rejections Out Register' },
  { key: 'stock-journal', label: 'Stock Transfer Journal Register' },
  { key: 'physical-stock', label: 'Physical Stock Register' },
  { key: 'material-out', label: 'Material Out Register' },
  { key: 'material-in', label: 'Material In Register' },
]

// ------------------------------------------------------------------
// Stock Item (Summary)
// ------------------------------------------------------------------

const STOCK_SUMMARY_COLUMNS = [
  { key: 'stock_item', label: 'Stock Item' },
  { key: 'stock_group', label: 'Stock Group' },
  { key: 'unit', label: 'Unit' },
  { key: 'opening_quantity', label: 'Opening Qty', align: 'right', render: (r) => formatQuantity(r.opening_quantity) },
  { key: 'opening_value', label: 'Opening Value', align: 'right', render: (r) => formatCurrency(r.opening_value) },
  { key: 'closing_quantity', label: 'Closing Qty', align: 'right', render: (r) => formatQuantity(r.closing_quantity) },
  { key: 'closing_rate', label: 'Closing Rate', align: 'right', render: (r) => formatCurrency(r.closing_rate) },
  { key: 'closing_value', label: 'Closing Value', align: 'right', render: (r) => formatCurrency(r.closing_value) },
]

function StockSummaryTab() {
  const [toDate, setToDate] = useState('')
  const params = { to_date: toDate || undefined }

  return (
    <>
      <DateFilter label="As on Date" value={toDate} onChange={setToDate} />
      <ReportBody
        path={`/reports/stock-summary${toQuery(params)}`}
        columns={STOCK_SUMMARY_COLUMNS}
        exportBasePath="/reports/stock-summary/export"
        exportParams={params}
        filenameBase="stock_summary"
        footer={(rows) => {
          const totalValue = rows.reduce((sum, row) => sum + (Number(row.closing_value) || 0), 0)
          return (
            <div className="table-footer">
              <span>Total Closing Value: {formatCurrency(totalValue)}</span>
            </div>
          )
        }}
      />
    </>
  )
}

// ------------------------------------------------------------------
// Stock Group Summary
// ------------------------------------------------------------------

const STOCK_GROUP_COLUMNS = [
  { key: 'stock_group', label: 'Stock Group' },
  { key: 'parent', label: 'Parent' },
  { key: 'base_units', label: 'Base Units' },
]

function StockGroupsTab() {
  return (
    <ReportBody
      path="/reports/stock-groups"
      columns={STOCK_GROUP_COLUMNS}
      exportBasePath="/reports/stock-groups/export"
      exportParams={{}}
      filenameBase="stock_group_summary"
    />
  )
}

// ------------------------------------------------------------------
// Stock Category Summary
// ------------------------------------------------------------------

const STOCK_CATEGORY_COLUMNS = [
  { key: 'stock_category', label: 'Stock Category' },
  { key: 'parent', label: 'Parent' },
]

function StockCategoriesTab() {
  return (
    <ReportBody
      path="/reports/stock-categories"
      columns={STOCK_CATEGORY_COLUMNS}
      exportBasePath="/reports/stock-categories/export"
      exportParams={{}}
      filenameBase="stock_category_summary"
    />
  )
}

// ------------------------------------------------------------------
// Locations (Godowns)
// ------------------------------------------------------------------

const GODOWN_COLUMNS = [
  { key: 'godown', label: 'Godown' },
  { key: 'parent', label: 'Parent' },
  { key: 'is_internal', label: 'Internal', render: (r) => (r.is_internal ? 'Yes' : 'No') },
]

function GodownsTab() {
  return (
    <ReportBody
      path="/reports/godowns"
      columns={GODOWN_COLUMNS}
      exportBasePath="/reports/godowns/export"
      exportParams={{}}
      filenameBase="locations"
    />
  )
}

// ------------------------------------------------------------------
// Stock Movement (additional report, not in the Tally menu)
// ------------------------------------------------------------------

const STOCK_MOVEMENT_COLUMNS = [
  { key: 'date', label: 'Date' },
  { key: 'stock_item', label: 'Stock Item' },
  { key: 'voucher_type', label: 'Vch Type' },
  { key: 'voucher_number', label: 'Vch No.' },
  { key: 'party', label: 'Party' },
  { key: 'quantity', label: 'Quantity', render: (r) => formatQuantity(r.quantity) },
  { key: 'rate', label: 'Rate', render: (r) => formatCurrency(r.rate) },
  { key: 'value', label: 'Value', render: (r) => formatCurrency(r.value) },
  { key: 'direction', label: 'Movement' },
]

function StockMovementTab() {
  const [fromDate, setFromDate] = useState('')
  const [toDate, setToDate] = useState('')
  const [stockItemInput, setStockItemInput] = useState('')
  const [selectionError, setSelectionError] = useState(null)
  const [filters, setFilters] = useState(null)

  const params = filters
    ? {
        from_date: filters.from || undefined,
        to_date: filters.to || undefined,
        stock_item_name: filters.stockItem || undefined,
      }
    : {}

  const path = filters ? `/reports/stock-movement${toQuery(params)}` : null

  function handleSubmit(event) {
    event.preventDefault()

    if (fromDate && toDate && fromDate > toDate) {
      setSelectionError('From date cannot be later than to date.')
      return
    }

    setSelectionError(null)
    setFilters({
      from: fromDate || null,
      to: toDate || null,
      stockItem: stockItemInput.trim() || null,
    })
  }

  return (
    <>
      <form className="ledger-filters filter-bar" onSubmit={handleSubmit}>
        <div className="form-field">
          <label htmlFor="movement-item">Stock Item (optional)</label>
          <input
            id="movement-item"
            value={stockItemInput}
            onChange={(event) => setStockItemInput(event.target.value)}
            placeholder="e.g. Steel Rod 10mm"
            autoComplete="off"
          />
        </div>

        <div className="form-field form-field--date">
          <label htmlFor="movement-from">From Date</label>
          <input
            id="movement-from"
            type="date"
            value={fromDate}
            onChange={(event) => setFromDate(event.target.value)}
          />
        </div>

        <div className="form-field form-field--date">
          <label htmlFor="movement-to">To Date</label>
          <input
            id="movement-to"
            type="date"
            value={toDate}
            onChange={(event) => setToDate(event.target.value)}
          />
        </div>

        <button type="submit" className="btn">View Movement</button>
      </form>

      {selectionError && (
        <p className="selection-error">
          <AlertCircle size={16} />
          {selectionError}
        </p>
      )}

      {!filters && (
        <div className="empty-state">
          <PackageSearch size={28} strokeWidth={1.5} />
          <span>Choose a date range and/or stock item, then click "View Movement".</span>
        </div>
      )}

      {filters && (
        <ReportBody
          path={path}
          columns={STOCK_MOVEMENT_COLUMNS}
          exportBasePath="/reports/stock-movement/export"
          exportParams={params}
          filenameBase="stock_movement"
        />
      )}
    </>
  )
}

// ------------------------------------------------------------------
// Stock Valuation (additional report, not in the Tally menu)
// ------------------------------------------------------------------

const STOCK_VALUATION_COLUMNS = [
  { key: 'stock_item', label: 'Stock Item' },
  { key: 'unit', label: 'Unit' },
  { key: 'closing_quantity', label: 'Closing Qty', render: (r) => formatQuantity(r.closing_quantity) },
  { key: 'valuation_rate', label: 'Valuation Rate', render: (r) => formatCurrency(r.valuation_rate) },
  { key: 'valuation_value', label: 'Valuation Value', render: (r) => formatCurrency(r.valuation_value) },
]

function StockValuationTab() {
  const [toDate, setToDate] = useState('')
  const params = { to_date: toDate || undefined }

  return (
    <>
      <DateFilter label="As on Date" value={toDate} onChange={setToDate} />
      <ReportBody
        path={`/reports/stock-valuation${toQuery(params)}`}
        columns={STOCK_VALUATION_COLUMNS}
        exportBasePath="/reports/stock-valuation/export"
        exportParams={params}
        filenameBase="stock_valuation"
        footer={(rows) => {
          const totalValue = rows.reduce((sum, row) => sum + (Number(row.valuation_value) || 0), 0)
          return (
            <div className="table-footer">
              <span>Total Valuation: {formatCurrency(totalValue)}</span>
            </div>
          )
        }}
      />
    </>
  )
}

// ------------------------------------------------------------------
// Negative Stock (additional report, not in the Tally menu)
// ------------------------------------------------------------------

const NEGATIVE_STOCK_COLUMNS = [
  { key: 'stock_item', label: 'Stock Item' },
  { key: 'stock_group', label: 'Stock Group' },
  { key: 'unit', label: 'Unit' },
  { key: 'closing_quantity', label: 'Closing Qty', render: (r) => formatQuantity(r.closing_quantity) },
  { key: 'closing_rate', label: 'Closing Rate', render: (r) => formatCurrency(r.closing_rate) },
  { key: 'closing_value', label: 'Closing Value', render: (r) => formatCurrency(r.closing_value) },
]

function NegativeStockTab() {
  const [toDate, setToDate] = useState('')
  const params = { to_date: toDate || undefined }

  return (
    <>
      <DateFilter label="As on Date" value={toDate} onChange={setToDate} />
      <ReportBody
        path={`/reports/negative-stock${toQuery(params)}`}
        columns={NEGATIVE_STOCK_COLUMNS}
        exportBasePath="/reports/negative-stock/export"
        exportParams={params}
        filenameBase="negative_stock"
      />
    </>
  )
}

// ------------------------------------------------------------------
// Small shared "as on date" filter used by several tabs
// ------------------------------------------------------------------

function DateFilter({ label, value, onChange }) {
  return (
    <div className="ledger-filters filter-bar">
      <div className="form-field form-field--date">
        <label htmlFor="inventory-as-on-date">{label}</label>
        <input
          id="inventory-as-on-date"
          type="date"
          value={value}
          onChange={(event) => onChange(event.target.value)}
        />
      </div>
    </div>
  )
}

// ------------------------------------------------------------------
// Tabs shell
// ------------------------------------------------------------------

// Matches the Inventory Books menu shown in the provided Tally screenshot.
// Summary reports first, followed by the Inventory Books registers in order.
const TABS = [
  // -- Summary --
  { key: 'stock-item', label: 'Stock Item', Component: StockSummaryTab },
  { key: 'locations', label: 'Locations', Component: GodownsTab },
  { key: 'stock-group-summary', label: 'Stock Group Summary', Component: StockGroupsTab },
  { key: 'stock-category-summary', label: 'Stock Category Summary', Component: StockCategoriesTab },

  // -- Registers --
  ...REGISTERS.map((register) => ({
    key: register.key,
    label: register.label,
    Component: () => <RegisterTab registerKey={register.key} />,
  })),

]

function Inventory() {
  const [activeTab, setActiveTab] = useState(TABS[0].key)

  const ActiveComponent = useMemo(
    () => TABS.find((tab) => tab.key === activeTab)?.Component,
    [activeTab]
  )

  return (
    <>
      <PageHeader
        title="Inventory Books"
        subtitle="Summary and Registers, straight from Tally's Inventory Books menu"
      />

      <div className="inventory-tabs" role="tablist" aria-label="Inventory reports">
        <span className="tab-group-label">Summary</span>
        {TABS.map((tab) => (
          <Fragment key={tab.key}>
            {tab.key === REGISTERS[0].key && (
              <>
                <span className="tab-divider" aria-hidden="true" />
                <span className="tab-group-label">Registers</span>
              </>
            )}
            <button
              type="button"
              role="tab"
              aria-selected={tab.key === activeTab}
              className={
                tab.key === activeTab
                  ? 'inventory-tab inventory-tab--active'
                  : 'inventory-tab'
              }
              onClick={() => setActiveTab(tab.key)}
            >
              {tab.label}
            </button>
          </Fragment>
        ))}
      </div>

      <Card>{ActiveComponent && <ActiveComponent />}</Card>
    </>
  )
}

export default Inventory