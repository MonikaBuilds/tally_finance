// Which permission each page needs. The backend enforces the same rules
// (403 for anything outside the user's permissions); this only keeps the
// menu honest and shows a clear message instead of a failing page.

const OPEN_PATHS = new Set(['/chatbot', '/tally-status', '/reports', '/admin/users'])

const INVENTORY_PATH = /(inventory|stock|godown|location|registers)/i

export function requiredPermission(pathname) {
  const path = (pathname || '/').replace(/\/+$/, '') || '/'

  if (OPEN_PATHS.has(path)) {
    return null
  }

  if (INVENTORY_PATH.test(path)) {
    return 'inventory'
  }

  // Dashboard, financial statements, ledgers, day book, outstanding.
  return 'financial'
}

export function readCurrentUser() {
  try {
    return JSON.parse(sessionStorage.getItem('chat_user') || 'null')
  } catch {
    return null
  }
}

export function hasPermission(user, permission) {
  if (!permission) {
    return true
  }

  const roles = Array.isArray(user?.roles) ? user.roles : []

  if (roles.includes('superadmin')) {
    return true
  }

  const permissions = Array.isArray(user?.permissions) ? user.permissions : []

  return permissions.includes(permission)
}

export function canOpen(user, pathname) {
  return hasPermission(user, requiredPermission(pathname))
}
