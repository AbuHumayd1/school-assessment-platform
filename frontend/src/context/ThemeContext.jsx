import { createContext, useContext, useEffect, useState } from 'react'
import { applyTheme, initialTheme } from '../utils/theme.js'

const ThemeContext = createContext({ theme: 'light', toggleTheme() {} })
export function ThemeProvider({ children }) {
  const [theme, setTheme] = useState(initialTheme)
  useEffect(() => { applyTheme(theme) }, [theme])
  function toggleTheme() {
    const next = theme === 'dark' ? 'light' : 'dark'
    setTheme(next); applyTheme(next, globalThis, true)
  }
  return <ThemeContext.Provider value={{ theme, toggleTheme }}>{children}</ThemeContext.Provider>
}
export function useTheme() { return useContext(ThemeContext) }
