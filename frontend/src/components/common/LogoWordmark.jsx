import { Link } from 'react-router-dom'
import MadaarMark from './MadaarMark.jsx'

export default function LogoWordmark({ light = false, compact = false, monochrome = false, to = '/', ariaLabel = 'Madaar home' }) {
  return (
    <Link className={['wordmark', light && 'wordmark--light', compact && 'wordmark--compact'].filter(Boolean).join(' ')} to={to} aria-label={ariaLabel}>
      <span className="wordmark__mark" aria-hidden="true"><MadaarMark monochrome={monochrome} /></span>
      {!compact && <span className="wordmark__name">Madaar</span>}
    </Link>
  )
}
