const API_BASE_URL = (import.meta.env.VITE_API_BASE_URL || '/api/v1').replace(/\/$/, '')
const unsafeMethods = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])
let csrfToken = null

export class ApiError extends Error {
  constructor(message, { status, data } = {}) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.data = data
  }
}

async function readResponse(response) {
  if (response.status === 204) return null
  const contentType = response.headers.get('content-type') || ''
  if (contentType.includes('application/json')) {
    try {
      return await response.json()
    } catch {
      throw new ApiError('The server returned an unexpected response.', { status: response.status })
    }
  }
  const text = await response.text()
  if (response.ok) throw new ApiError('The server returned an unexpected response.', { status: response.status })
  return text
}

async function send(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const headers = new Headers(options.headers || {})
  headers.set('Accept', 'application/json')
  let body = options.body
  if (body !== undefined && body !== null && typeof body !== 'string' && !(body instanceof FormData)) {
    headers.set('Content-Type', 'application/json')
    body = JSON.stringify(body)
  }

  const response = await fetch(`${API_BASE_URL}/${path.replace(/^\/+/, '')}`, {
    ...options,
    method,
    body,
    headers,
    credentials: 'include',
  })
  const data = await readResponse(response)
  if (data && typeof data.csrfToken === 'string') csrfToken = data.csrfToken
  if (!response.ok) {
    const message = typeof data?.detail === 'string' ? data.detail : `Request failed (${response.status}).`
    throw new ApiError(message, { status: response.status, data })
  }
  return data
}

async function ensureCsrfToken() {
  if (!csrfToken) {
    const data = await send('auth/csrf/')
    if (typeof data?.csrfToken !== 'string' || !data.csrfToken) {
      throw new ApiError('The server could not prepare a secure request.')
    }
  }
  return csrfToken
}

export async function apiFetch(path, options = {}) {
  const method = (options.method || 'GET').toUpperCase()
  const requestOptions = { ...options, method }
  if (unsafeMethods.has(method)) {
    const token = await ensureCsrfToken()
    requestOptions.headers = { ...options.headers, 'X-CSRFToken': token }
  }
  return send(path, requestOptions)
}
