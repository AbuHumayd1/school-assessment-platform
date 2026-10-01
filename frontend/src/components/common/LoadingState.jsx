export default function LoadingState({ label = 'Loading', className = '' }) {
  return <div className={['loading-state', className].filter(Boolean).join(' ')} role="status" aria-live="polite"><span className="spinner" aria-hidden="true" /><span>{label}</span></div>
}
