export const HERO_INTERVAL = 4500
export const heroAudiences = ['Built for Schools', 'Built for Madrasahs', 'Built for Training Programmes', 'Built for Professional Examinations', 'Built for Competitions', 'Built for Educational Institutes', 'Built for Organisations']
export function installHeroRotation(environment, advance) {
  const preference = environment.matchMedia?.('(prefers-reduced-motion: reduce)')
  let timer
  function configure() {
    if (timer !== undefined) environment.clearInterval(timer)
    timer = undefined
    if (!preference?.matches) timer = environment.setInterval(advance, HERO_INTERVAL)
  }
  configure()
  preference?.addEventListener?.('change', configure)
  return () => { if (timer !== undefined) environment.clearInterval(timer); preference?.removeEventListener?.('change', configure) }
}
