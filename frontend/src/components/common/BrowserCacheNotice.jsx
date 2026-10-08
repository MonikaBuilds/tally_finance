import { useEffect, useState } from 'react'
import {
  getStaleBrowserCacheEntries,
  subscribeToBrowserCacheStatus,
} from '../../utils/browserCache'

function BrowserCacheNotice() {
  const [entries, setEntries] = useState(getStaleBrowserCacheEntries)

  useEffect(() => {
    const refreshEntries = () => setEntries(getStaleBrowserCacheEntries())
    return subscribeToBrowserCacheStatus(refreshEntries)
  }, [])

  if (!entries.length) return null

  const timestamps = entries
    .map((entry) => entry.cachedAt)
    .filter(Number.isFinite)
  const timestamp = timestamps.length
    ? new Date(Math.min(...timestamps)).toLocaleString()
    : null
  const refreshing = entries.some((entry) => entry.refreshing)

  return (
    <div className="browser-cache-notice" role="status">
      {refreshing
        ? `Showing saved report data${timestamp ? ` from ${timestamp}` : ''} while checking Tally.`
        : `Tally could not refresh this report. Showing saved data${timestamp ? ` from ${timestamp}` : ''}.`}
    </div>
  )
}

export default BrowserCacheNotice
