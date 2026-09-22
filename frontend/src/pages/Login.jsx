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
import { apiPost, setAccessToken } from '../api/client'
import './Login.css'

function Login({ onLogin }) {
    const [username, setUsername] = useState('')
    const [password, setPassword] = useState('')
    const [showPassword, setShowPassword] = useState(false)
    const [error, setError] = useState('')
    const [loading, setLoading] = useState(false)

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
            const response = await apiPost('/auth/login', {
                username: cleanUsername,
                password,
            })

            setAccessToken(response.access_token)

            sessionStorage.setItem(
                'chat_user',
                JSON.stringify({
                    user_id: response.user_id,
                    username: response.username,
                    companies: response.companies,
                }),
            )

            if (
                Array.isArray(response.companies) &&
                response.companies.length === 1
            ) {
                sessionStorage.setItem(
                    'selected_company',
                    response.companies[0],
                )
            } else {
                sessionStorage.removeItem(
                    'selected_company',
                )
            }

            onLogin?.(response)
        } catch (err) {
            setError(
                err?.message ||
                'Unable to sign in. Please verify your credentials.'
            )
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
                                    disabled={loading}
                                    autoFocus
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
                                    placeholder="Enter your password"
                                    autoComplete="current-password"
                                    disabled={loading}
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
                        </div>

                        {error && (
                            <div
                                className="login-error"
                                role="alert"
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
