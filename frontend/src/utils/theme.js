export const THEME_KEY = 'madaar.theme'
export function savedTheme(storage) {
  try { const value = (storage === undefined ? globalThis.localStorage : storage)?.getItem(THEME_KEY); return ['light', 'dark'].includes(value) ? value : null } catch { return null }
}
export function initialTheme(environment = globalThis) {
  let preference
  try { preference = savedTheme(environment.localStorage) } catch { /* Storage access can be disabled. */ }
  return preference || (environment.matchMedia?.('(prefers-color-scheme: dark)').matches ? 'dark' : 'light')
}
export function applyTheme(theme, environment = globalThis, persist = false) {
  if (!['light', 'dark'].includes(theme)) return
  if (environment.document) {
    environment.document.documentElement.dataset.theme = theme
    environment.document.documentElement.style.colorScheme = theme
  }
  if (persist) { try { environment.localStorage?.setItem(THEME_KEY, theme) } catch { /* In-memory choice still works. */ } }
}
