import { useLocation, useNavigate } from 'react-router'
import { ArrowLeft } from 'lucide-react'

// Back button for every page reached from the Trial Balance.
//
// Normally it steps back one entry in the browser history, which puts
// the user on the previous Trial Balance page with the same URL - so
// the same group / dates as before. If the page was opened directly
// (no in-app history to go back to, `location.key` is "default"), it
// falls back to the Trial Balance for the same period instead of
// leaving the app.
function TrialBalanceBackButton({ fallbackTo }) {
  const navigate = useNavigate()
  const location = useLocation()

  function handleBack() {
    if (location.key !== 'default') {
      navigate(-1)
    } else {
      navigate(fallbackTo, { replace: true })
    }
  }

  return (
    <button type="button" className="btn btn-secondary" onClick={handleBack}>
      <ArrowLeft size={16} /> Back
    </button>
  )
}

export default TrialBalanceBackButton
