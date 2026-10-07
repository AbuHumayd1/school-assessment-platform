import { apiFetch } from './api.js'
import { examRequest } from './assessments.js'

export function ownerOutcomes(institution, exam, section, query = {}, options = {}, request) {
  return examRequest(institution, `${exam}/${section}/`, options, query, request)
}
export async function outcomesIndex(institution, section, query = {}, options = {}, request) {
  const data = await examRequest(institution, `outcomes/${section}/`, options, query, request)
  if (!Array.isArray(data?.results) || !Number.isInteger(data.count) || data.results.some(row => row.institution !== institution || !row.summary)) throw new Error('Workspace context changed.')
  return data
}
export function releaseOutcomes(institution, exam, result = null, request) {
  return examRequest(institution, `${exam}/results/${result == null ? '' : `${result}/`}release/`, { method: 'POST', body: {} }, {}, request)
}
export async function ownResults(options = {}, request = apiFetch) {
  const data = await request('results/my/', options)
  if (!Array.isArray(data) || data.some(row => !row || typeof row.assessment_title !== 'string' || typeof row.passed !== 'boolean')) throw new Error('The server returned an unexpected response.')
  return data
}
export async function downloadReport(institution, exam, format, options = {}, request) {
  if (!['csv', 'pdf', 'docx'].includes(format)) throw new Error('Unsupported report format.')
  return ownerOutcomes(institution, exam, `reports/${format}`, {}, { ...options, responseType: 'blob' }, request)
}
export function saveReport(blob, exam, format) {
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url; link.download = `${String(exam.title).replace(/[^\p{L}\p{N} -]/gu, '').slice(0, 80) || 'exam'}-results.${format}`
  document.body.append(link); link.click(); link.remove()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
