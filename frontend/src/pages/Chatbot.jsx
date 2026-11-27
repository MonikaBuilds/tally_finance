import { useEffect, useRef, useState } from 'react'
import { Bot, Send, User } from 'lucide-react'
import PageHeader from '../components/layout/PageHeader'
import AssistantMessage from '../components/chat/AssistantMessage'
import { apiPost, downloadFile } from '../api/client'
import { loadChatHistory, saveChatHistory } from '../utils/chatHistory'

const SUGGESTIONS = [
  'What is my revenue this month?',
  'Whom do I need to pay?',
  'Which invoices are pending?',
  'What are my outstanding receivables and payables?',
]

function getSelectedCompany() {
  const selectedCompany = sessionStorage.getItem('selected_company')

  if (selectedCompany) {
    return selectedCompany
  }

  try {
    const storedUser = sessionStorage.getItem('chat_user')

    if (!storedUser) {
      return null
    }

    const user = JSON.parse(storedUser)

    if (
      Array.isArray(user.companies) &&
      user.companies.length === 1
    ) {
      sessionStorage.setItem(
        'selected_company',
        user.companies[0],
      )

      return user.companies[0]
    }
  } catch {
    return null
  }

  return null
}

const WELCOME_MESSAGE = {
  role: 'assistant',
  content:
    "Hi! How can I assist you today? Ask me about your Profit & Loss, " +
    'receivables, payables, pending invoices, or any other report — ' +
    "I'll pull the numbers straight from Tally.",
}

function newSessionId() {
  try {
    return typeof crypto !== 'undefined' && crypto.randomUUID
      ? crypto.randomUUID()
      : `sess_${Date.now()}`
  } catch {
    return `sess_${Date.now()}`
  }
}

function Chatbot() {
  // Restore this tab's conversation for the selected company, so leaving
  // the page does not lose the chat or break follow-up questions.
  const [stored] = useState(() => loadChatHistory(getSelectedCompany()))

  const [messages, setMessages] = useState(
    () => stored?.messages?.length ? stored.messages : [WELCOME_MESSAGE],
  )

  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [pendingDownload, setPendingDownload] = useState(null)
  const [downloadErrors, setDownloadErrors] = useState({})
  const [sessionId] = useState(() => stored?.sessionId || newSessionId())

  const listRef = useRef(null)
  const hasScrolledRef = useRef(false)

  // Scroll only the message list. scrollIntoView() would also scroll every
  // ancestor (the whole page), which made the screen jump on each reply.
  useEffect(() => {
    const list = listRef.current
    if (!list) return

    const behavior = hasScrolledRef.current ? 'smooth' : 'auto'
    hasScrolledRef.current = true

    const latest = list.querySelector('[data-latest-answer]')
    const answerJustArrived =
      !loading && messages.length > 1 && messages.at(-1)?.role === 'assistant'

    if (answerJustArrived && latest) {
      // Land on the start of a new answer, not its end, so a long table
      // is read from its heading down instead of from the totals up.
      list.scrollTo({ top: Math.max(latest.offsetTop - 16, 0), behavior })
    } else {
      list.scrollTo({ top: list.scrollHeight, behavior })
    }
  }, [messages, loading])

  useEffect(() => {
    saveChatHistory(getSelectedCompany(), sessionId, messages)
  }, [messages, sessionId])

  async function sendMessage(text) {
    const trimmed = text.trim()

    if (!trimmed || loading) {
      return
    }

    const companyName = getSelectedCompany()

    // A cross-company comparison does not need one active company:
    // the question names the companies itself and the backend
    // authorizes them against the user's own access.
    const isComparisonQuery =
      /\b(compare|comparison|versus|vs\.?)\b/i.test(trimmed)

    if (!companyName && !isComparisonQuery) {
      setError(
        'Please select a company before using the AI Assistant.',
      )
      return
    }

    setMessages((prev) => [
      ...prev,
      {
        role: 'user',
        content: trimmed,
      },
    ])

    setInput('')
    setError(null)
    setLoading(true)

    try {
      const response = await apiPost(
        '/chat',
        {
          message: trimmed,
          company_name: companyName,
          session_id: sessionId,
        },
      )

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: response.answer,
          intent: response.intent,
          downloads: response.downloads || [],
          blocked:
            response.intent === 'write_operation',
          isStale: Boolean(response.is_stale || response.source === 'stale_cache'),
        },
      ])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  async function downloadReport(download) {
    // Only relative chat-export URLs supplied by this app are downloadable.
    if (!/^\/chat\/exports\/[a-f0-9-]+\.xlsx\?company_name=/.test(download.url)) return
    setPendingDownload(download.url)
    setDownloadErrors((previous) => ({ ...previous, [download.url]: null }))
    try {
      await downloadFile(download.url, download.filename)
    } catch (err) {
      setDownloadErrors((previous) => ({ ...previous, [download.url]: err.message }))
    } finally {
      setPendingDownload(null)
    }
  }

  function handleSubmit(event) {
    event.preventDefault()
    sendMessage(input)
  }

  return (
    <>
      <PageHeader
        title="AI Financial Assistant"
        subtitle="Ask about your Tally data in plain language"
      />

      <div className="chat-card">
        <div className="chat-messages" ref={listRef}>
          {messages.map((message, index) => (
            <div
              key={index}
              data-latest-answer={index === messages.length - 1 ? '' : undefined}
              className={
                message.role === 'user'
                  ? 'chat-message chat-message--user'
                  : 'chat-message'
              }
            >
              <span className="chat-avatar" aria-hidden="true">
                {message.role === 'user' ? <User size={16} /> : <Bot size={16} />}
              </span>

              {message.role === 'user' ? (
                <div className="chat-bubble chat-bubble--user">
                  {message.content}
                </div>
              ) : (
                <AssistantMessage
                  message={message}
                  pendingDownload={pendingDownload}
                  downloadErrors={downloadErrors}
                  onDownload={downloadReport}
                />
              )}
            </div>
          ))}

          {loading && (
            <div className="chat-message" role="status">
              <span className="chat-avatar" aria-hidden="true">
                <Bot size={16} />
              </span>
              <div className="chat-bubble chat-bubble--assistant chat-bubble--typing">
                <span className="chat-typing-dots" aria-hidden="true">
                  <span /><span /><span />
                </span>
                Reading your Tally data…
              </div>
            </div>
          )}

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

        </div>

        {messages.length <= 1 && (
          <div className="chat-suggestions">
            {SUGGESTIONS.map((suggestion) => (
              <button
                key={suggestion}
                type="button"
                className="chat-suggestion"
                onClick={() =>
                  sendMessage(suggestion)
                }
                disabled={loading}
              >
                {suggestion}
              </button>
            ))}
          </div>
        )}

        <form
          className="chat-input-row"
          onSubmit={handleSubmit}
        >
          <input
            className="chat-input"
            type="text"
            placeholder="Ask about revenue, payables, invoices..."
            value={input}
            onChange={(event) =>
              setInput(event.target.value)
            }
            disabled={loading}
          />

          <button
            className="btn"
            type="submit"
            disabled={
              loading ||
              !input.trim()
            }
          >
            <Send size={16} />
            Send
          </button>
        </form>
      </div>
    </>
  )
}

export default Chatbot