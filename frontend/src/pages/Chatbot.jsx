import { useEffect, useRef, useState } from 'react'
import { Bot, Loader2, Send, User } from 'lucide-react'
import PageHeader from '../components/layout/PageHeader'
import { apiPost } from '../api/client'

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

function Chatbot() {
  const [messages, setMessages] = useState([
    {
      role: 'assistant',
      content:
        "Hi! How can I assist you today? Ask me about your Profit & Loss, " +
        'receivables, payables, pending invoices, or any other report — ' +
        "I'll pull the numbers straight from Tally.",
    },
  ])

  const [input, setInput] = useState('')
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const bottomRef = useRef(null)

  useEffect(() => {
    bottomRef.current?.scrollIntoView({
      behavior: 'smooth',
    })
  }, [messages, loading])

  async function sendMessage(text) {
    const trimmed = text.trim()

    if (!trimmed || loading) {
      return
    }

    const companyName = getSelectedCompany()

    if (!companyName) {
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
        },
      )

      setMessages((prev) => [
        ...prev,
        {
          role: 'assistant',
          content: response.answer,
          intent: response.intent,
          blocked:
            response.intent === 'write_operation',
        },
      ])
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
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
        <div className="chat-messages">
          {messages.map((message, index) => (
            <div
              key={index}
              className={
                message.role === 'user'
                  ? 'chat-message chat-message--user'
                  : 'chat-message'
              }
            >
              <span className="chat-avatar" aria-hidden="true">
                {message.role === 'user' ? <User size={16} /> : <Bot size={16} />}
              </span>

              <div
                className={
                  message.role === 'user'
                    ? 'chat-bubble chat-bubble--user'
                    : message.blocked
                      ? 'chat-bubble chat-bubble--assistant chat-bubble--blocked'
                      : 'chat-bubble chat-bubble--assistant'
                }
              >
                {message.content}
              </div>
            </div>
          ))}

          {loading && (
            <div className="chat-message">
              <span className="chat-avatar" aria-hidden="true">
                <Bot size={16} />
              </span>
              <div className="chat-bubble chat-bubble--assistant chat-bubble--typing">
                <Loader2 size={14} className="spin" />
                Thinking...
              </div>
            </div>
          )}

          {error && (
            <div className="error-message">
              {error}
            </div>
          )}

          <div ref={bottomRef} />
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