import { useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

/**
 * Standard industrial back button.
 *
 * Steps back one entry in the browser session history if in-app history
 * exists. If opened directly via URL or refresh (location.key is 'default'),
 * it navigates safely to `fallbackTo` instead of leaving the application.
 */
function BackButton({ fallbackTo = '/', onClick, label = 'Back', className = '' }) {
  const navigate = useNavigate()
  const location = useLocation()

  function handleBack() {
    if (onClick) {
      onClick()
      return
    }

    if (location.key !== 'default') {
      navigate(-1)
    } else if (fallbackTo) {
      navigate(fallbackTo, { replace: true })
    } else {
      navigate(-1)
    }
  }

  return (
    <button
      type="button"
      className={`btn btn-secondary back-button ${className}`.trim()}
      onClick={handleBack}
      title="Go back to previous page"
      aria-label="Go back"
    >
      <ArrowLeft size={16} />
      <span>{label}</span>
    </button>
  )
}

export default BackButton

