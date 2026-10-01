import { Link } from 'react-router-dom'

export default function LogoWordmark({ light = false, compact = false, to = '/' }) {
  return (
    <Link className={['wordmark', light && 'wordmark--light', compact && 'wordmark--compact'].filter(Boolean).join(' ')} to={to} aria-label="School Assessment Platform home">
      <span className="wordmark__mark" aria-hidden="true">SA</span>
      {!compact && <span className="wordmark__name">School Assessment<span>Platform</span></span>}
    </Link>
  )
}
