import { canAccessStaffCapability } from './staffCapabilities.js'

const staffRoutes = { students: 'candidates', staff: 'memberships', classes: 'groups', subjects: 'subjects', questions: 'questions', exams: 'assessments', submissions: 'submissions', results: 'results', reports: 'reports', settings: 'institution_settings' }

export function signInDestination(user, workspaces, from, hasCandidateAccess = false, selectedRole = null) {
  const hasWorkspace = workspaces.length > 0
  const pathname = from?.pathname
  const safePath = typeof pathname === 'string' && !/[\\\s?#%]/.test(pathname)
    && !pathname.split('/').some(part => part === '.' || part === '..')
  const staffMatch = safePath && pathname.match(/^\/app(?:\/([a-z]+))?\/?$/)
  const role = selectedRole || (workspaces.length === 1 ? workspaces[0].role : null)
  const staffReturn = hasWorkspace && staffMatch && (!staffMatch[1] || canAccessStaffCapability(role, staffRoutes[staffMatch[1]]))
  const candidateReturn = safePath && hasCandidateAccess && /^\/student(?:\/(?:exams|results|exam\/\d+))?\/?$/.test(pathname)
  const search = typeof from?.search === 'string' && from.search.startsWith('?') ? from.search : ''
  const hash = typeof from?.hash === 'string' && from.hash.startsWith('#') ? from.hash : ''
  if (staffReturn || candidateReturn) return `${pathname}${search}${hash}`
  if (hasWorkspace && hasCandidateAccess) return null
  return hasWorkspace ? '/app' : hasCandidateAccess ? '/student' : null
}
