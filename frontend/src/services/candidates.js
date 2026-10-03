export const candidateStatuses = ['active', 'inactive', 'archived']

export const deletionHistoryMessage = 'This candidate has assessment history and cannot be permanently deleted. Deactivate the candidate instead.'

export async function deleteCandidate(request, institutionId, id) {
  const response = await request(`candidates/${id}/?institution=${institutionId}`, { method: 'DELETE' })
  if (response !== null) throw new Error('Candidate deletion could not be confirmed.')
}

export function candidateDeletionError(error) {
  return error.status === 409 && error.data?.code === 'candidate_has_assessment_history'
    ? deletionHistoryMessage : 'We could not complete this request. Please try again.'
}

export function portalAccessState(candidate) {
  if (!candidate?.portal_account) return 'not_enabled'
  if (!candidate.portal_account.is_active) return 'account_inactive'
  return candidate.status === 'active' ? 'enabled' : 'candidate_inactive'
}

export function candidateFields(values) {
  return {
    first_name: values.first_name.trim(), last_name: values.last_name.trim(), candidate_id: values.candidate_id.trim(),
    email: values.email.trim(), phone: values.phone.trim(), date_of_birth: values.date_of_birth || null, status: values.status,
  }
}

export async function listCandidates(request, institutionId, { search = '', status = '', page = 1, signal } = {}) {
  const query = new URLSearchParams({ institution: String(institutionId), page: String(page) })
  if (search) query.set('search', search)
  if (status) query.set('status', status)
  const response = await request(`candidates/?${query}`, { signal })
  if (!Array.isArray(response?.results) || !Number.isInteger(response.count) || response.results.some(row => row.institution !== institutionId)) {
    throw new Error('Candidate list could not be confirmed.')
  }
  return response
}

export async function getCandidate(request, institutionId, id, options = {}) {
  const response = await request(`candidates/${id}/?institution=${institutionId}`, options)
  if (response?.id !== id || response?.institution !== institutionId) throw new Error('Candidate details could not be confirmed.')
  return response
}

export async function saveCandidate(request, institutionId, id, values, { profileOnly = false } = {}) {
  const fields = candidateFields(values)
  if (id && profileOnly) { delete fields.candidate_id; delete fields.status }
  const response = await request(id ? `candidates/${id}/` : 'candidates/', {
    method: id ? 'PATCH' : 'POST', body: { ...fields, institution: institutionId },
  })
  if (!Number.isInteger(response?.id) || response.institution !== institutionId) throw new Error('Candidate changes could not be confirmed.')
  return response
}

export async function provisionCandidate(request, institutionId, id) {
  const response = await request(`candidates/${id}/provision-access/?institution=${institutionId}`, { method: 'POST', body: {} })
  if (!response?.account?.email || typeof response.initial_password !== 'string' || !response.initial_password) throw new Error('Portal access could not be confirmed.')
  return response
}
