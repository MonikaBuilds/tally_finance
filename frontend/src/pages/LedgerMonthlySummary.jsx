import { useMemo } from 'react'
import { useLocation } from 'react-router'
import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import { formatCurrency } from '../utils/format'

function monthKeyForDate(dateStr) {
  if (!dateStr) return null

  const value = String(dateStr).trim()

  if (/^\d{4}-\d{2}-\d{2}/.test(value)) {
    return value.slice(0, 7)
  }

  const dash = value.match(
    /^(\d{2})-(\d{2})-(\d{4})$/
  )

  if (dash) {
    return `${dash[3]}-${dash[2]}`
  }

  const slash = value.match(
    /^(\d{2})\/(\d{2})\/(\d{4})$/
  )

  if (slash) {
    return `${slash[3]}-${slash[2]}`
  }

  return null
}

function monthLabel(key) {
  if (!key) return ''

  const [year, month] = key.split('-')

  const names = [
    'Jan',
    'Feb',
    'Mar',
    'Apr',
    'May',
    'Jun',
    'Jul',
    'Aug',
    'Sep',
    'Oct',
    'Nov',
    'Dec',
  ]

  const number = Number(month)

  if (number < 1 || number > 12) {
    return key
  }

  return `${names[number - 1]}-${year}`
}

function LedgerMonthlySummary() {
  const location = useLocation()

  const params = new URLSearchParams(
    location.search
  )

  const ledgerName =
    params.get('ledger_name') || ''

  const path = ledgerName
    ? `/reports/ledger?ledger_name=${encodeURIComponent(
        ledgerName
      )}`
    : null

  const {
    data: response,
    loading,
    error,
  } = useFetch(path)

  const monthlyRows = useMemo(() => {
    const entries = Array.isArray(
      response?.report?.entries
    )
      ? response.report.entries
      : []

    const buckets = new Map()

    for (const entry of entries) {
      const key = monthKeyForDate(entry.date)

      if (!key) continue

      if (!buckets.has(key)) {
        buckets.set(key, {
          key,
          month: monthLabel(key),
          debit: 0,
          credit: 0,
          closing_balance: null,
        })
      }

      const bucket = buckets.get(key)

      bucket.debit +=
        Number(entry.debit) || 0

      bucket.credit +=
        Number(entry.credit) || 0

      if (
        entry.running_balance !== undefined &&
        entry.running_balance !== null
      ) {
        bucket.closing_balance =
          Number(entry.running_balance) || 0
      }
    }

    return Array.from(
      buckets.values()
    ).sort((a, b) =>
      a.key.localeCompare(b.key)
    )
  }, [response])

  if (loading) return <Loader />

  if (error) {
    return <ErrorMessage message={error} />
  }

  if (!response?.success) {
    return (
      <ErrorMessage
        message={response?.error || response?.message}
      />
    )
  }

  const report = response.report || {}

  const columns = [
    {
      key: 'month',
      label: 'Particulars',
    },
    {
      key: 'debit',
      label: 'Debit',
      render: (row) =>
        formatCurrency(row.debit),
    },
    {
      key: 'credit',
      label: 'Credit',
      render: (row) =>
        formatCurrency(row.credit),
    },
    {
      key: 'closing_balance',
      label: 'Closing Balance',
      render: (row) =>
        formatCurrency(row.closing_balance),
    },
  ]

  return (
    <>
      <PageHeader
        title="Ledger Monthly Summary"
        subtitle={`Ledger: ${
          report.ledger_name || ledgerName
        }`}
      />

      <Card
        title={
          report.ledger_name || ledgerName
        }
      >
        <DataTable
          columns={columns}
          rows={monthlyRows}
        />

        <div className="table-footer">
          <span>Opening Balance</span>
          <span>
            {formatCurrency(
              report.opening_balance
            )}
          </span>
        </div>
      </Card>
    </>
  )
}

export default LedgerMonthlySummary