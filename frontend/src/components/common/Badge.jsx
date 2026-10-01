const variants = new Set(['neutral', 'primary', 'success', 'warning', 'error'])

export default function Badge({ children, variant = 'neutral', className = '' }) {
  const state = variants.has(variant) ? variant : 'neutral'
  return <span className={['badge', `badge--${state}`, className].filter(Boolean).join(' ')}>{children}</span>
}
