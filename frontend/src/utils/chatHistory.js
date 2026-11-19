// Chat conversation kept for this browser tab only (sessionStorage), per
// company, so leaving the AI Assistant page does not lose the conversation
// or the session id the backend uses for follow-up questions.

const PREFIX = 'tfi.chat:'
const MAX_MESSAGES = 100

function storageKey(company) {
  return `${PREFIX}${company || 'default'}`
}

export function loadChatHistory(company) {
  try {
    const stored = JSON.parse(sessionStorage.getItem(storageKey(company)) || 'null')

    if (stored && Array.isArray(stored.messages) && stored.sessionId) {
      return stored
    }
  } catch {
    // Corrupt or unavailable storage: start a fresh conversation.
  }

  return null
}

export function saveChatHistory(company, sessionId, messages) {
  try {
    sessionStorage.setItem(
      storageKey(company),
      JSON.stringify({
        sessionId,
        // Keep the newest messages only, so storage stays small.
        messages: messages.slice(-MAX_MESSAGES),
      }),
    )
  } catch {
    // Storage full or blocked: the chat still works for this page view.
  }
}

export function clearChatHistory() {
  try {
    Object.keys(sessionStorage)
      .filter((key) => key.startsWith(PREFIX))
      .forEach((key) => sessionStorage.removeItem(key))
  } catch {
    // Nothing to clear.
  }
}
