function Card({ title, subtitle, actions, className = '', children }) {
  const hasHeader = title || subtitle || actions

  return (
    <div className={className ? `card ${className}` : 'card'}>
      {hasHeader && (
        <div className="card-header">
          <div>
            {title && <h3 className="card-title">{title}</h3>}
            {subtitle && <p className="card-subtitle">{subtitle}</p>}
          </div>
          {actions && <div className="page-header-actions">{actions}</div>}
        </div>
      )}
      {children}
    </div>
  )
}

export default Card
