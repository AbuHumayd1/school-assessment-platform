import { useEffect, useLayoutEffect, useRef } from 'react'
import { useLocation, useNavigationType } from 'react-router-dom'

function scrollImmediately(top) {
  const root = document.documentElement
  const previousBehavior = root.style.scrollBehavior
  root.style.scrollBehavior = 'auto'
  window.scrollTo(0, top)
  root.style.scrollBehavior = previousBehavior
}

function scrollToHash(hash) {
  if (!hash) return false
  let id
  try {
    id = decodeURIComponent(hash.slice(1))
  } catch {
    id = hash.slice(1)
  }
  const target = document.getElementById(id) || document.getElementsByName(id)[0]
  if (!target) return false

  const header = document.querySelector('.public-header, .student-topbar, .student-mobile-header, .exam-runner-header')
  const headerOffset = header?.getBoundingClientRect().bottom || 0
  const top = Math.max(0, target.getBoundingClientRect().top + window.scrollY - headerOffset)
  window.scrollTo({ top, behavior: 'smooth' })
  return true
}

export default function RouteScrollRestoration() {
  const location = useLocation()
  const navigationType = useNavigationType()
  const previousLocation = useRef(null)
  const positions = useRef(new Map())

  useEffect(() => {
    const key = location.key
    const recordPosition = () => positions.current.set(key, window.scrollY)
    recordPosition()
    window.addEventListener('scroll', recordPosition, { passive: true })
    return () => {
      window.removeEventListener('scroll', recordPosition)
    }
  }, [location.key])

  useLayoutEffect(() => {
    const previous = previousLocation.current
    if (previous) positions.current.set(previous.key, window.scrollY)
    previousLocation.current = { pathname: location.pathname, hash: location.hash, key: location.key }

    const pathnameChanged = !previous || previous.pathname !== location.pathname
    const hashChanged = !previous || previous.hash !== location.hash
    if (!pathnameChanged && !hashChanged) return

    if (location.hash) {
      requestAnimationFrame(() => {
        if (!scrollToHash(location.hash) && pathnameChanged && navigationType !== 'POP') scrollImmediately(0)
      })
      return
    }

    if (!pathnameChanged) return
    if (navigationType === 'POP') {
      const savedPosition = positions.current.get(location.key) ?? 0
      requestAnimationFrame(() => scrollImmediately(savedPosition))
      return
    }

    scrollImmediately(0)
  }, [location.pathname, location.hash, location.key, navigationType])

  return null
}
