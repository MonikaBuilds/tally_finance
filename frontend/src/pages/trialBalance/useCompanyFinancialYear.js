import { useMemo } from 'react'
import { useFetch } from '../../hooks/useFetch'
import { financialYearEnd } from '../../hooks/useDefaultAsOnDate'

// Default Trial Balance period = the company's own financial year,
// derived from the books-from date Tally reports for the company (the
// same source useDefaultAsOnDate uses). Nothing here is hardcoded: if
// Tally gives no usable books-from date, `from`/`to` stay empty and the
// Trial Balance is requested without dates (Tally's own default period).
//
// `ready` is false only while the company list is still loading.
export function useCompanyFinancialYear() {
  const { data, loading, error } = useFetch('/tally/companies')

  return useMemo(() => {
    if (loading) return { ready: false, from: '', to: '' }

    const companies = data?.companies

    if (error || !Array.isArray(companies) || companies.length === 0) {
      return { ready: true, from: '', to: '' }
    }

    const selectedName = sessionStorage.getItem('selected_company')
    const company =
      (selectedName &&
        companies.find(
          (c) => c.name?.toLowerCase() === selectedName.toLowerCase()
        )) ||
      companies[0]

    const to = financialYearEnd(company?.books_from)

    if (!to) return { ready: true, from: '', to: '' }

    // Financial year ends 31-Mar, so it started 1-Apr the year before.
    const from = `${Number(to.slice(0, 4)) - 1}-04-01`

    return { ready: true, from, to }
  }, [data, loading, error])
}
