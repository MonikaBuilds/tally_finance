import react from '@vitejs/plugin-react'
import { defineConfig, loadEnv } from 'vite'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, process.cwd(), '')

  // Optional: comma-separated host names allowed to open the dev server
  // (for example a tunnel address).
  const allowedHosts = (env.VITE_ALLOWED_HOSTS || '')
    .split(',')
    .map((host) => host.trim())
    .filter(Boolean)

  // Optional: forward /api requests to the backend through the same
  // address the browser uses, so login and CSRF cookies stay same-origin.
  const proxyTarget = (env.VITE_BACKEND_PROXY_TARGET || '').trim()

  const server = {}
  if (allowedHosts.length) server.allowedHosts = allowedHosts
  if (proxyTarget) {
    server.proxy = {
      '/api': { target: proxyTarget, changeOrigin: true },
    }
  }

  return {
    plugins: [react()],
    server: Object.keys(server).length ? server : undefined,
  }
})