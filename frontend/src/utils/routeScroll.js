export function createRouteScrollManager(environment) {
  const positions = new Map()
  let currentKey, previousRoute, cancelPending = () => {}
  const record = () => { if (currentKey !== undefined) positions.set(currentKey, environment.scrollY) }
  const scroll = top => {
    const root = environment.document.documentElement
    const previous = root.style.scrollBehavior
    root.style.scrollBehavior = 'auto'
    environment.scrollTo({ top, left: 0, behavior: 'instant' })
    root.style.scrollBehavior = previous
  }
  environment.addEventListener('scroll', record, { passive: true })
  return {
    navigate(location, navigationType) {
      const route = `${location.pathname}${location.search}${location.hash}`
      if (location.key === currentKey && route === previousRoute) return
      record()
      cancelPending()
      const initial = currentKey === undefined
      const saved = positions.get(location.key)
      currentKey = location.key
      previousRoute = route
      if (!initial && navigationType === 'POP' && saved !== undefined) { scroll(saved); return }
      if (!location.hash) { scroll(0); return }
      let id
      try { id = decodeURIComponent(location.hash.slice(1)) } catch { id = location.hash.slice(1) }
      let observer, timer, frame
      let stopped = false
      const stop = () => {
        stopped = true
        observer?.disconnect()
        if (timer !== undefined) environment.clearTimeout(timer)
        if (frame !== undefined) environment.cancelAnimationFrame(frame)
      }
      const find = () => {
        if (stopped) return
        const target = environment.document.getElementById(id) || environment.document.getElementsByName(id)[0]
        if (!target) return
        const header = environment.document.querySelector('.public-header, .student-topbar, .student-mobile-header, .exam-runner-header')
        scroll(Math.max(0, target.getBoundingClientRect().top + environment.scrollY - (header?.getBoundingClientRect().bottom || 0)))
        stop()
      }
      cancelPending = stop
      frame = environment.requestAnimationFrame(find)
      observer = new environment.MutationObserver(find)
      observer.observe(environment.document.body, { childList: true, subtree: true })
      timer = environment.setTimeout(stop, 2000)
    },
    dispose() { cancelPending(); environment.removeEventListener('scroll', record) },
  }
}
