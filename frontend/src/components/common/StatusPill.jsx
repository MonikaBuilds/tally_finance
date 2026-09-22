function StatusPill({ status }) {
  const label = status ? String(status).replace(/_/g, ' ') : 'unknown'

  return <span className={`status-pill status-pill--${status}`}>{label}</span>
}

export default StatusPill
