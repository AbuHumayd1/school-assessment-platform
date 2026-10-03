import { staffApiFetch } from './api.js'

export const examStatuses = ['draft', 'review', 'approved', 'scheduled', 'archived']
export function ownerPath(path, institutionId, query = {}) {
  const params = new URLSearchParams({ ...query, institution: String(institutionId) })
  return `assessments/${path}?${params}`
}
export async function examRequest(institutionId, path = '', options = {}, query = {}, request = staffApiFetch) {
  return request(ownerPath(path, institutionId, query), options)
}
export async function listExams(institutionId, query = {}, options = {}, request = staffApiFetch) {
  const data = await examRequest(institutionId, '', options, query, request)
  if (!Array.isArray(data?.results) || !Number.isInteger(data.count) || data.results.some(row => row.institution !== institutionId)) throw new Error('Workspace context changed.')
  return data
}
export async function getExam(institutionId, id, options = {}, request = staffApiFetch) {
  const data = await examRequest(institutionId, `${id}/`, options, {}, request)
  if (data?.institution !== institutionId || String(data.id) !== String(id)) throw new Error('Workspace context changed.')
  return data
}
export function examError(error) {
  if (error.status === 409 && error.data?.code === 'credential_exists') return 'A credential already exists. Use Reset PIN to issue a new PIN.'
  if (error.status === 400) {
    const data = error.data
    const labels = { non_field_errors: '', title: 'Title', subject: 'Subject', group: 'Group / Cohort', questions: 'Questions', start_at: 'Start', end_at: 'End', duration_minutes: 'Duration', attempt_limit: 'Attempt limit', pass_mark: 'Pass mark', exam_code: 'Exam code', expires_at: 'Expiry', assessment: 'Exam', candidate: 'Candidate', status: 'Status', detail: '' }
    if (data && typeof data === 'object') return Object.entries(data).map(([field, value]) => `${labels[field] === '' ? '' : `${labels[field] || field}: `}${Array.isArray(value) ? value.join(' ') : String(value)}`).join(' ')
  }
  return 'We could not complete this request. Please try again.'
}
export function credentialState(credential, now = Date.now()) {
  if (!credential.active || credential.revoked_at) return 'Revoked'
  if (credential.candidate_status !== 'active') return 'Candidate inactive'
  if (credential.expires_at && Date.parse(credential.expires_at) <= now) return 'Expired'
  return 'Valid credential'
}
export function localDateValue(value) {
  if (!value) return ''
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return ''
  return new Date(date.getTime() - date.getTimezoneOffset() * 60000).toISOString().slice(0, 16)
}
export function examFields(values) {
  const fields = ['title', 'description', 'assessment_type', 'subject', 'group', 'duration_minutes', 'pass_mark', 'start_at', 'end_at', 'attempt_limit', 'resume_allowed', 'review_allowed', 'randomize_questions', 'randomize_options', 'security_level', 'candidate_access', 'result_visibility', 'result_release_mode']
  return Object.fromEntries(fields.map(key => [key, ['start_at', 'end_at'].includes(key) ? (values[key] ? new Date(values[key]).toISOString() : null) : key === 'group' ? (values[key] ? Number(values[key]) : null) : ['subject', 'duration_minutes', 'attempt_limit'].includes(key) ? Number(values[key]) : values[key]]))
}

// A request scope owns callbacks only until its page/context is disposed.
export function createOwnerScope() {
  let active = true
  return {
    cancel() { active = false },
    async run(load, success, failure) {
      try { const data = await load(); if (active) success(data) }
      catch (error) { if (active && error.name !== 'AbortError') failure(error) }
    },
  }
}
export function pinDisclosureReducer(state, event) {
  return event.type === 'issued' ? event.disclosure : null
}
