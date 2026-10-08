import test from 'node:test'
import assert from 'node:assert/strict'

import {
  isCacheablePath,
  buildBrowserCacheKey,
  getBrowserCache,
  setBrowserCache,
  clearBrowserCache,
} from '../src/utils/browserCache.js'

// Simple mock for sessionStorage in Node environment
class MockSessionStorage {
  constructor() {
    this.store = new Map()
  }
  getItem(key) {
    return this.store.get(key) || null
  }
  setItem(key, value) {
    this.store.set(key, String(value))
  }
  removeItem(key) {
    this.store.delete(key)
  }
  clear() {
    this.store.clear()
  }
  get length() {
    return this.store.size
  }
  key(index) {
    return Array.from(this.store.keys())[index] || null
  }
}

globalThis.sessionStorage = new MockSessionStorage()

/**
 * Simulator function that executes the exact synchronous cache evaluation
 * logic found inside useFetch's useState initializer and useEffect entry.
 */
function evaluateUseFetchState(path, options = {}) {
  const {
    cache = true,
    forceRefresh = false,
  } = options

  const isCacheEnabled = Boolean(cache !== false && isCacheablePath(path))
  const isForceRefresh = Boolean(
    forceRefresh ||
    (path && /[?&](refresh|force_refresh)=/.test(path))
  )

  const cacheKey = isCacheEnabled ? buildBrowserCacheKey(path) : null
  const cached = (!isForceRefresh && cacheKey) ? getBrowserCache(cacheKey) : null

  if (!path) {
    return { data: null, loading: false, error: null, isStale: false, shouldFetch: false }
  }

  if (cached && !cached.isStale) {
    return {
      data: cached.data,
      loading: false,
      error: null,
      isStale: false,
      shouldFetch: false, // 0ms fresh cache hit!
    }
  }

  if (cached && cached.data !== undefined) {
    return {
      data: cached.data,
      loading: true,
      error: null,
      isStale: true,
      shouldFetch: true, // SWR: show cached, fetch in background
    }
  }

  return {
    data: null,
    loading: true,
    error: null,
    isStale: false,
    shouldFetch: true, // Cold cache miss
  }
}

test('useFetch caching: cold miss triggers initial loading and background fetch', () => {
  clearBrowserCache()

  const path = '/dashboard/summary?from_date=2025-04-01&to_date=2025-04-30'
  const state = evaluateUseFetchState(path)

  assert.equal(state.data, null)
  assert.equal(state.loading, true)
  assert.equal(state.shouldFetch, true)
  assert.equal(state.isStale, false)
})

test('useFetch caching: warm fresh cache returns instantaneous data with no fetch (0ms hit)', () => {
  clearBrowserCache()

  const path = '/dashboard/summary?from_date=2025-04-01&to_date=2025-04-30'
  const key = buildBrowserCacheKey(path)
  const cachedData = { total_sales: 850000, net_profit: 220000 }

  setBrowserCache(key, cachedData, 60000)

  const state = evaluateUseFetchState(path)

  assert.deepEqual(state.data, cachedData)
  assert.equal(state.loading, false)
  assert.equal(state.shouldFetch, false) // Zero network requests needed!
  assert.equal(state.isStale, false)
})

test('useFetch caching: stale cache serves SWR data immediately while scheduling revalidation', () => {
  clearBrowserCache()

  const path = '/dashboard/monthly?from_date=2025-04-01'
  const key = buildBrowserCacheKey(path)
  const cachedData = [{ month: 'Apr 2025', income: 50000 }]

  setBrowserCache(key, cachedData, 1000)

  // Fast forward time to expire entry
  const originalNow = Date.now
  try {
    Date.now = () => originalNow() + 2000

    const state = evaluateUseFetchState(path)

    assert.deepEqual(state.data, cachedData) // Content visible immediately
    assert.equal(state.loading, true) // Background refresh flag
    assert.equal(state.shouldFetch, true)
    assert.equal(state.isStale, true)
  } finally {
    Date.now = originalNow
  }
})

test('useFetch caching: forceRefresh and refresh query param bypass cache', () => {
  clearBrowserCache()

  const basePath = '/dashboard/summary?from_date=2025-04-01&to_date=2025-04-30'
  const key = buildBrowserCacheKey(basePath)
  const oldData = { total_sales: 1000 }

  setBrowserCache(key, oldData, 60000)

  // 1. Bypass via query param
  const refreshPath = `${basePath}&refresh=1728219500`
  const stateByParam = evaluateUseFetchState(refreshPath)

  assert.equal(stateByParam.data, null) // Does not reuse old cached data
  assert.equal(stateByParam.loading, true)
  assert.equal(stateByParam.shouldFetch, true)

  // 2. Bypass via option
  const stateByOption = evaluateUseFetchState(basePath, { forceRefresh: true })

  assert.equal(stateByOption.data, null)
  assert.equal(stateByOption.loading, true)
  assert.equal(stateByOption.shouldFetch, true)
})

test('useFetch caching: explicit cache=false disables browser cache', () => {
  clearBrowserCache()

  const path = '/reports/ledgers'
  const key = buildBrowserCacheKey(path)
  setBrowserCache(key, { ledgers: ['Cash', 'Bank'] }, 60000)

  const state = evaluateUseFetchState(path, { cache: false })

  assert.equal(state.data, null)
  assert.equal(state.loading, true)
  assert.equal(state.shouldFetch, true)
})

test('useFetch caching: auth endpoints are never cached even if cache=true', () => {
  clearBrowserCache()

  const authPath = '/auth/me'
  const key = buildBrowserCacheKey(authPath)

  // Even if manually attempted, isCacheablePath blocks it
  assert.equal(isCacheablePath(authPath), false)

  const state = evaluateUseFetchState(authPath)
  assert.equal(state.data, null)
  assert.equal(state.loading, true)
  assert.equal(state.shouldFetch, true)
})
