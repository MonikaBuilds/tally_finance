import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import ExportButtons from '../components/common/ExportButtons'
import { formatCurrency } from '../utils/format'

const COLUMNS = [
  { key: 'name', label: 'Ledger' },
  { key: 'debit', label: 'Debit', align: 'right', render: (row) => formatCurrency(row.debit) },
  { key: 'credit', label: 'Credit', align: 'right', render: (row) => formatCurrency(row.credit) },
]

function TrialBalance() {
  const { data: response, loading, error } = useFetch('/reports/trial-balance')

  if (loading) return <Loader />
  if (error) return <ErrorMessage message={error} />
  if (!response.success) return <ErrorMessage message={response.error || response.message} />

  const report = response.report
  const totalDebit = report.reduce((sum, row) => sum + (row.debit || 0), 0)
  const totalCredit = report.reduce((sum, row) => sum + (row.credit || 0), 0)

  return (
    <>
      <PageHeader
        title="Trial Balance"
        actions={<ExportButtons basePath="/reports/trial-balance/export" filenameBase="trial_balance" />}
      />

      <Card>
        <DataTable columns={COLUMNS} rows={report} />
        <div className="table-footer">
          <span>Total Debit: {formatCurrency(totalDebit)}</span>
          <span>Total Credit: {formatCurrency(totalCredit)}</span>
        </div>
      </Card>
    </>
  )
}

export default TrialBalance