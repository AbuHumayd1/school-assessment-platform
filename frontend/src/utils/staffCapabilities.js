const allWorkspaceRoles = new Set(['platform_admin', 'institution_admin', 'teacher', 'examiner'])
const administratorRoles = new Set(['platform_admin', 'institution_admin'])
const submissionRoles = new Set(['platform_admin', 'institution_admin', 'examiner'])

const capabilityRoles = {
  dashboard: allWorkspaceRoles,
  memberships: administratorRoles,
  institution_settings: administratorRoles,
  candidates: allWorkspaceRoles,
  groups: allWorkspaceRoles,
  subjects: allWorkspaceRoles,
  questions: allWorkspaceRoles,
  assessments: allWorkspaceRoles,
  submissions: submissionRoles,
  results: allWorkspaceRoles,
  reports: allWorkspaceRoles,
}

export function canAccessStaffCapability(role, capability) {
  return capabilityRoles[capability]?.has(role) ?? false
}

export function examWorkflowActions(role, exam) {
  if (!allWorkspaceRoles.has(role)) return []
  const admin = administratorRoles.has(role)
  if (exam.status === 'draft' && !exam.has_attempt_history) return ['edit', ...(exam.question_count > 0 ? ['submit-review'] : [])]
  if (exam.status === 'review') return [...(submissionRoles.has(role) ? ['request-changes'] : []), ...(admin ? ['approve'] : [])]
  if (exam.status === 'approved' && admin) return [...(exam.start_at && exam.end_at && (exam.candidate_access !== 'assigned_group' || exam.group) ? ['schedule'] : []), ...(!exam.has_attempt_history ? ['reopen'] : []), 'archive']
  if (exam.status === 'scheduled' && admin) return ['archive']
  return []
}
export function canManageQuickAccess(role) { return administratorRoles.has(role) }
