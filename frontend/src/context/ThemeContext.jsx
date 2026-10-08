import { createContext, useContext, useEffect, useState } from 'react'
import { applyTheme, initialTheme, savedTheme } from '../utils/theme.js'

const ThemeContext = createContext({ theme: 'light', toggleTheme() {} })
export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(initialTheme)
  const [explicit, setExplicit] = useState(() => Boolean(savedTheme()))
  useEffect(() => { applyTheme(theme) }, [theme])
  useEffect(() => {
    if (explicit) return undefined
    const media = window.matchMedia?.('(prefers-color-scheme: dark)')
    const change = event => setTheme(event.matches ? 'dark' : 'light')
    media?.addEventListener?.('change', change)
    return () => media?.removeEventListener?.('change', change)
  }, [explicit])
  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark'
    setExplicit(true); setTheme(next); applyTheme(next, globalThis, true)
  }
  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>
}
export function useTheme() { return useContext(ThemeContext) }
