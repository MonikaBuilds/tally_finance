import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'
import ExportButtons from '../components/common/ExportButtons'
import { formatCurrency } from '../utils/format'

const COLUMNS = [
  { key: 'name', label: 'Account' },
  { key: 'amount', label: 'Amount', align: 'right', render: (row) => formatCurrency(row.amount) },
]

function BalanceSheet() {
  const { data: response, loading, error } = useFetch('/reports/balance-sheet')

  if (loading) return <Loader />
  if (error) return <ErrorMessage message={error} />
  if (!response.success) return <ErrorMessage message={response.error || response.message} />

  return (
    <>
      <PageHeader
        title="Balance Sheet"
        actions={<ExportButtons basePath="/reports/balance-sheet/export" filenameBase="balance_sheet" />}
      />

      <Card>
        <DataTable columns={COLUMNS} rows={response.report} />
      </Card>
    </>
  )
}

export default BalanceSheet