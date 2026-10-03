import { useEffect, useRef } from 'react'
import { installPublicReveal } from '../../utils/publicReveal.js'

export default function PublicMarketingMotion({ children, enabled, routeKey }) {
  const root = useRef(null)
  useEffect(() => { if (enabled && root.current) return installPublicReveal(root.current) }, [enabled, routeKey])
  return <div ref={root} className="public-marketing-motion" data-public-motion={enabled ? '' : undefined}>{children}</div>
}
