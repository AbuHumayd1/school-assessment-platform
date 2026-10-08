import { apiFetch } from './api.js'

const base = 'platform/library/'
export const libraryList = (resource, query = {}, options = {}) => apiFetch(`${base}${resource}/?${new URLSearchParams(Object.entries(query).filter(([, value]) => value !== ''))}`, options)
export const librarySave = (resource, body, id, options = {}) => apiFetch(`${base}${resource}/${id ? `${id}/` : ''}`, { ...options, method: id ? 'PATCH' : 'POST', body })
export const libraryAction = (id, action) => apiFetch(`${base}questions/${id}/${action}/`, { method: 'POST', body: {} })

export async function libraryChoices(resource, query = {}, options = {}) {
  const rows = []
  let page = 1
  while (true) {
    const data = await libraryList(resource, { ...query, page }, options)
    rows.push(...(Array.isArray(data) ? data : data.results))
    if (!data.next) return rows
    page += 1
  }
}
