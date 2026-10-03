export function createExamAdapter(request, { mode = 'portal', onAccessExpired = () => {}, errorMessage = () => 'We could not complete this request. Check your connection and try again.' } = {}) {
  const prefix = mode === 'quick' ? 'quick-exam/attempt' : 'attempts'
  const path = id => {
    if (!/^\d+$/.test(String(id))) throw new Error('This examination link is not valid.')
    return `${prefix}/${id}`
  }
  async function call(route, options) {
    try { return await request(route, options) } catch (error) {
      if (mode !== 'quick') throw error
      if (error.status === 401) onAccessExpired()
      throw Object.assign(new Error(errorMessage(error)), { status: error.status })
    }
  }
  return {
    mode,
    getAttempt: id => call(`${path(id)}/`),
    getAttemptQuestions: id => call(`${path(id)}/questions/`),
    getAttemptQuestion: (id, question) => call(`${path(id)}/questions/${question}/`),
    saveAttemptAnswer: (id, question, selected) => call(`${path(id)}/questions/${question}/answer/`, { method: 'PUT', body: { selected_options: selected } }),
    setAttemptReview: (id, question, marked) => call(`${path(id)}/questions/${question}/review/`, { method: 'PATCH', body: { marked_for_review: marked } }),
    submitAttempt: id => call(`${path(id)}/submit/`, { method: 'POST', body: {} }),
    getAttemptIntegrity: async id => { await request('auth/csrf/'); return call(`${path(id)}/integrity/`) },
    recordAttemptIntegrity: (id, signal) => call(`${path(id)}/integrity/`, { method: 'POST', body: { signal }, keepalive: true }),
  }
}

export async function verifyQuickAccess(request, values) {
  await request('auth/csrf/')
  const response = await request('quick-exam/verify/', { method: 'POST', body: {
    exam_code: values.exam_code.trim(), candidate_id: values.candidate_id.trim(), pin: values.pin,
  } })
  if (response?.verified !== true) throw new Error('Unexpected verification response.')
  return response
}

export async function loadQuickAccess(request) {
  try {
    const context = await request('quick-exam/session/')
    const assessment = context?.assessment
    const availability = context?.availability
    const validDate = value => value == null || (typeof value === 'string' && Number.isFinite(Date.parse(value)))
    if (typeof context?.candidate?.candidate_id !== 'string' || !context.candidate.candidate_id ||
      !Number.isInteger(assessment?.id) || assessment.id < 1 || typeof assessment.title !== 'string' ||
      !Number.isInteger(assessment.duration_minutes) || assessment.duration_minutes < 1 ||
      !Number.isInteger(assessment.question_count) || assessment.question_count < 0 ||
      !validDate(assessment.start_at) || !validDate(assessment.end_at) ||
      typeof availability?.can_start !== 'boolean' || typeof availability.can_resume !== 'boolean' ||
      typeof availability.state !== 'string' || !Number.isInteger(availability.attempts_remaining) || availability.attempts_remaining < 0) throw new Error('Unexpected examination information.')
    return context
  } catch (error) { if (error.status === 401) return null; throw error }
}

export async function startQuickAccess(request) {
  const attempt = await request('quick-exam/start/', { method: 'POST', body: {} })
  if (!Number.isInteger(attempt?.id) || attempt.id < 1 || attempt.status !== 'in_progress') throw new Error('Unexpected attempt response.')
  return attempt
}

export async function endQuickAccess(request) {
  await request('auth/csrf/')
  return request('quick-exam/logout/', { method: 'POST', body: {} })
}

export async function endQuickAccessBeforeStart(request) {
  const current = await loadQuickAccess(request)
  if (current?.availability.state === 'in_progress') return false
  await endQuickAccess(request)
  return true
}

// Only a transient navigation guard. Recovery always comes from the server cookie.
let quickAttemptPath = null
export const rememberQuickAttempt = path => { quickAttemptPath = path }
export const getQuickAttemptPath = () => quickAttemptPath
export const clearQuickAttempt = id => {
  if (id === undefined || quickAttemptPath === `/take-exam/attempt/${id}`) quickAttemptPath = null
}
