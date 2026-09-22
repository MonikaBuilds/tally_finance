import { useState } from 'react'
import { FileDown, FileSpreadsheet, Loader2 } from 'lucide-react'
import { downloadFile } from '../../api/client'

function ExportButtons({ basePath, params = {}, filenameBase = 'report', disabled = false }) {
  const [pending, setPending] = useState(null) // 'pdf' | 'xlsx' | null
  const [error, setError] = useState(null)

  async function handleDownload(format) {
    setPending(format)
    setError(null)

    try {
      const query = new URLSearchParams(
        Object.entries(params).filter(([, value]) => value !== undefined && value !== null && value !== '')
      ).toString()

      const path = `${basePath}/${format}${query ? `?${query}` : ''}`
      await downloadFile(path, `${filenameBase}.${format}`)
    } catch (err) {
      setError(err.message)
    } finally {
      setPending(null)
    }
  }

  const isDisabled = disabled || pending !== null

  return (
    <div className="export-buttons">
      <button
        type="button"
        className="btn btn--outline"
        onClick={() => handleDownload('pdf')}
        disabled={isDisabled}
      >
        {pending === 'pdf' ? <Loader2 size={16} className="spin" /> : <FileDown size={16} />}
        {pending === 'pdf' ? 'Preparing…' : 'PDF'}
      </button>
      <button
        type="button"
        className="btn btn--outline"
        onClick={() => handleDownload('xlsx')}
        disabled={isDisabled}
      >
        {pending === 'xlsx' ? <Loader2 size={16} className="spin" /> : <FileSpreadsheet size={16} />}
        {pending === 'xlsx' ? 'Preparing…' : 'Excel'}
      </button>
      {error && <span className="export-error">{error}</span>}
    </div>
  )
}

export default ExportButtons
