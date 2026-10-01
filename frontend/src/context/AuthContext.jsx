import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { apiFetch } from '../services/api.js'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)

  const refreshUser = useCallback(async () => {
    setLoading(true)
    try {
      const currentUser = await apiFetch('auth/me/')
      setUser(currentUser?.authenticated === false ? null : currentUser)
      return currentUser
    } catch (error) {
      if (error.status === 401) setUser(null)
      else setUser(null)
      return null
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { refreshUser() }, [refreshUser])

  const signIn = useCallback(async (credentials) => {
    const data = await apiFetch('auth/login/', { method: 'POST', body: credentials })
    if (!data?.user || typeof data.user.id !== 'number') throw new Error('The server returned an unexpected sign-in response.')
    setUser(data.user)
    return data.user
  }, [])

  const signOut = useCallback(async () => {
    await apiFetch('auth/logout/', { method: 'POST' })
    setUser(null)
  }, [])

  const value = useMemo(() => ({ user, loading, refreshUser, signIn, signOut }), [user, loading, refreshUser, signIn, signOut])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() {
  const auth = useContext(AuthContext)
  if (!auth) throw new Error('useAuth must be used within AuthProvider.')
  return auth
}
