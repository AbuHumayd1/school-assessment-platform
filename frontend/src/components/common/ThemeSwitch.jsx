import { useTheme } from '../../context/ThemeContext.jsx'
import { useOptionalLanguageMode } from '../../context/LanguageModeContext.jsx'

export default function ThemeSwitch({ locale }) {
  const { theme, toggleTheme } = useTheme()
  const { languageMode } = useOptionalLanguageMode() || {}
  const arabic = locale ? locale === 'ar' : languageMode === 'arabic'
  const label = arabic ? (theme === 'dark' ? 'تفعيل المظهر الفاتح' : 'تفعيل المظهر الداكن') : (theme === 'dark' ? 'Switch to light mode' : 'Switch to dark mode')
  return <button className="theme-switch" type="button" aria-label={label} title={label} aria-pressed={theme === 'dark'} onClick={toggleTheme}>
    <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">{theme === 'dark' ? <><circle cx="12" cy="12" r="4" /><path d="M12 2v2m0 16v2M2 12h2m16 0h2M5 5l1.4 1.4m11.2 11.2L19 19M5 19l1.4-1.4M17.6 6.4 19 5" /></> : <path d="M20 15.5A8.5 8.5 0 0 1 8.5 4 8.5 8.5 0 1 0 20 15.5Z" />}</svg>
  </button>
}
