export async function endSession(request, clearState) {
  try {
    await request('auth/logout/', { method: 'POST' })
  } catch (error) {
    // An expired server session is already signed out. Other failures must remain retryable.
    if (error.status !== 401) {
      if (error.status !== 403) throw error
      // SessionAuthentication may report an absent session as 403. Verify it;
      // a CSRF rejection with a still-active session must not pretend to log out.
      let expired = false
      try { await request('auth/me/') } catch (checkError) { expired = checkError.status === 401 }
      if (!expired) throw error
    }
  }
  clearState()
}

export async function candidateAccess(request, user, options = {}) {
  if (!user?.is_candidate) return false
  try {
    const context = await request('candidate/me/', options)
    return Number.isInteger(context?.candidate?.id) && Number.isInteger(context?.institution?.id)
  } catch (error) {
    if ([403, 404, 409].includes(error.status)) return false
    throw error
  }
}
