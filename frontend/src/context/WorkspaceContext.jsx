import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { useAuth } from './AuthContext.jsx'
import { apiFetch, setInstitutionContext } from '../services/api.js'

const WorkspaceContext = createContext(null)
const STORAGE_PREFIX = 'school-assessment.active-workspace.'

function storageKey(userId) {
  return `${STORAGE_PREFIX}${userId}`
}

function readStoredWorkspace(userId) {
  try {
    const value = localStorage.getItem(storageKey(userId))
    return value && /^\d+$/.test(value) ? value : null
  } catch {
    return null
  }
}

function writeStoredWorkspace(userId, workspaceId) {
  try {
    if (workspaceId == null) localStorage.removeItem(storageKey(userId))
    else localStorage.setItem(storageKey(userId), String(workspaceId))
  } catch { /* Workspace selection remains available in memory. */ }
}

export function WorkspaceProvider({ children }) {
  const { user, loading: authLoading } = useAuth()
  const [workspaces, setWorkspaces] = useState([])
  const [currentWorkspace, setCurrentWorkspace] = useState(null)
  const [loading, setLoading] = useState(true)
  const [resolvedUserId, setResolvedUserId] = useState(null)
  const [error, setError] = useState(null)
  const [retryKey, setRetryKey] = useState(0)
  const previousUserId = useRef(null)
  const retry = useCallback(() => setRetryKey(value => value + 1), [])

  useEffect(() => {
    const refreshAuthorization = () => retry()
    window.addEventListener('workspace-context-invalidated', refreshAuthorization)
    return () => window.removeEventListener('workspace-context-invalidated', refreshAuthorization)
  }, [retry])

  useEffect(() => {
    let cancelled = false
    const userId = user?.id

    setInstitutionContext(null)
    setWorkspaces([])
    setCurrentWorkspace(null)
    setError(null)
    setResolvedUserId(null)

    if (!userId) {
      if (previousUserId.current != null) writeStoredWorkspace(previousUserId.current, null)
      previousUserId.current = null
      setLoading(authLoading)
      return () => { cancelled = true }
    }

    previousUserId.current = userId
    setLoading(true)
    async function loadWorkspaces() {
      try {
        const response = await apiFetch('auth/context/')
        const available = Array.isArray(response?.workspaces) ? response.workspaces.filter(
          item => Number.isInteger(item?.institution?.id) && typeof item?.institution?.name === 'string' && typeof item?.role === 'string',
        ) : []
        if (cancelled) return

        setWorkspaces(available)
        const storedId = readStoredWorkspace(userId)
        const storedSelection = storedId == null ? null : available.find(
          item => String(item.institution.id) === storedId,
        ) || null

        // An old selection is never trusted. A sole currently authorized workspace
        // can still be selected automatically; multi-workspace users choose explicitly.
        if (storedId && !storedSelection) writeStoredWorkspace(userId, null)
        const selected = available.length === 1 ? available[0] : storedSelection
        setCurrentWorkspace(selected)
        setInstitutionContext(selected?.institution.id ?? null)
        if (available.length === 1) writeStoredWorkspace(userId, available[0].institution.id)
      } catch (requestError) {
        if (!cancelled) setError(requestError)
      } finally {
        if (!cancelled) {
          setResolvedUserId(userId)
          setLoading(false)
        }
      }
    }

    loadWorkspaces()
    return () => { cancelled = true }
  }, [user?.id, authLoading, retryKey])

  const selectWorkspace = useCallback((institutionId) => {
    const next = workspaces.find(item => String(item.institution.id) === String(institutionId))
    if (!next || !user?.id) return false
    setCurrentWorkspace(next)
    setInstitutionContext(next.institution.id)
    writeStoredWorkspace(user.id, next.institution.id)
    return true
  }, [user?.id, workspaces])

  const clearSelection = useCallback(() => {
    setCurrentWorkspace(null)
    setInstitutionContext(null)
    if (user?.id) writeStoredWorkspace(user.id, null)
  }, [user?.id])

  const contextLoading = authLoading || loading || (user?.id ?? null) !== resolvedUserId
  const value = useMemo(() => ({
    workspaces,
    currentWorkspace,
    currentRole: currentWorkspace?.role ?? null,
    loading: contextLoading,
    error,
    accessState: contextLoading ? 'loading' : error ? 'error' : workspaces.length === 0 ? 'no_workspace' : currentWorkspace ? 'ready' : 'select_workspace',
    selectWorkspace,
    clearSelection,
    retry,
  }), [workspaces, currentWorkspace, contextLoading, error, selectWorkspace, clearSelection, retry])

  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>
}

export function useWorkspace() {
  const context = useContext(WorkspaceContext)
  if (!context) throw new Error('useWorkspace must be used within WorkspaceProvider.')
  return context
}
