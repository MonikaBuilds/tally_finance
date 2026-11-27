import { useMemo } from 'react'
import { Check, Copy, Database, FileSpreadsheet, Loader2, WifiOff } from 'lucide-react'
import { parseChatAnswer } from '../../utils/chatAnswerParser'
import AnswerContent from './AnswerContent'
import useCopy from './useCopy'

function AssistantMessage({ message, pendingDownload, downloadErrors, onDownload }) {
  const parsed = useMemo(() => parseChatAnswer(message.content), [message.content])
  const [copied, copy] = useCopy()

  const hasTable = parsed.blocks.some((block) => block.type === 'table')
  const downloads = message.downloads || []
  const showFooter =
    !message.blocked &&
    (parsed.fromTally || message.isStale || downloads.length > 0 || parsed.blocks.length > 1)

  const bubbleClass = [
    'chat-bubble',
    'chat-bubble--assistant',
    message.blocked && 'chat-bubble--blocked',
    hasTable && 'chat-bubble--rich',
  ].filter(Boolean).join(' ')

  return (
    <div className={hasTable ? 'chat-bubble-wrap chat-bubble-wrap--wide' : 'chat-bubble-wrap'}>
      <div className={bubbleClass}>
        {message.blocked || parsed.blocks.length === 0
          ? <p className="answer-paragraph">{message.content}</p>
          : <AnswerContent blocks={parsed.blocks} />}
      </div>

      {showFooter && (
        <div className="chat-answer-footer">
          <div className="chat-answer-footer__source">
            {message.isStale ? (
              <span
                className="chat-source chat-source--stale"
                title="Tally was offline, so this answer uses the last cached copy of your data"
              >
                <WifiOff size={12} aria-hidden="true" />
                Cached data · Tally offline
              </span>
            ) : parsed.fromTally ? (
              <span className="chat-source" title="Figures were read live from Tally">
                <Database size={12} aria-hidden="true" />
                Live from Tally
              </span>
            ) : null}
          </div>

          <div className="chat-answer-footer__actions">
            {downloads.map((download) => {
              const pending = pendingDownload === download.url
              return (
                <button
                  key={download.url}
                  type="button"
                  className="chat-action"
                  onClick={() => onDownload(download)}
                  disabled={pendingDownload !== null}
                  aria-label={download.label || 'Download Excel'}
                  title={download.filename || 'Download Excel'}
                >
                  {pending
                    ? <Loader2 size={14} className="spin" aria-hidden="true" />
                    : <FileSpreadsheet size={14} aria-hidden="true" />}
                  {pending ? 'Preparing…' : 'Excel'}
                </button>
              )
            })}
            <button
              type="button"
              className="chat-action"
              onClick={() => copy(message.content)}
              aria-label="Copy answer"
              title="Copy answer as text"
            >
              {copied ? <Check size={14} aria-hidden="true" /> : <Copy size={14} aria-hidden="true" />}
              {copied ? 'Copied' : 'Copy'}
            </button>
          </div>
        </div>
      )}

      {downloads.map((download) =>
        downloadErrors[download.url] ? (
          <div key={download.url} className="export-error" role="alert">
            {downloadErrors[download.url]}
          </div>
        ) : null,
      )}
    </div>
  )
}

export default AssistantMessage
