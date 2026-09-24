import { useMemo } from 'react'
import { useFetch } from './useFetch'

// ------------------------------------------------------------------
// Default "As on Date" for inventory reports (Stock Item, Stock
// Valuation, Negative Stock).
//
// Why this exists: those reports call Tally's "Stock Summary" style
// collection. If no SVTODATE is sent, Tally falls back to its own
// current system date - which, once you're past the end of the
// active financial year, falls *outside* the period that actually
// has data and silently returns an empty report (no error, just
// "No records found").
//
// To avoid that trap we default the date picker to the last day of
// the company's current financial year (booked from BOOKSFROM,
// assuming the standard Apr-Mar Indian financial year), computed
// from Tally's own company data. The user can still override it.
// ------------------------------------------------------------------

function toISODate(d) {
  return d.toISOString().slice(0, 10)
}

// Given a books-from date (YYYY-MM-DD, the start of the company's
// current financial year), return the last day of that financial
// year as YYYY-MM-DD. Indian financial years run 1 April - 31 March.
export function financialYearEnd(booksFromISO) {
  if (!booksFromISO) return null

  const booksFrom = new Date(booksFromISO)
  if (Number.isNaN(booksFrom.getTime())) return null

  const month = booksFrom.getUTCMonth() // 0 = Jan, 3 = Apr
  const year = booksFrom.getUTCFullYear()

  // Books opened in Apr-Dec -> year ends in March of next year.
  // Books opened in Jan-Mar -> already inside the FY that ends this year.
  const endYear = month >= 3 ? year + 1 : year

  // Day 0 of April = 31 March.
  return toISODate(new Date(Date.UTC(endYear, 3, 0)))
}

// Fetches the active company's books-from date and derives a sane
// default "as on" date from it. `date` is null while loading/unknown,
// in which case callers should just leave the date picker blank.
//
// Also returns `debug`, a plain-English status string, so this can be
// diagnosed on-screen on machines where DevTools isn't available.
export function useDefaultAsOnDate() {
  const { data, loading, error } = useFetch('/tally/companies')

  return useMemo(() => {
    if (loading) {
      return { date: null, debug: 'Loading companies from /tally/companies…' }
    }

    if (error) {
      return { date: null, debug: `Error calling /tally/companies: ${error}` }
    }

    const companies = data?.companies

    if (!Array.isArray(companies) || companies.length === 0) {
      return {
        date: null,
        debug: `/tally/companies returned no companies. Raw response: ${JSON.stringify(
          data
        )}`,
      }
    }

    const selectedName = sessionStorage.getItem('selected_company')
    const company =
      (selectedName &&
        companies.find(
          (c) => c.name?.toLowerCase() === selectedName.toLowerCase()
        )) ||
      companies[0]

    const date = financialYearEnd(company?.books_from)

    if (!date) {
      return {
        date: null,
        debug: `Company "${company?.name}" has no usable books_from (got: ${JSON.stringify(
          company?.books_from
        )}). Raw company record: ${JSON.stringify(company)}`,
      }
    }

    return {
      date,
      debug: `Defaulted from company "${company.name}" (books_from ${company.books_from}) -> ${date}`,
    }
  }, [data, loading, error])
}