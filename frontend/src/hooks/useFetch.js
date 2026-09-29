import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'

export function useFetch(path, options = {}) {
  const { timeoutMs } = options

  const [state, setState] = useState({
    data: null,
    loading: Boolean(path),
    error: null,
  })

  useEffect(() => {
    // A falsy path means "nothing to fetch yet" (e.g. the Ledger page
    // waiting on the user to pick a ledger before it has a query to run).
    // We don't touch state here - the neutral value is returned directly
    // below, without going through an extra render.
    if (!path) return

    let ignore = false
    const controller = new AbortController()

    let timeoutId = null

    setState({
      data: null,
      loading: true,
      error: null,
    })

    if (timeoutMs) {
      timeoutId = window.setTimeout(() => {
        controller.abort()
      }, timeoutMs)
    }

    apiGet(path, {
      signal: controller.signal,
    })
      .then((result) => {
        if (!ignore) {
          setState({
            data: result,
            loading: false,
            error: null,
          })
        }
      })
      .catch((err) => {
        if (ignore) return

        if (err.name === 'AbortError') {
          setState({
            data: null,
            loading: false,
            error: 'Request timed out. Tally is currently unavailable.',
          })
          return
        }

        setState({
          data: null,
          loading: false,
          error: err.message,
        })
      })
      .finally(() => {
        if (timeoutId) {
          window.clearTimeout(timeoutId)
        }
      })

    return () => {
      ignore = true

      if (timeoutId) {
        window.clearTimeout(timeoutId)
      }

      controller.abort()
    }
  }, [path, timeoutMs])

  if (!path) {
    return {
      data: null,
      loading: false,
      error: null,
    }
  }

  return state
}