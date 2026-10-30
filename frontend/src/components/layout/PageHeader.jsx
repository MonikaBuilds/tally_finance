import BackButton from '../common/BackButton'

function PageHeader({
  title,
  subtitle,
  actions,
  backFallback,
  onBack,
  backButton,
}) {
  const showBack = Boolean(backFallback || onBack || backButton)

  return (
    <div className="page-header">
      <div className="page-header-main">
        {showBack && (backButton || <BackButton fallbackTo={backFallback} onClick={onBack} />)}
        <div className="page-header-text">
          <h1>{title}</h1>
          {subtitle && <p className="page-subtitle">{subtitle}</p>}
        </div>
      </div>
      {actions && <div className="page-header-actions">{actions}</div>}
    </div>
  )
}

export default PageHeader
