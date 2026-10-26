import { useMemo, useState } from 'react'
import { useNavigate, useParams, useSearchParams } from 'react-router'
import { ArrowLeft } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import { useCompanyFinancialYear } from './trialBalance/useCompanyFinancialYear'
import { formatAmount, formatQuantityWithUnit, toQuery } from '../utils/stockFormat'

/*
 * One page for the three Tally "<X> Summary" screens that share the same
 * shape - a Primary-rooted tree whose leaves are stock items:
 *
 *   /reports/stock-groups/:name      Stock Group Summary
 *   /reports/stock-categories/:name  Stock Category Summary
 *   /reports/godowns/:name           Godown Summary
 *
 * `name` is whatever was picked in the list (Primary included). Clicking
 * a child group / category / godown goes one level deeper on the same
 * route; clicking a stock item continues to its monthly summary.
 * Everything shown comes from the backend (which gets it from Tally).
 */

const KINDS = {
  group: {
    title: 'Stock Group Summary',
    api: '/reports/stock-group-summary',
    param: 'group',
    base: '/reports/stock-groups',
    tab: 'stock-group-summary',
    itemRoute: (item, period) =>
      `/reports/stock-item-monthly${toQuery({ item, ...period })}`,
  },
  category: {
    title: 'Stock Category Summary',
    api: '/reports/stock-category-summary',
    param: 'category',
    base: '/reports/stock-categories',
    tab: 'stock-category-summary',
    itemRoute: (item, period) =>
      `/reports/stock-item-monthly${toQuery({ item, ...period })}`,
  },
  godown: {
    title: 'Godown Summary',
    api: '/reports/godown-summary',
    param: 'godown',
    base: '/reports/godowns',
    tab: 'godowns',
    // Godown Monthly Summary is scoped to the godown being viewed.
    itemRoute: (item, period, selected) =>
      `/reports/location-monthly${toQuery({ location: selected, item, ...period })}`,
  },
}

function StockSummaryDrill({ kind }) {
  const config = KINDS[kind]
  const navigate = useNavigate()
  const { name } = useParams()
  const [searchParams] = useSearchParams()
  const [includeZero, setIncludeZero] = useState(false)

  // Period: explicit ?from/?to when we arrived from another drill-down,
  // otherwise the company's own financial year as reported by Tally.
  const companyYear = useCompanyFinancialYear()
  const from = searchParams.get('from') || companyYear.from
  const to = searchParams.get('to') || companyYear.to
  const periodReady = Boolean(searchParams.get('to')) || companyYear.ready

  const path = periodReady
    ? `${config.api}${toQuery({
        [config.param]: name,
        from_date: from,
        to_date: to,
        include_zero: includeZero ? 'true' : undefined,
      })}`
    : null

  const { data: response, loading, error } = useFetch(path)

  const rows = useMemo(
    () => (Array.isArray(response?.report) ? response.report : []),
    [response]
  )
  const selected = response?.selected || name
  const totals = response?.totals
  const period = { from, to }

  const columns = [
    {
      key: 'name',
      label: 'Particulars',
      render: (row) => (row.kind === 'item' ? row.name : `${row.name} ▸`),
    },
    {
      key: 'closing_quantity',
      label: 'Closing Quantity',
      align: 'right',
      render: (row) => formatQuantityWithUnit(row.closing_quantity, row.unit),
    },
    {
      key: 'closing_rate',
      label: 'Rate',
      align: 'right',
      render: (row) => (row.closing_rate ? formatAmount(row.closing_rate) : ''),
    },
    {
      key: 'closing_value',
      label: 'Value',
      align: 'right',
      render: (row) => formatAmount(row.closing_value),
    },
  ]

  function openRow(row) {
    if (row.kind === 'item') {
      navigate(config.itemRoute(row.name, period, selected))
      return
    }

    // A child group / category / godown: same page, one level down.
    navigate(`${config.base}/${encodeURIComponent(row.name)}${toQuery(period)}`)
  }

  return (
    <>
      <PageHeader
        title={`${config.title}: ${selected || ''}`}
        subtitle={from && to ? `${from} to ${to}` : undefined}
        actions={
          <button type="button" className="btn btn-secondary" onClick={() => navigate(-1)}>
            <ArrowLeft size={16} /> Back
          </button>
        }
      />

      <Card>
        <div className="ledger-filters filter-bar">
          <label className="form-field">
            <span>
              <input
                type="checkbox"
                checked={includeZero}
                onChange={(event) => setIncludeZero(event.target.checked)}
              />{' '}
              Show zero balances
            </span>
          </label>
        </div>

        {loading && <Loader />}
        {error && <ErrorMessage message={error} />}

        {!loading && !error && response && !response.success && (
          <ErrorMessage message={response.error || response.message} />
        )}

        {!loading && !error && response?.success && (
          <>
            <p className="table-hint">
              Click a {kind === 'godown' ? 'godown' : kind} to open it, or a stock item to view its
              monthly summary.
            </p>

            <DataTable columns={columns} rows={rows} onRowClick={openRow} />

            <div className="table-footer">
              <span>
                Grand Total: {formatQuantityWithUnit(totals?.closing_quantity, totals?.unit)} ·{' '}
                {formatAmount(totals?.closing_value)}
              </span>
              {rows.some((row) => row.approximate) && (
                <span>
                  {' '}
                  · Some items are held in more than one godown; their per-godown figures are
                  worked out from vouchers at the item's closing rate.
                </span>
              )}
            </div>
          </>
        )}
      </Card>
    </>
  )
}

export default StockSummaryDrill
