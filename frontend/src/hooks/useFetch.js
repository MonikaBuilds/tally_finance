import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'

export function useFetch(path) {
  const [state, setState] = useState({ data: null, loading: Boolean(path), error: null })

  useEffect(() => {
    // A falsy path means "nothing to fetch yet" (e.g. the Ledger page
    // waiting on the user to pick a ledger before it has a query to run).
    // We don't touch state here - the neutral value is returned directly
    // below, without going through an extra render.
    if (!path) return

    let ignore = false

    setState({ data: null, loading: true, error: null })

    apiGet(path)
      .then((result) => {
        if (!ignore) setState({ data: result, loading: false, error: null })
      })
      .catch((err) => {
        if (!ignore) setState({ data: null, loading: false, error: err.message })
      })

    return () => {
      ignore = true
    }
  }, [path])

  if (!path) {
    return { data: null, loading: false, error: null }
  }

  return state
}