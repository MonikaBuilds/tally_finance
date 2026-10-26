/**
 * Browser-side resilient cache manager.
 * Dual-tier caching: in-memory Map for 0ms transitions + sessionStorage fallback.
 * Supports TTL expiry, company isolation, Stale-While-Revalidate (SWR),
 * safe cacheability filtering (never caches auth tokens or credentials),
 * and cache invalidation on logout/company change.
 */

const MEMORY_CACHE = new Map()
const STALE_CACHE_ENTRIES = new Map()
const STORAGE_PREFIX = 'tfi.bcache:'
const DEFAULT_TTL_MS = 60000 // 60 seconds (1 minute)
const SELECTED_COMPANY_KEY = 'selected_company'
const CACHE_STATUS_EVENT = 'tfi:browser-cache-status'

export function updateBrowserCacheStatus(key, status) {
  if (!key) return

  if (status) {
    STALE_CACHE_ENTRIES.set(key, status)
  } else {
    STALE_CACHE_ENTRIES.delete(key)
  }

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(CACHE_STATUS_EVENT))
  }
}

export function getStaleBrowserCacheEntries() {
  return Array.from(STALE_CACHE_ENTRIES.values())
}

export function subscribeToBrowserCacheStatus(listener) {
  if (typeof window === 'undefined') return () => {}
  window.addEventListener(CACHE_STATUS_EVENT, listener)
  listener()
  return () => window.removeEventListener(CACHE_STATUS_EVENT, listener)
}

/**
 * Safe helper to access sessionStorage without throwing in non-browser/SSR/Node environments.
 */
function getStorage() {
  try {
    if (typeof window !== 'undefined' && window.sessionStorage) {
      return window.sessionStorage
    }
    if (typeof sessionStorage !== 'undefined') {
      return sessionStorage
    }
  } catch {
    // Storage access blocked or restricted
  }
  return null
}

/**
 * Determine whether an API endpoint path is safe and suitable for browser-side caching.
 * NEVER caches authentication tokens, credentials, passwords, or state-changing requests.
 */
export function isCacheablePath(path) {
  if (!path || typeof path !== 'string') return false

  const clean = path.trim().toLowerCase()

  // 1. Strict Exclusion: Never cache authentication, login, tokens, or credentials
  if (
    clean.startsWith('/auth') ||
    clean.includes('token') ||
    clean.includes('password') ||
    clean.includes('secret') ||
    clean.includes('login') ||
    clean.includes('logout') ||
    clean.includes('csrf')
  ) {
    return false
  }

  // 2. Safe read-only paths (Dashboard, Tally metadata/status, and Financial Reports)
  if (
    clean.startsWith('/dashboard') ||
    clean.startsWith('/reports') ||
    clean.startsWith('/tally/companies') ||
    clean.startsWith('/tally/status')
  ) {
    return true
  }

  // Allow general read-only GET queries that do not mutate state
  return !clean.startsWith('/admin')
}

/**
 * Remove transient cache-busting tokens (refresh, force_refresh, _)
 * so cache key identity remains canonical for the underlying resource.
 */
export function normalizePathForCacheKey(path) {
  if (!path || typeof path !== 'string') return ''
  try {
    const [pathname, search] = path.split('?')
    if (!search) return pathname

    const params = new URLSearchParams(search)
    params.delete('refresh')
    params.delete('force_refresh')
    params.delete('_')

    const cleanQuery = params.toString()
    return cleanQuery ? `${pathname}?${cleanQuery}` : pathname
  } catch {
    return path
  }
}

/**
 * Retrieve the currently selected company name from sessionStorage.
 */
export function getCurrentSelectedCompany() {
  const storage = getStorage()
  if (!storage) return null

  try {
    const company = storage.getItem(SELECTED_COMPANY_KEY)
    return company && company !== '*' ? company.trim() : null
  } catch {
    return null
  }
}

/**
 * Build a deterministic, company-isolated and request-aware browser cache key.
 */
export function buildBrowserCacheKey(path, company = null) {
  const resolvedCompany = (
    company ||
    getCurrentSelectedCompany() ||
    '_all_'
  )
    .trim()
    .toLowerCase()

  const normalizedPath = normalizePathForCacheKey(path)
  return `${STORAGE_PREFIX}${resolvedCompany}:${normalizedPath}`
}

/**
 * Retrieve an entry from browser cache (Memory -> sessionStorage).
 * Returns { data, isStale: boolean, timestamp: number } or null.
 */
export function getBrowserCache(key) {
  if (!key) return null

  const now = Date.now()

  // 1. Check in-memory cache first (0ms lookup)
  if (MEMORY_CACHE.has(key)) {
    const entry = MEMORY_CACHE.get(key)
    if (entry && entry.expiresAt) {
      return {
        data: entry.data,
        isStale: now > entry.expiresAt,
        timestamp: entry.timestamp,
      }
    }
  }

  // 2. Check sessionStorage fallback
  const storage = getStorage()
  if (storage) {
    try {
      const raw = storage.getItem(key)
      if (raw) {
        const entry = JSON.parse(raw)
        if (entry && entry.data !== undefined && entry.expiresAt) {
          // Restore to memory cache for fast subsequent reads
          MEMORY_CACHE.set(key, entry)
          return {
            data: entry.data,
            isStale: now > entry.expiresAt,
            timestamp: entry.timestamp,
          }
        }
      }
    } catch {
      // JSON parse error or storage read failure
    }
  }

  return null
}

/**
 * Store data in browser cache (Memory + sessionStorage).
 */
export function setBrowserCache(key, data, ttlMs = DEFAULT_TTL_MS) {
  if (!key || data === undefined || ttlMs <= 0) return

  const now = Date.now()
  const entry = {
    data,
    timestamp: now,
    expiresAt: now + ttlMs,
  }

  // Save to memory
  MEMORY_CACHE.set(key, entry)

  // Save to sessionStorage
  const storage = getStorage()
  if (storage) {
    try {
      storage.setItem(key, JSON.stringify(entry))
    } catch {
      // Storage quota exceeded or unavailable; in-memory cache remains active
    }
  }
}

/**
 * Invalidate a specific cache key.
 */
export function invalidateBrowserCache(key) {
  if (!key) return

  MEMORY_CACHE.delete(key)
  const storage = getStorage()
  if (storage) {
    try {
      storage.removeItem(key)
    } catch {
      // Silently ignore storage errors
    }
  }
}

/**
 * Invalidate all browser cache entries for a specific company.
 */
export function clearBrowserCacheForCompany(company) {
  if (!company) return

  const norm = company.trim().toLowerCase()
  const prefix = `${STORAGE_PREFIX}${norm}:`

  // Invalidate in-memory entries
  for (const key of MEMORY_CACHE.keys()) {
    if (key.startsWith(prefix)) {
      MEMORY_CACHE.delete(key)
    }
  }
  for (const key of STALE_CACHE_ENTRIES.keys()) {
    if (key.startsWith(prefix)) STALE_CACHE_ENTRIES.delete(key)
  }

  // Invalidate in sessionStorage
  const storage = getStorage()
  if (storage) {
    try {
      const keysToRemove = []
      for (let i = 0; i < storage.length; i++) {
        const k = storage.key(i)
        if (k && k.startsWith(prefix)) {
          keysToRemove.push(k)
        }
      }
      for (const k of keysToRemove) {
        storage.removeItem(k)
      }
    } catch {
      // Silently ignore
    }
  }

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(CACHE_STATUS_EVENT))
  }
}

/**
 * Clear all browser cache entries (e.g. on logout, user switch, or company change).
 */
export function clearBrowserCache() {
  MEMORY_CACHE.clear()
  STALE_CACHE_ENTRIES.clear()

  const storage = getStorage()
  if (storage) {
    try {
      const keysToRemove = []
      for (let i = 0; i < storage.length; i++) {
        const k = storage.key(i)
        if (k && k.startsWith(STORAGE_PREFIX)) {
          keysToRemove.push(k)
        }
      }
      for (const k of keysToRemove) {
        storage.removeItem(k)
      }
    } catch {
      // Silently ignore storage access errors
    }
  }

  if (typeof window !== 'undefined') {
    window.dispatchEvent(new Event(CACHE_STATUS_EVENT))
  }
}

