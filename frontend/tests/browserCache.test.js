import test from 'node:test'
import assert from 'node:assert/strict'

import {
  isCacheablePath,
  normalizePathForCacheKey,
  buildBrowserCacheKey,
  getBrowserCache,
  setBrowserCache,
  invalidateBrowserCache,
  clearBrowserCacheForCompany,
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

test('isCacheablePath: strict security filtering for auth and credentials', () => {
  // Authentication & credential endpoints must NEVER be cached
  assert.equal(isCacheablePath('/auth/login'), false)
  assert.equal(isCacheablePath('/auth/me'), false)
  assert.equal(isCacheablePath('/auth/refresh'), false)
  assert.equal(isCacheablePath('/auth/logout'), false)
  assert.equal(isCacheablePath('/api/v1/auth/tokens'), false)
  assert.equal(isCacheablePath('/api/token/verify'), false)
  assert.equal(isCacheablePath('/users/reset-password'), false)
  assert.equal(isCacheablePath('/csrf-token'), false)
  assert.equal(isCacheablePath(''), false)
  assert.equal(isCacheablePath(null), false)
  assert.equal(isCacheablePath(undefined), false)

  // Safe read-only business endpoints MUST be cacheable
  assert.equal(isCacheablePath('/dashboard/summary?from_date=2025-04-01&to_date=2025-04-30'), true)
  assert.equal(isCacheablePath('/dashboard/monthly'), true)
  assert.equal(isCacheablePath('/reports/ledgers'), true)
  assert.equal(isCacheablePath('/reports/stock-summary'), true)
  assert.equal(isCacheablePath('/reports/receivables'), true)
  assert.equal(isCacheablePath('/reports/payables'), true)
  assert.equal(isCacheablePath('/tally/companies'), true)
  assert.equal(isCacheablePath('/tally/status'), true)
})

test('normalizePathForCacheKey: strips transient refresh parameters while preserving query filters', () => {
  const raw1 = '/dashboard/summary?from_date=2025-04-01&to_date=2025-04-30&refresh=1728219000'
  const normalized1 = normalizePathForCacheKey(raw1)
  assert.equal(normalized1, '/dashboard/summary?from_date=2025-04-01&to_date=2025-04-30')

  const raw2 = '/dashboard/monthly?force_refresh=true&from_date=2025-04-01'
  const normalized2 = normalizePathForCacheKey(raw2)
  assert.equal(normalized2, '/dashboard/monthly?from_date=2025-04-01')

  const raw3 = '/tally/companies?refresh=1'
  const normalized3 = normalizePathForCacheKey(raw3)
  assert.equal(normalized3, '/tally/companies')

  const rawPlain = '/reports/ledgers'
  assert.equal(normalizePathForCacheKey(rawPlain), '/reports/ledgers')
})

test('buildBrowserCacheKey: enforces strict company isolation and normalizes casing', () => {
  const path = '/dashboard/summary?from_date=2025-04-01&to_date=2025-04-30'

  const keyCompanyA = buildBrowserCacheKey(path, 'Acme Corp')
  const keyCompanyB = buildBrowserCacheKey(path, 'Beta Ltd')
  const keyCompanyAUpper = buildBrowserCacheKey(path, 'ACME CORP')

  // Company A and Company B must have distinct keys
  assert.notEqual(keyCompanyA, keyCompanyB)
  assert.ok(keyCompanyA.includes('acme corp'))
  assert.ok(keyCompanyB.includes('beta ltd'))

  // Case normalization
  assert.equal(keyCompanyA, keyCompanyAUpper)

  // Fallback when no company selected
  const keyNoCompany = buildBrowserCacheKey(path, null)
  assert.ok(keyNoCompany.includes('_all_'))
})

test('setBrowserCache and getBrowserCache: stores data, returns fresh, and identifies stale entries', () => {
  clearBrowserCache()

  const testKey = 'tfi.bcache:testco:/dashboard/summary'
  const sampleData = { total_sales: 500000, net_profit: 120000 }

  // 1. Initial lookup -> miss
  assert.equal(getBrowserCache(testKey), null)

  // 2. Set with 1000ms TTL
  setBrowserCache(testKey, sampleData, 1000)

  // 3. Immediate read -> fresh hit
  const freshHit = getBrowserCache(testKey)
  assert.ok(freshHit)
  assert.deepEqual(freshHit.data, sampleData)
  assert.equal(freshHit.isStale, false)

  // 4. Stale evaluation
  // Manually manipulate expiry in memory for deterministic test
  const originalNow = Date.now
  try {
    Date.now = () => originalNow() + 2000
    const staleHit = getBrowserCache(testKey)
    assert.ok(staleHit)
    assert.deepEqual(staleHit.data, sampleData)
    assert.equal(staleHit.isStale, true)
  } finally {
    Date.now = originalNow
  }
})

test('invalidateBrowserCache: removes single key from memory and sessionStorage', () => {
  clearBrowserCache()

  const key1 = 'tfi.bcache:company1:/report1'
  const key2 = 'tfi.bcache:company1:/report2'

  setBrowserCache(key1, { val: 1 }, 60000)
  setBrowserCache(key2, { val: 2 }, 60000)

  assert.ok(getBrowserCache(key1))
  assert.ok(getBrowserCache(key2))

  invalidateBrowserCache(key1)

  assert.equal(getBrowserCache(key1), null)
  assert.ok(getBrowserCache(key2))
})

test('clearBrowserCacheForCompany: purges only selected company entries', () => {
  clearBrowserCache()

  const keyCoA1 = 'tfi.bcache:co_alpha:/summary'
  const keyCoA2 = 'tfi.bcache:co_alpha:/monthly'
  const keyCoB1 = 'tfi.bcache:co_beta:/summary'

  setBrowserCache(keyCoA1, { company: 'Alpha' }, 60000)
  setBrowserCache(keyCoA2, { company: 'Alpha' }, 60000)
  setBrowserCache(keyCoB1, { company: 'Beta' }, 60000)

  clearBrowserCacheForCompany('co_alpha')

  assert.equal(getBrowserCache(keyCoA1), null)
  assert.equal(getBrowserCache(keyCoA2), null)
  assert.ok(getBrowserCache(keyCoB1))
})

test('clearBrowserCache: clears all entries on logout', () => {
  clearBrowserCache()

  setBrowserCache('tfi.bcache:co1:/summary', { a: 1 }, 60000)
  setBrowserCache('tfi.bcache:co2:/summary', { b: 2 }, 60000)

  assert.ok(getBrowserCache('tfi.bcache:co1:/summary'))
  assert.ok(getBrowserCache('tfi.bcache:co2:/summary'))

  clearBrowserCache()

  assert.equal(getBrowserCache('tfi.bcache:co1:/summary'), null)
  assert.equal(getBrowserCache('tfi.bcache:co2:/summary'), null)
})
