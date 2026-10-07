// Mode is required authorization metadata; never infer full access from its absence.
export function validWorkspaces(response) {
  if (!Array.isArray(response?.workspaces)) throw new Error('Workspace access could not be confirmed.')
  if (response.workspaces.some(item => !Number.isInteger(item?.institution?.id)
    || typeof item?.institution?.name !== 'string' || typeof item?.role !== 'string'
    || !['full_workspace', 'managed_exam'].includes(item?.institution?.workspace_mode))) {
    throw new Error('Workspace configuration could not be confirmed. Reload after checking the server.')
  }
  return response.workspaces
}

export function initialWorkspace(available, isPlatformAdmin, storedSelection) {
  if (isPlatformAdmin) return storedSelection
  return available.length === 1 ? available[0] : null
}
