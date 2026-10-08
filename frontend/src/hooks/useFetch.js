import { useEffect, useState } from 'react'
import { apiGet } from '../api/client'
import {
  isCacheablePath,
  buildBrowserCacheKey,
  getBrowserCache,
  setBrowserCache,
  updateBrowserCacheStatus,
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
  const reportStatusKey = path?.toLowerCase().startsWith('/reports/')
    ? cacheKey
    : null
  const cached = cacheKey ? getBrowserCache(cacheKey) : null

  const [state, setState] = useState(() => {
    if (!path) {
      return {
        path,
        data: null,
        loading: false,
        error: null,
        refreshError: null,
        isStale: false,
        cachedAt: null,
      }
    }
    if (cached && cached.data !== undefined) {
      return {
        path,
        data: cached.data,
        loading: false,
        error: null,
        refreshError: null,
        isStale: cached.isStale || isForceRefresh,
        cachedAt: cached.timestamp,
      }
    }
    return {
      path,
      data: null,
      loading: true,
      error: null,
      refreshError: null,
      isStale: false,
      cachedAt: null,
    }
  })

  useEffect(() => {
    if (!path) return

    const currentCached = cacheKey ? getBrowserCache(cacheKey) : null

    // If we already have fresh cached data, skip redundant network fetch
    if (!isForceRefresh && currentCached && !currentCached.isStale) {
      updateBrowserCacheStatus(reportStatusKey, null)
      return
    }

    let ignore = false
    const controller = new AbortController()
    let timeoutId = null

    if (currentCached && currentCached.data !== undefined) {
      // The current cache entry is used as the visible state while revalidating.
      updateBrowserCacheStatus(reportStatusKey, {
        cachedAt: currentCached.timestamp,
        refreshing: true,
      })
    } else {
      updateBrowserCacheStatus(reportStatusKey, null)
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
          const serverStale = Boolean(
            result?.is_stale || result?.source === 'stale_cache'
          )
          const responseTimestamp = serverStale && result?.cached_at
            ? Date.parse(result.cached_at)
            : Date.now()

          if (
            isCacheEnabled &&
            cacheKey &&
            result !== undefined &&
            result?.success !== false &&
            !serverStale
          ) {
            setBrowserCache(cacheKey, result, ttlMs)
          }
          setState({
            path,
            data: result,
            loading: false,
            error: null,
            refreshError: serverStale ? 'The server returned retained cached data.' : null,
            isStale: serverStale,
            cachedAt: Number.isFinite(responseTimestamp)
              ? responseTimestamp
              : Date.now(),
          })
          updateBrowserCacheStatus(
            reportStatusKey,
            serverStale
              ? {
                  cachedAt: Number.isFinite(responseTimestamp)
                    ? responseTimestamp
                    : Date.now(),
                  refreshing: false,
                }
              : null
          )
        }
      })
      .catch((err) => {
        if (ignore) return

        const message = err.name === 'AbortError'
          ? 'Request timed out. Tally is currently unavailable.'
          : err.message

        if (currentCached && currentCached.data !== undefined) {
          updateBrowserCacheStatus(reportStatusKey, {
            cachedAt: currentCached.timestamp,
            refreshing: false,
          })
          setState({
            path,
            data: currentCached.data,
            loading: false,
            error: null,
            refreshError: message,
            isStale: true,
            cachedAt: currentCached.timestamp,
          })
          return
        }

        updateBrowserCacheStatus(reportStatusKey, null)
        setState({
          path,
          data: null,
          loading: false,
          error: message,
          refreshError: null,
          isStale: false,
          cachedAt: null,
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
      updateBrowserCacheStatus(reportStatusKey, null)
    }
  }, [path, timeoutMs, forceRefresh, isForceRefresh, cacheKey, reportStatusKey, ttlMs, isCacheEnabled])

  if (!path) {
    return {
      data: null,
      loading: false,
      error: null,
      refreshError: null,
      isStale: false,
      cachedAt: null,
    }
  }

  if (state.path !== path) {
    if (cached && cached.data !== undefined) {
      return {
        data: cached.data,
        loading: false,
        error: null,
        refreshError: null,
        isStale: cached.isStale || isForceRefresh,
        cachedAt: cached.timestamp,
      }
    }
    return {
      data: null,
      loading: true,
      error: null,
      refreshError: null,
      isStale: false,
      cachedAt: null,
    }
  }

  return state
}
