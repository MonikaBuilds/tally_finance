import { useState } from 'react'
import {
    AlertCircle,
    BarChart3,
    Eye,
    EyeOff,
    Loader2,
    Lock,
    ShieldCheck,
    User,
} from 'lucide-react'
import {
    apiGet,
    apiPost,
} from '../api/client'
import { clearBrowserCache } from '../utils/browserCache'
import './Login.css'

function Login({ onLogin }) {
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [showPassword, setShowPassword] = useState(false)
    const [capsLockActive, setCapsLockActive] = useState(false)
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)

    function handleKeyDown(event) {
        if (event.getModifierState) {
            setCapsLockActive(event.getModifierState('CapsLock'))
        }
    }

    function handleKeyUp(event) {
        if (event.getModifierState) {
            setCapsLockActive(event.getModifierState('CapsLock'))
        }
    }

    async function handleSubmit(event) {
        event.preventDefault()

        const cleanUsername = username.trim()

        if (!cleanUsername || !password) {
            setError('Please enter your username and password.')
            return
        }

        setError('')
        setLoading(true)

        try {
            // Authenticate user with backend in a single roundtrip.
            // Backend returns user_id, username, companies, roles, and permissions.
            const response = await apiPost('/auth/login', {
                username: cleanUsername,
                password,
            })

            // Fallback to /auth/me only if roles/permissions were missing in response
            let currentUser = response
            if (!currentUser?.roles || !currentUser?.permissions) {
                currentUser = await apiGet('/auth/me')
            }

            clearBrowserCache()

            sessionStorage.setItem(
                'chat_user',
                JSON.stringify(currentUser),
            )

            if (
                Array.isArray(currentUser.companies) &&
                currentUser.companies.length === 1
            ) {
                sessionStorage.setItem(
                    'selected_company',
                    currentUser.companies[0],
                )
            } else {
                sessionStorage.removeItem(
                    'selected_company',
                )
            }

            onLogin?.(currentUser)
        } catch (err) {
            let message = err?.message || 'Unable to sign in. Please verify your credentials.'

            // Surface human-friendly messaging for network disconnects or offline server
            if (
                (typeof navigator !== 'undefined' && !navigator.onLine) ||
                message.toLowerCase().includes('failed to fetch') ||
                message.toLowerCase().includes('networkerror')
            ) {
                message = 'Unable to connect to the server. Please verify the backend service is running and check your network connection.'
            }

            setError(message)
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="login-page">
            <main className="login-main">
                <section
                    className="login-card"
                    aria-labelledby="login-title"
                >
                    <div className="login-brand">
                        <div className="login-logo">
                            <BarChart3 size={20} />
                        </div>

                        <div className="login-brand-copy">
                            <strong>Tally Financial Intelligence</strong>
                            <span>Financial Management Platform</span>
                        </div>
                    </div>

                    <div className="login-heading">
                        <h1 id="login-title">
                            Welcome back
                        </h1>

                        <p>
                            Sign in to access your financial intelligence
                            dashboard.
                        </p>
                    </div>

                    <form
                        className="login-form"
                        onSubmit={handleSubmit}
                        noValidate
                    >
                        <div className="login-field">
                            <label htmlFor="username">
                                Username
                            </label>

                            <div className="login-input-wrapper">
                                <User
                                    size={16}
                                    className="login-input-icon"
                                    aria-hidden="true"
                                />

                                <input
                                    id="username"
                                    type="text"
                                    value={username}
                                    onChange={(event) => {
                                        setUsername(event.target.value)

                                        if (error) {
                                            setError('')
                                        }
                                    }}
                                    placeholder="Enter your username"
                                    autoComplete="username"
                                    autoCapitalize="none"
                                    autoCorrect="off"
                                    spellCheck={false}
                                    disabled={loading}
                                    autoFocus
                                    aria-invalid={Boolean(error)}
                                    aria-describedby={error ? 'login-error-message' : undefined}
                                />
                            </div>
                        </div>

                        <div className="login-field">
                            <label htmlFor="password">
                                Password
                            </label>

                            <div className="login-input-wrapper">
                                <Lock
                                    size={16}
                                    className="login-input-icon"
                                    aria-hidden="true"
                                />

                                <input
                                    id="password"
                                    type={showPassword ? 'text' : 'password'}
                                    value={password}
                                    onChange={(event) => {
                                        setPassword(event.target.value)

                                        if (error) {
                                            setError('')
                                        }
                                    }}
                                    onKeyDown={handleKeyDown}
                                    onKeyUp={handleKeyUp}
                                    placeholder="Enter your password"
                                    autoComplete="current-password"
                                    spellCheck={false}
                                    disabled={loading}
                                    aria-invalid={Boolean(error)}
                                    aria-describedby={error ? 'login-error-message' : undefined}
                                />

                                <button
                                    type="button"
                                    className="password-toggle"
                                    onClick={() =>
                                        setShowPassword((current) => !current)
                                    }
                                    disabled={loading}
                                    aria-label={
                                        showPassword
                                            ? 'Hide password'
                                            : 'Show password'
                                    }
                                    title={
                                        showPassword
                                            ? 'Hide password'
                                            : 'Show password'
                                    }
                                >
                                    {showPassword ? (
                                        <EyeOff size={16} />
                                    ) : (
                                        <Eye size={16} />
                                    )}
                                </button>
                            </div>

                            {capsLockActive && (
                                <div className="login-caps-warning" role="status">
                                    Caps Lock is on
                                </div>
                            )}
                        </div>

                        {error && (
                            <div
                                id="login-error-message"
                                className="login-error"
                                role="alert"
                                aria-live="polite"
                            >
                                <AlertCircle size={16} />
                                <span>{error}</span>
                            </div>
                        )}

                        <button
                            className="login-submit"
                            type="submit"
                            disabled={loading}
                        >
                            {loading && (
                                <Loader2 size={16} className="spin" />
                            )}

                            {loading
                                ? 'Signing in...'
                                : 'Sign in'}
                        </button>
                    </form>

                    <div className="login-security">
                        <ShieldCheck size={14} />

                        <span>
                            Access is restricted to authorized users.
                        </span>
                    </div>
                </section>
            </main>

            <footer className="login-footer">
                <span>
                    © 2026 Tally Financial Intelligence
                </span>

                <span className="footer-separator" aria-hidden="true" />

                <span>
                    Authorized access only
                </span>
            </footer>
        </div>
    )
}

export default Login
