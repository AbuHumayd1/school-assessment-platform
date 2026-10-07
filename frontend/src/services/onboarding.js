// Keep state transitions dependent on confirmed session and authorization responses.
export async function registerAccount(request, fields) {
  const response = await request('auth/register/', { method: 'POST', body: fields })
  if (!Number.isInteger(response?.user?.id) || !response.user.email) throw new Error('Registration could not be confirmed.')
  return response.user
}

export async function createWorkspace(request, fields) {
  const response = await request('institutions/create-workspace/', { method: 'POST', body: fields })
  if (!Number.isInteger(response?.id)) throw new Error('Workspace creation could not be confirmed.')
  return response.id
}

export async function createdWorkspaceContext(request, userId, workspaceId) {
  const response = await request('auth/context/')
  if (response?.user?.id !== userId || !Array.isArray(response.workspaces)) throw new Error('Workspace access could not be confirmed.')
  const workspaces = response.workspaces.filter(item => Number.isInteger(item?.institution?.id) && typeof item.institution.name === 'string' && typeof item.role === 'string')
  const selected = workspaces.find(item => item.institution.id === workspaceId && ['institution_admin', 'platform_admin'].includes(item.role))
  if (!selected) throw new Error('Workspace access could not be confirmed.')
  return { workspaces, selected, isPlatformAdmin: response.is_platform_admin === true }
}

export const onboardingDestination = '/setup'
