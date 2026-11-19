import test from 'node:test'
import assert from 'node:assert/strict'

// sessionStorage stand-in for Node. Object.keys() must list stored keys,
// exactly like the browser's Storage object does.
class MockSessionStorage {
  getItem(key) {
    return Object.prototype.hasOwnProperty.call(this, key) ? this[key] : null
  }
  setItem(key, value) {
    this[key] = String(value)
  }
  removeItem(key) {
    delete this[key]
  }
}

globalThis.sessionStorage = new MockSessionStorage()

const { requiredPermission, hasPermission, canOpen } = await import('../src/utils/permissions.js')
const { loadChatHistory, saveChatHistory, clearChatHistory } = await import('../src/utils/chatHistory.js')

test('pages map to the permission the backend enforces', () => {
  assert.equal(requiredPermission('/'), 'financial')
  assert.equal(requiredPermission('/reports/profit-loss'), 'financial')
  assert.equal(requiredPermission('/reports/day-book'), 'financial')
  assert.equal(requiredPermission('/reports/inventory'), 'inventory')
  assert.equal(requiredPermission('/reports/stock-item-vouchers'), 'inventory')
  assert.equal(requiredPermission('/reports/godowns/Main'), 'inventory')
  assert.equal(requiredPermission('/reports/trial-balance/opening-stock'), 'inventory')
  assert.equal(requiredPermission('/chatbot'), null)
  assert.equal(requiredPermission('/reports/'), null)
})

test('inventory-only users cannot open financial pages', () => {
  const user = { roles: ['user'], permissions: ['inventory'] }
  assert.equal(canOpen(user, '/reports/profit-loss'), false)
  assert.equal(canOpen(user, '/'), false)
  assert.equal(canOpen(user, '/reports/inventory'), true)
  assert.equal(canOpen(user, '/chatbot'), true)
})

test('superadmin can open everything', () => {
  assert.equal(hasPermission({ roles: ['superadmin'], permissions: [] }, 'inventory'), true)
})

test('missing user data denies protected pages', () => {
  assert.equal(canOpen(null, '/reports/profit-loss'), false)
  assert.equal(canOpen(null, '/chatbot'), true)
})

test('chat history is kept per company and survives navigation', () => {
  const messages = [{ role: 'user', content: 'What are my receivables?' }]
  saveChatHistory('ABC Pvt Ltd', 'session-1', messages)

  assert.deepEqual(loadChatHistory('ABC Pvt Ltd'), { sessionId: 'session-1', messages })
  assert.equal(loadChatHistory('Other Co'), null)
})

test('chat history keeps only the newest 100 messages', () => {
  const many = Array.from({ length: 150 }, (_, i) => ({ role: 'user', content: String(i) }))
  saveChatHistory('ABC Pvt Ltd', 'session-2', many)

  const stored = loadChatHistory('ABC Pvt Ltd')
  assert.equal(stored.messages.length, 100)
  assert.equal(stored.messages[0].content, '50')
})

test('logout clears every stored conversation', () => {
  saveChatHistory('ABC Pvt Ltd', 's', [{ role: 'user', content: 'x' }])
  saveChatHistory('Other Co', 's', [{ role: 'user', content: 'y' }])

  clearChatHistory()

  assert.equal(loadChatHistory('ABC Pvt Ltd'), null)
  assert.equal(loadChatHistory('Other Co'), null)
})

test('corrupt stored history starts a fresh conversation', () => {
  sessionStorage.setItem('tfi.chat:ABC Pvt Ltd', '{not json')
  assert.equal(loadChatHistory('ABC Pvt Ltd'), null)
})
