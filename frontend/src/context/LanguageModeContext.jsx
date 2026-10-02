import { createContext, useContext, useEffect, useMemo, useState } from 'react'

const LanguageModeContext = createContext(null)
const STORAGE_KEY = 'school-assessment.interface-language-mode'
const MODES = new Set(['english', 'bilingual', 'arabic'])

function readMode() {
  try {
    const stored = localStorage.getItem(STORAGE_KEY)
    return MODES.has(stored) ? stored : 'english'
  } catch {
    return 'english'
  }
}

export function LanguageModeProvider({ children }) {
  const [languageMode, setLanguageMode] = useState(readMode)

  useEffect(() => {
    try { localStorage.setItem(STORAGE_KEY, languageMode) } catch { /* Preference remains available in memory. */ }
  }, [languageMode])

  const value = useMemo(() => ({
    languageMode,
    setLanguageMode: mode => { if (MODES.has(mode)) setLanguageMode(mode) },
    label: (english, arabic) => {
      if (languageMode === 'arabic') return arabic
      if (languageMode === 'bilingual') return `${english} · ${arabic}`
      return english
    },
    direction: languageMode === 'arabic' ? 'rtl' : 'ltr',
  }), [languageMode])

  return <LanguageModeContext.Provider value={value}>{children}</LanguageModeContext.Provider>
}

export function useLanguageMode() {
  const context = useContext(LanguageModeContext)
  if (!context) throw new Error('useLanguageMode must be used within LanguageModeProvider.')
  return context
}
