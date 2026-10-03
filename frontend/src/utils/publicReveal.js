// Explicit targets belong to marketing JSX. Content is visible before enhancement.
export function installPublicReveal(root, environment = window) {
  const targets = [...root.querySelectorAll('[data-public-reveal]')]
  const preference = environment.matchMedia?.('(prefers-reduced-motion: reduce)')
  const revealed = new Set()
  const frames = new Set()
  let observer
  let stopped = false
  function reveal(element) {
    if (revealed.has(element)) return
    revealed.add(element)
    element.classList.remove('public-reveal--pending')
    element.classList.add('public-reveal--shown')
    observer?.unobserve?.(element)
  }
  function showAll() {
    stopped = true
    observer?.disconnect()
    for (const frame of frames) environment.cancelAnimationFrame?.(frame)
    targets.forEach(element => {
      revealed.add(element)
      element.classList.remove('public-reveal', 'public-reveal--pending', 'public-reveal--shown')
      element.style.removeProperty('--reveal-delay')
    })
  }
  if (preference?.matches || !environment.IntersectionObserver) return () => {}
  try {
    observer = new environment.IntersectionObserver(entries => {
      for (const entry of entries) if (entry.isIntersecting) reveal(entry.target)
    }, { threshold: .15, rootMargin: '0px 0px -40px 0px' })
    targets.forEach(element => {
      const group = element.closest?.('[data-public-reveal-group]')
      const index = group ? [...group.querySelectorAll('[data-public-reveal]')].indexOf(element) : 0
      element.style.setProperty('--reveal-delay', `${Math.min(Math.max(index, 0) * 80, 400)}ms`)
      element.classList.add('public-reveal')
      // Keep initially visible content readable; observe individual below-fold rows/cards.
      const rect = element.getBoundingClientRect()
      if (rect.top < environment.innerHeight && rect.bottom > 0) { reveal(element); return }
      element.classList.add('public-reveal--pending')
      // Give the pending style a painted frame before IO can switch to the entrance state.
      const observe = () => { if (!stopped) { try { observer.observe(element) } catch { showAll() } } }
      if (environment.requestAnimationFrame) {
        frames.add(environment.requestAnimationFrame(() => {
          if (!stopped) frames.add(environment.requestAnimationFrame(observe))
        }))
      } else observe()
    })
    preference?.addEventListener?.('change', showAll)
  } catch { showAll() }
  return () => {
    showAll()
    preference?.removeEventListener?.('change', showAll)
    targets.forEach(element => { element.classList.remove('public-reveal', 'public-reveal--shown') })
  }
}
