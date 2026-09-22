import { AlertCircle } from 'lucide-react'

function ErrorMessage({ message }) {
  return (
    <div className="error-message" role="alert">
      <AlertCircle size={18} />
      <span>Something went wrong{message ? `: ${message}` : '.'}</span>
    </div>
  )
}

export default ErrorMessage
