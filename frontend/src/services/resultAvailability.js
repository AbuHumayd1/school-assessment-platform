// Product choices map to the existing two Assessment fields; no extra policy.
export const resultAvailabilityChoices = [
  { value: 'manual', label: 'When I release them', result_visibility: 'after_submission', result_release_mode: 'manual_release' },
  { value: 'after_submit', label: 'After they submit', result_visibility: 'after_submission', result_release_mode: 'immediate' },
  { value: 'after_close', label: 'After the exam closes', result_visibility: 'scheduled_release', result_release_mode: 'manual_release' },
  { value: 'hidden', label: 'Keep results hidden', result_visibility: 'hidden', result_release_mode: 'approval_required' },
]
export function resultAvailability(exam) {
  if (exam.result_visibility === 'hidden') return 'hidden'
  if (exam.result_visibility === 'scheduled_release') return 'after_close'
  return exam.result_release_mode === 'immediate' ? 'after_submit' : 'manual'
}
export function resultAvailabilityLabel(exam) {
  return resultAvailabilityChoices.find(choice => choice.value === resultAvailability(exam)).label
}
export function resultAvailabilityExplanation(exam) {
  if (exam.result_visibility === 'hidden') return 'Results are kept hidden from candidates.'
  if (exam.result_visibility === 'scheduled_release') return exam.result_release_mode === 'immediate'
    ? 'Candidates can see published results only after the exam closes. Results marked before closing still need to be released.'
    : 'Candidates can see results only after the exam closes and you release them.'
  return exam.result_release_mode === 'immediate'
    ? 'Results become available when submitted attempts are marked.'
    : 'Candidates can see their results only after you release them.'
}
export function canReleaseResults(exam, now = Date.now()) {
  if (exam.result_visibility === 'hidden') return false
  if (exam.result_visibility === 'scheduled_release') return Boolean(exam.end_at && now >= Date.parse(exam.end_at))
  return exam.result_visibility === 'after_submission'
}
export function canEditResultSettings(exam, administrator) {
  return administrator && exam.status === 'draft' && !exam.has_attempt_history
}
