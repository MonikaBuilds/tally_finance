import { useState } from 'react'
import { Plug, RefreshCw, Unplug } from 'lucide-react'

import { useFetch } from '../hooks/useFetch'
import { apiGet } from '../api/client'
import PageHeader from '../components/layout/PageHeader'
import Loader from '../components/common/Loader'
import ErrorMessage from '../components/common/ErrorMessage'
import Card from '../components/common/Card'
import StatusPill from '../components/common/StatusPill'
import DataTable from '../components/common/DataTable'

const COMPANY_COLUMNS = [{ key: 'name', label: 'Company Name' }]

function TallyStatus() {
  const { data: status, loading, error } = useFetch('/tally/status')

  const [companies, setCompanies] = useState(null)
  const [companiesLoading, setCompaniesLoading] = useState(false)

  async function handleFetchCompanies() {
    setCompaniesLoading(true)
    setCompanies(null)

    try {
      const result = await apiGet('/tally/companies')
      setCompanies(result)
    } catch (err) {
      setCompanies({ success: false, error: err.message })
    } finally {
      setCompaniesLoading(false)
    }
  }

  return (
    <>
      <PageHeader
        title="Tally Status"
        subtitle="Connection to your TallyPrime server"
      />

      <Card title="Connection">
        {loading && <Loader />}
        {error && <ErrorMessage message={error} />}
        {status && (
          <div className="status-row">
            <span
              className={
                status.connected
                  ? 'status-icon status-icon--positive'
                  : 'status-icon status-icon--negative'
              }
            >
              {status.connected ? <Plug size={20} /> : <Unplug size={20} />}
            </span>

            <div className="status-copy">
              <div>
                <StatusPill status={status.connected ? 'connected' : 'disconnected'} />
              </div>
              {status.message && <p className="card-note">{status.message}</p>}
              {status.error && <p className="card-note">{status.error}</p>}
            </div>
          </div>
        )}
      </Card>

      <Card
        title="Companies"
        subtitle="Companies currently open in Tally"
        actions={
          <button
            className="btn btn-secondary"
            onClick={handleFetchCompanies}
            disabled={companiesLoading}
          >
            <RefreshCw size={16} className={companiesLoading ? 'spin' : undefined} />
            {companiesLoading ? 'Fetching...' : 'Fetch Companies from Tally'}
          </button>
        }
      >
        {!companies && !companiesLoading && (
          <p className="card-note">
            Fetch the list to see which companies Tally is serving.
          </p>
        )}

        {companiesLoading && <Loader label="Fetching companies…" />}

        {companies && companies.success && (
          <DataTable columns={COMPANY_COLUMNS} rows={companies.companies} />
        )}

        {companies && !companies.success && (
          <ErrorMessage message={companies.error || companies.message} />
        )}
      </Card>
    </>
  )
}

export default TallyStatus
