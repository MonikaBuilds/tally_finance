import BackButton from '../../components/common/BackButton'

// Backwards-compatible wrapper delegating to the unified BackButton
function TrialBalanceBackButton({ fallbackTo, onClick, label = 'Back' }) {
  return <BackButton fallbackTo={fallbackTo} onClick={onClick} label={label} />
}

export default TrialBalanceBackButton
