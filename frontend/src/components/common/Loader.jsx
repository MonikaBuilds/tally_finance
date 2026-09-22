import { Loader2 } from 'lucide-react'

function Loader({ label = 'Loading…' }) {
  return (
    <div className="loader" role="status">
      <Loader2 size={18} className="spin" />
      <span>{label}</span>
    </div>
  )
}

export default Loader
