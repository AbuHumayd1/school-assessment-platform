import { apiFetch } from './api.js'

const base = attemptId => `attempts/${attemptId}`
const activeAttemptKey = 'school-assessment.active-attempt-path'

export function rememberActiveAttempt(path) {
  sessionStorage.setItem(activeAttemptKey, path)
}

export function getRememberedAttemptPath() {
  return sessionStorage.getItem(activeAttemptKey)
}

export function clearRememberedAttempt(attemptId) {
  const path = getRememberedAttemptPath()
  if (path === `/student/exam/${attemptId}`) sessionStorage.removeItem(activeAttemptKey)
}

export function startAttempt(assessmentId) {
  return apiFetch('attempts/start/', { method: 'POST', body: { assessment: assessmentId } })
}

export function getAttempt(attemptId) {
  return apiFetch(`${base(attemptId)}/`)
}

export function getAttemptQuestions(attemptId) {
  return apiFetch(`${base(attemptId)}/questions/`)
}

export function getAttemptQuestion(attemptId, questionId) {
  return apiFetch(`${base(attemptId)}/questions/${questionId}/`)
}

export function saveAttemptAnswer(attemptId, questionId, selectedOptions) {
  return apiFetch(`${base(attemptId)}/questions/${questionId}/answer/`, {
    method: 'PUT',
    body: { selected_options: selectedOptions },
  })
}

export function setAttemptReview(attemptId, questionId, markedForReview) {
  return apiFetch(`${base(attemptId)}/questions/${questionId}/review/`, {
    method: 'PATCH',
    body: { marked_for_review: markedForReview },
  })
}

export function submitAttempt(attemptId) {
  return apiFetch(`${base(attemptId)}/submit/`, { method: 'POST', body: {} })
}

export async function getAttemptIntegrity(attemptId) {
  await apiFetch('auth/csrf/')
  return apiFetch(`${base(attemptId)}/integrity/`)
}

export function recordAttemptIntegrity(attemptId, signal) {
  return apiFetch(`${base(attemptId)}/integrity/`, {
    method: 'POST',
    body: { signal },
    keepalive: true,
  })
}
