import { useFetch } from '../hooks/useFetch'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import DataTable from '../components/common/DataTable'

function PurchaseBill() {
  const {
    data: response,
    loading,
    error,
  } = useFetch('/reports/bill-allocations')

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

  const rows =
    response.bills ||
    response.rows ||
    []

  const columns = [
    {
      key: 'date',
      label: 'Date',
    },
    {
      key: 'party_ledger_name',
      label: 'Party Ledger',
    },
    {
      key: 'party_name',
      label: 'Party',
    },
    {
      key: 'voucher_type',
      label: 'Voucher Type',
    },
    {
      key: 'voucher_number',
      label: 'Voucher No.',
    },
    {
      key: 'reference',
      label: 'Reference',
    },
    {
      key: 'narration',
      label: 'Narration',
    },
  ]

  return (
    <>
      <PageHeader
        title="Purchase Bill"
        subtitle="Purchase bill data fetched from Tally"
      />

      <Card title="Purchase Bill">
        <DataTable
          columns={columns}
          rows={rows}
        />
      </Card>
    </>
  )
}

export default PurchaseBill