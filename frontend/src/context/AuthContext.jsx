import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { apiFetch, clearSessionContext, setInstitutionContext } from '../services/api.js'
import { endSession } from '../services/session.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  const sessionVersion = useRef(0)

  const refreshUser = useCallback(async () => {
    const version = sessionVersion.current
    setLoading(true)
    try {
      const currentUser = await apiFetch('auth/me/')
      if (version !== sessionVersion.current) return null
      setUser(currentUser?.authenticated === false ? null : currentUser)
      return currentUser
    } catch (error) {
      if (version !== sessionVersion.current) return null
      setInstitutionContext(null)
      if (error.status === 401) setUser(null)
      else setUser(null)
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
    return data.user
  }, [])

  const signOut = useCallback(async () => {
    await endSession(apiFetch, () => {
      sessionVersion.current += 1
      clearSessionContext()
      setUser(null)
      setLoading(false)
    })
  }, [])

  const value = useMemo(() => ({ user, loading, refreshUser, signIn, signOut }), [user, loading, refreshUser, signIn, signOut])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used within AuthProvider.')
  return auth
}
