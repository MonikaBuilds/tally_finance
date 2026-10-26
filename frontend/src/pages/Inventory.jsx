import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router'
import { AlertCircle, PackageSearch } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import { useDefaultAsOnDate } from '../hooks/useDefaultAsOnDate'

import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import ExportButtons from '../components/common/ExportButtons'
import { formatCurrency, formatQuantity, financialYearRange } from '../utils/format'
import { formatAmount } from '../utils/stockFormat'

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

function ReportBody({ path, columns, exportBasePath, exportParams, filenameBase, footer, onRowClick }) {
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

      <DataTable columns={columns} rows={report} onRowClick={onRowClick} />

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
  {
    key: 'cancelled_vouchers',
    label: '(cancelled)',
    align: 'right',
    render: (r) => (r.cancelled_vouchers ? r.cancelled_vouchers : ''),
  },
]

function RegisterTab({ registerKey }) {
  const navigate = useNavigate()

  // The period lives in the URL so Back from a month's voucher list
  // returns to the same period. With no dates the backend picks the
  // latest financial year that has stock activity.
  const [searchParams, setSearchParams] = useSearchParams()
  const fromDate = searchParams.get('from') || ''
  const toDate = searchParams.get('to') || ''

  const setPeriod = (key, value) => {
    const next = new URLSearchParams(searchParams)
    if (value) next.set(key, value)
    else next.delete(key)
    setSearchParams(next)
  }
  const setFromDate = (value) => setPeriod('from', value)
  const setToDate = (value) => setPeriod('to', value)

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

          <p className="table-hint">
            {response.from} to {response.to}. Click a month to list its vouchers.
          </p>

          <DataTable
            columns={REGISTER_COLUMNS}
            rows={response.report || []}
            onRowClick={(row) =>
              navigate(
                `/reports/registers/${registerKey}/vouchers${toQuery({
                  from: row.from,
                  to: row.to,
                })}`
              )
            }
          />

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
  { key: 'opening_value', label: 'Opening Value', align: 'right', render: (r) => formatAmount(r.opening_value) },
  { key: 'closing_quantity', label: 'Closing Qty', align: 'right', render: (r) => formatQuantity(r.closing_quantity) },
  { key: 'closing_rate', label: 'Closing Rate', align: 'right', render: (r) => formatAmount(r.closing_rate) },
  { key: 'closing_value', label: 'Closing Value', align: 'right', render: (r) => formatAmount(r.closing_value) },
]

function StockSummaryTab() {
  const navigate = useNavigate()
  const [toDate, setToDate] = useState('')
  const [touched, setTouched] = useState(false)
  const { date: defaultAsOnDate } = useDefaultAsOnDate()

  // Prefill with the end of the company's current financial year (once
  // we know it) so the report isn't silently run "as on" today's date,
  // which is often past the end of the period that actually has data.
  useEffect(() => {
    if (!touched && defaultAsOnDate && !toDate) {
      setToDate(defaultAsOnDate)
    }
  }, [defaultAsOnDate, touched, toDate])

  // The financial year containing the "as on" date, so Tally computes
  // opening figures from that year's start rather than its own default.
  const params = {
    from_date: toDate ? financialYearRange(0, new Date(toDate)).from : undefined,
    to_date: toDate || undefined,
  }

  return (
    <>
      <DateFilter
        label="As on Date"
        value={toDate}
        onChange={(value) => {
          setTouched(true)
          setToDate(value)
        }}
      />
      <p className="table-hint">Click a stock item to view its Stock Monthly Summary.</p>
      <ReportBody
        path={`/reports/stock-summary${toQuery(params)}`}
        columns={STOCK_SUMMARY_COLUMNS}
        exportBasePath="/reports/stock-summary/export"
        exportParams={params}
        filenameBase="stock_summary"
        onRowClick={(row) => {
          // Anchor the monthly-summary drill-down to the financial year
          // that contains the "As on Date" the user actually picked here,
          // instead of letting that page default to *today's* real-world
          // financial year (which, once you're past year-end, is a year
          // with no data at all).
          const anchor = toDate ? financialYearRange(0, new Date(toDate)) : null
          navigate(
            `/reports/stock-item-monthly${toQuery({
              item: row.stock_item,
              from: anchor?.from,
              to: anchor?.to,
            })}`
          )
        }}
        footer={(rows) => {
          const totalValue = rows.reduce((sum, row) => sum + (Number(row.closing_value) || 0), 0)
          return (
            <div className="table-footer">
              <span>Total Closing Value: {formatAmount(totalValue)}</span>
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

// Tally lists its implicit "Primary" root first, shown as "♦ Primary".
const masterName = (name, isPrimary) => (isPrimary ? `♦ ${name}` : name)

const STOCK_GROUP_COLUMNS = [
  { key: 'stock_group', label: 'Stock Group', render: (r) => masterName(r.stock_group, r.is_primary) },
  { key: 'parent', label: 'Parent' },
  { key: 'base_units', label: 'Base Units' },
]

function StockGroupsTab() {
  const navigate = useNavigate()

  return (
    <>
      <p className="table-hint">Click a stock group to open its Stock Group Summary.</p>
      <ReportBody
        path="/reports/stock-groups"
        columns={STOCK_GROUP_COLUMNS}
        exportBasePath="/reports/stock-groups/export"
        exportParams={{}}
        filenameBase="stock_group_summary"
        onRowClick={(row) =>
          navigate(`/reports/stock-groups/${encodeURIComponent(row.stock_group)}`)
        }
      />
    </>
  )
}

// ------------------------------------------------------------------
// Stock Category Summary
// ------------------------------------------------------------------

const STOCK_CATEGORY_COLUMNS = [
  { key: 'stock_category', label: 'Stock Category', render: (r) => masterName(r.stock_category, r.is_primary) },
  { key: 'parent', label: 'Parent' },
]

function StockCategoriesTab() {
  const navigate = useNavigate()

  return (
    <>
      <p className="table-hint">Click a stock category to open its Stock Category Summary.</p>
      <ReportBody
        path="/reports/stock-categories"
        columns={STOCK_CATEGORY_COLUMNS}
        exportBasePath="/reports/stock-categories/export"
        exportParams={{}}
        filenameBase="stock_category_summary"
        onRowClick={(row) =>
          navigate(`/reports/stock-categories/${encodeURIComponent(row.stock_category)}`)
        }
      />
    </>
  )
}

// ------------------------------------------------------------------
// Locations (Godowns)
// ------------------------------------------------------------------

const GODOWN_COLUMNS = [
  { key: 'godown', label: 'Godown', render: (r) => masterName(r.godown, r.is_primary) },
  { key: 'parent', label: 'Parent' },
  { key: 'is_internal', label: 'Internal', render: (r) => (r.is_primary ? '' : r.is_internal ? 'Yes' : 'No') },
]

function GodownsTab() {
  const navigate = useNavigate()

  return (
    <>
      <p className="table-hint">Click a godown to open its Godown Summary.</p>
      <ReportBody
        path="/reports/godowns"
        columns={GODOWN_COLUMNS}
        exportBasePath="/reports/godowns/export"
        exportParams={{}}
        filenameBase="godowns"
        onRowClick={(row) =>
          navigate(`/reports/godowns/${encodeURIComponent(row.godown)}`)
        }
      />
    </>
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
  const [touched, setTouched] = useState(false)
  const { date: defaultAsOnDate } = useDefaultAsOnDate()

  useEffect(() => {
    if (!touched && defaultAsOnDate && !toDate) {
      setToDate(defaultAsOnDate)
    }
  }, [defaultAsOnDate, touched, toDate])

  const params = { to_date: toDate || undefined }

  return (
    <>
      <DateFilter
        label="As on Date"
        value={toDate}
        onChange={(value) => {
          setTouched(true)
          setToDate(value)
        }}
      />
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
  const [touched, setTouched] = useState(false)
  const { date: defaultAsOnDate } = useDefaultAsOnDate()

  useEffect(() => {
    if (!touched && defaultAsOnDate && !toDate) {
      setToDate(defaultAsOnDate)
    }
  }, [defaultAsOnDate, touched, toDate])

  const params = { to_date: toDate || undefined }

  return (
    <>
      <DateFilter
        label="As on Date"
        value={toDate}
        onChange={(value) => {
          setTouched(true)
          setToDate(value)
        }}
      />
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
  { key: 'godowns', label: 'Godowns', Component: GodownsTab },
  { key: 'stock-group-summary', label: 'Stock Group Summary', Component: StockGroupsTab },
  { key: 'stock-category-summary', label: 'Stock Category Summary', Component: StockCategoriesTab },

  // -- Registers --
  ...REGISTERS.map((register) => ({
    key: register.key,
    label: register.label,
    Component: () => <RegisterTab registerKey={register.key} />,
  })),

]

const TAB_GROUPS = [
  { label: 'Summary', tabs: TABS.filter((tab) => !REGISTERS.some((r) => r.key === tab.key)) },
  { label: 'Registers', tabs: TABS.filter((tab) => REGISTERS.some((r) => r.key === tab.key)) },
]

function Inventory() {
  // The tab lives in the URL (?tab=godowns) so Back from a drill-down
  // lands on the list the user came from instead of the first tab.
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedTab = searchParams.get('tab')
  const activeTab = TABS.some((tab) => tab.key === requestedTab) ? requestedTab : TABS[0].key
  const setActiveTab = (key) => setSearchParams({ tab: key })

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

      {/* One row per group with its label; tabs wrap instead of
          scrolling so every register stays visible. */}
      <div className="inventory-tabs" role="tablist" aria-label="Inventory reports">
        {TAB_GROUPS.map((group) => (
          <div key={group.label} className="inventory-tab-group" role="presentation">
            <span className="tab-group-label" id={`tab-group-${group.label}`}>
              {group.label}
            </span>
            <div
              className="inventory-tab-list"
              role="group"
              aria-labelledby={`tab-group-${group.label}`}
            >
              {group.tabs.map((tab) => (
                <button
                  key={tab.key}
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
              ))}
            </div>
          </div>
        ))}
      </div>

      <Card>{ActiveComponent && <ActiveComponent />}</Card>
    </>
  )
}

export default Inventory