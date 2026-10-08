export const PUBLIC_LANGUAGE_KEY = 'school-assessment.public-locale'
export const WORKSPACE_LANGUAGE_KEY = 'school-assessment.interface-language-mode'
export const LANGUAGE_EVENT = 'madaar-interface-language'
export function readPublicLocale(storage) {
  try {
    if (storage === undefined) storage = globalThis.localStorage
    const value = storage?.getItem(PUBLIC_LANGUAGE_KEY)
    if (value === 'ar' || value === 'en') return value
    return storage?.getItem(WORKSPACE_LANGUAGE_KEY) === 'arabic' ? 'ar' : 'en'
  } catch { return 'en' }
}
export function applyInterfaceLocale(locale, document = globalThis.document) {
  if (!document) return
  document.documentElement.lang = locale
  document.documentElement.dir = locale === 'ar' ? 'rtl' : 'ltr'
}
export function persistInterfaceLanguage(locale, mode = locale === 'ar' ? 'arabic' : 'english', environment = globalThis) {
  try {
    environment.localStorage?.setItem(PUBLIC_LANGUAGE_KEY, locale)
    environment.localStorage?.setItem(WORKSPACE_LANGUAGE_KEY, mode)
  } catch { /* Keep in-memory language when storage is unavailable. */ }
  applyInterfaceLocale(locale, environment.document)
  if (environment.dispatchEvent && environment.CustomEvent) environment.dispatchEvent(new environment.CustomEvent(LANGUAGE_EVENT, { detail: { locale, mode } }))
}
