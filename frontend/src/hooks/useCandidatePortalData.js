import { useCallback, useEffect, useState } from 'react'
import { useAuth } from '../context/AuthContext.jsx'
import { apiFetch } from '../services/api.js'

const friendlyError = 'Candidate information could not be loaded. Check your connection and try again.'

export default function useCandidatePortalData() {
  const { refreshUser } = useAuth()
  const [data, setData] = useState({ candidate: null, institution: null, groups: [], exams: [] })
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [accessState, setAccessState] = useState('ready')
  const [retryKey, setRetryKey] = useState(0)

  const retry = useCallback(() => setRetryKey(value => value + 1), [])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError(null)
      setAccessState('ready')
      try {
        const context = await apiFetch('candidate/me/')
        const examData = await apiFetch('candidate/me/exams/')
        if (!cancelled) setData({ ...context, exams: examData.exams || [] })
      } catch (requestError) {
        if (cancelled) return
        const code = requestError.data?.code || requestError.data?.detail?.code
        if (requestError.status === 401) {
          await refreshUser()
        } else if (code === 'candidate_not_linked') {
          setAccessState('unlinked')
        } else if (['candidate_inactive', 'institution_inactive', 'ambiguous_candidate_profiles'].includes(code) || requestError.status === 409) {
          setAccessState('restricted')
        } else {
          setError(friendlyError)
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    load()
    return () => { cancelled = true }
  }, [refreshUser, retryKey])

  return { ...data, loading, error, accessState, retry }
}
