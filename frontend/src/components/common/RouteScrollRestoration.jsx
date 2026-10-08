import { useLayoutEffect, useRef } from 'react'
import { useLocation, useNavigationType } from 'react-router-dom'
import { createRouteScrollManager } from '../../utils/routeScroll.js'

export default function RouteScrollRestoration() {
  const location = useLocation()
  const navigationType = useNavigationType()
  const manager = useRef(null)
  useLayoutEffect(() => {
    const controller = createRouteScrollManager(window)
    manager.current = controller
    return () => { controller.dispose(); manager.current = null }
  }, [])
  useLayoutEffect(() => {
    manager.current.navigate(location, navigationType)
  }, [location.pathname, location.search, location.hash, location.key, navigationType])
  return null
}