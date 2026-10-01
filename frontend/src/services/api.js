const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')

export class ApiError extends Error {
  constructor(message, { status, data } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

export async function apiFetch(path, options = {}) {
  const normalizedPath = path.replace(/^\/+/, '')
  const response = await fetch(`${API_BASE_URL}/${normalizedPath}`, {
    ...options,
    headers: {
      Accept: 'application/json',
      ...options.headers,
    },
  })

  const contentType = response.headers.get('content-type') || ''
  const data = contentType.includes('application/json')
    ? await response.json()
    : await response.text()

  if (!response.ok) {
    throw new ApiError(`Request failed with status ${response.status}`, {
      status: response.status,
      data,
    })
  }

  return data
}
