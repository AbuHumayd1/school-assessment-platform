import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch, clearSessionContext, setInstitutionContext } from '../services/api.js'
import { endSession, loadSessionUser } from '../services/session.js'
import { registerAccount } from '../services/onboarding.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const sessionVersion = useRef(0)

  const refreshUser = useCallback(async () => {
    const version = sessionVersion.current
    setLoading(true)
    setError(null)
    try {
      const currentUser = await loadSessionUser(apiFetch)
      if (version !== sessionVersion.current) return null
      setUser(currentUser)
      return currentUser
    } catch (error) {
      if (version !== sessionVersion.current) return null
      setInstitutionContext(null)
      setUser(null)
      setError(error)
      return null
    } finally {
      if (version === sessionVersion.current) setLoading(false)
    }
  }, [])

  useEffect(() => { refreshUser() }, [refreshUser])

  const signIn = useCallback(async (credentials) => {
    const data = await apiFetch('auth/login/', { method: 'POST', body: credentials })
    if (!data?.user || typeof data.user.id !== 'number') throw new Error('The server returned an unexpected sign-in response.')
    sessionVersion.current += 1
    setLoading(false)
    setInstitutionContext(null)
    setUser(data.user)
    setError(null)
    return data.user
  }, [])

  const register = useCallback(async (fields) => {
    const registeredUser = await registerAccount(apiFetch, fields)
    sessionVersion.current += 1
    setLoading(false)
    setInstitutionContext(null)
    setUser(registeredUser)
    setError(null)
    return registeredUser
  }, [])

  const signOut = useCallback(async () => {
    await endSession(apiFetch, () => {
      sessionVersion.current += 1
      clearSessionContext()
      setUser(null)
      setLoading(false)
      setError(null)
    })
  }, [])

  const value = useMemo(() => ({ user, loading, error, refreshUser, signIn, signOut, register }), [user, loading, error, refreshUser, signIn, signOut, register])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used within AuthProvider.')
  return auth
}
