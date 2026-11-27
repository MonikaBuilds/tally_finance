import { useEffect, useRef, useState } from 'react'

/* Copies text to the clipboard and flags success briefly for button feedback. */
export default function useCopy() {
  const [copied, setCopied] = useState(false)
  const timer = useRef(null)

  useEffect(() => () => clearTimeout(timer.current), [])

  async function copy(text) {
    try {
      await navigator.clipboard.writeText(text)
      setCopied(true)
      clearTimeout(timer.current)
      timer.current = setTimeout(() => setCopied(false), 1600)
    } catch {
      setCopied(false)
    }
  }

  return [copied, copy]
}
