const allWorkspaceRoles = new Set(['platform_admin', 'institution_admin', 'teacher', 'examiner'])
const administratorRoles = new Set(['platform_admin', 'institution_admin'])
const submissionRoles = new Set(['platform_admin', 'institution_admin', 'examiner'])

const capabilityRoles = {
  dashboard: administratorRoles,
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
