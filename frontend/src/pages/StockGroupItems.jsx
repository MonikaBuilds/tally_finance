import { useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import ExportButtons from '../components/common/ExportButtons'
import { formatCurrency, formatQuantity } from '../utils/format'

function toQuery(params) {
  const query = new URLSearchParams(
    Object.entries(params).filter(([, v]) => v !== undefined && v !== null && v !== '')
  ).toString()
  return query ? `?${query}` : ''
}

const COLUMNS = [
  { key: 'stock_item', label: 'Stock Item' },
  { key: 'unit', label: 'Unit' },
  { key: 'opening_quantity', label: 'Opening Qty', align: 'right', render: (r) => formatQuantity(r.opening_quantity) },
  { key: 'opening_value', label: 'Opening Value', align: 'right', render: (r) => formatCurrency(r.opening_value) },
  { key: 'closing_quantity', label: 'Closing Qty', align: 'right', render: (r) => formatQuantity(r.closing_quantity) },
  { key: 'closing_rate', label: 'Closing Rate', align: 'right', render: (r) => formatCurrency(r.closing_rate) },
  { key: 'closing_value', label: 'Closing Value', align: 'right', render: (r) => formatCurrency(r.closing_value) },
]

/*
 * Stock Group Summary -> (click a group) -> the items inside that
 * group, i.e. a Stock Summary scoped to a single Stock Group.
 * Clicking an item continues into its Stock Item Monthly Summary,
 * the same page reached from the plain Stock Summary tab.
 */
function StockGroupItems() {
  const location = useLocation()
  const navigate = useNavigate()
  const params = new URLSearchParams(location.search)

  const groupName = params.get('group') || ''
  const toDate = params.get('to_date') || ''

  const queryParams = { group: groupName || undefined, to_date: toDate || undefined }
  const path = groupName ? `/reports/stock-group-items${toQuery(queryParams)}` : null
  const { data: response, loading, error } = useFetch(path)

  return (
    <>
      <PageHeader
        title={`Stock Group: ${groupName || ''}`}
        subtitle="Items belonging to this stock group"
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} /> Back
          </button>
        }
      />

      <Card>
        {!groupName && <ErrorMessage message="No stock group was specified." />}
        {groupName && loading && <Loader />}
        {groupName && error && <ErrorMessage message={error} />}

        {groupName && !loading && !error && response?.success && (
          <>
            <div className="card-toolbar">
              <ExportButtons
                basePath="/reports/stock-group-items/export"
                params={queryParams}
                filenameBase={`stock_group_${groupName.replace(/\s+/g, '_')}`}
              />
            </div>

            <p className="table-hint">Click a stock item to view its Stock Monthly Summary.</p>

            <DataTable
              columns={COLUMNS}
              rows={response.report || []}
              onRowClick={(row) =>
                navigate(`/reports/stock-item-monthly?item=${encodeURIComponent(row.stock_item)}`)
              }
            />
          </>
        )}
      </Card>
    </>
  )
}

export default StockGroupItems
