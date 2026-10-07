import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import {
  isCacheablePath,
  buildBrowserCacheKey,
  getBrowserCache,
  setBrowserCache,
} from '../utils/browserCache'

export function useFetch(path, options = {}) {
  const {
    timeoutMs,
    cache = true,
    forceRefresh = false,
    ttlMs,
  } = options

  const isCacheEnabled = Boolean(cache !== false && isCacheablePath(path))
  const isForceRefresh = Boolean(
    forceRefresh ||
    (path && /[?&](refresh|force_refresh)=/i.test(path))
  )

  const cacheKey = isCacheEnabled ? buildBrowserCacheKey(path) : null
  const cached = (!isForceRefresh && cacheKey) ? getBrowserCache(cacheKey) : null

  const [state, setState] = useState(() => {
    if (!path) {
      return { data: null, loading: false, error: null }
    }
    if (cached && !cached.isStale) {
      // 0ms instant warm fresh hit!
      return { data: cached.data, loading: false, error: null }
    }
    if (cached && cached.data !== undefined) {
      // SWR: serve stale data immediately while fetching fresh in background
      return { data: cached.data, loading: true, error: null }
    }
    return { data: null, loading: true, error: null }
  })

  useEffect(() => {
    if (!path) return

    // If we already have fresh cached data, skip redundant network fetch
    if (!isForceRefresh && cached && !cached.isStale) {
      setState({ data: cached.data, loading: false, error: null })
      return
    }

    let ignore = false
    const controller = new AbortController()
    let timeoutId = null

    // If cold miss (no cached data), ensure loading is true and data is null
    if (!cached || cached.data === undefined) {
      setState({ data: null, loading: true, error: null })
    }

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
          if (isCacheEnabled && cacheKey && result !== undefined) {
            setBrowserCache(cacheKey, result, ttlMs)
          }
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
          setState((prev) => ({
            data: prev.data,
            loading: false,
            error: 'Request timed out. Tally is currently unavailable.',
          }))
          return
        }

        setState((prev) => ({
          data: prev.data,
          loading: false,
          error: err.message,
        }))
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
  }, [path, timeoutMs, forceRefresh])

  if (!path) {
    return {
      data: null,
      loading: false,
      error: null,
    }
  }

  return state
}