// Best-effort same-origin coordination, never an authentication boundary.
// This slot represents the browser's shared Quick cookie, not candidate identity.
export const QUICK_CLIENT_KEY = 'school-assessment.quick-client'
const leaseMs = 15000

export function createQuickTabOwner(environment, onLost = () => {}) {
  const id = environment.crypto.randomUUID()
  let record = null, active = false, closed = false, interval = null
  const pending = new Set()
  let channel = null
  try { channel = new environment.BroadcastChannel(QUICK_CLIENT_KEY) } catch { /* Storage events remain available. */ }
  const now = () => environment.Date?.now() ?? Date.now()
  const wait = ms => new Promise(resolve => environment.setTimeout(resolve, ms))
  function read() {
    try { return JSON.parse(environment.localStorage.getItem(QUICK_CLIENT_KEY)) } catch { return record }
  }
  function write(value) {
    record = value
    try { value ? environment.localStorage.setItem(QUICK_CLIENT_KEY, JSON.stringify(value)) : environment.localStorage.removeItem(QUICK_CLIENT_KEY) } catch { /* BroadcastChannel fallback contains only random coordination metadata. */ }
  }
  function send(type, value = record) { try { channel?.postMessage({ type, record: value }) } catch { /* A storage-backed lease still fences each request. */ } }
  function lose() {
    if (!active) return
    active = false
    environment.clearInterval(interval)
    for (const controller of pending) controller.abort()
    onLost()
  }
  function isOwner() {
    const current = read()
    const owned = !closed && active && current?.owner === id && current.expiresAt > now()
    if (active && !owned) lose()
    return owned
  }
  function receive(event) {
    const { type, record: incoming } = event.data || {}
    if (type === 'probe') { if (isOwner()) send('claim'); return }
    if (!incoming || typeof incoming.owner !== 'string' || !Number.isFinite(incoming.expiresAt) || !Number.isFinite(incoming.claimedAt)) return
    if (type === 'claim' && (!record || incoming.claimedAt > record.claimedAt || (incoming.claimedAt === record.claimedAt && incoming.owner > record.owner))) record = incoming
    if (type === 'heartbeat' && record?.owner === incoming.owner) record = incoming
    if (active && read()?.owner !== id) lose()
  }
  if (channel) channel.onmessage = receive
  const storageChange = event => { if (event.key === QUICK_CLIENT_KEY) { record = read(); if (active) isOwner() } }
  const release = () => {
    active = false
    environment.clearInterval(interval)
    for (const controller of pending) controller.abort()
    if (read()?.owner === id) write(null)
  }
  environment.addEventListener('storage', storageChange)
  environment.addEventListener('pagehide', release)
  async function claim({ takeover = false } = {}) {
    if (closed) return false
    if (isOwner()) return true
    send('probe')
    await wait(150)
    const acquire = () => {
      if (closed) return false
      const current = read()
      if (!takeover && current?.expiresAt > now() && current.owner !== id) return false
      write({ owner: id, expiresAt: now() + leaseMs, claimedAt: Math.max(now(), (current?.claimedAt || 0) + 1) })
      active = true
      send('claim')
      return true
    }
    // Serialize near-simultaneous claims where Web Locks are available. Storage
    // and BroadcastChannel alone provide a best-effort fallback, not a guarantee.
    let acquired
    if (environment.navigator?.locks) acquired = await environment.navigator.locks.request(QUICK_CLIENT_KEY, acquire)
    else acquired = acquire()
    if (!acquired) return false
    await wait(100)
    if (!isOwner()) return false
    environment.clearInterval(interval)
    interval = environment.setInterval(() => {
      if (!isOwner()) return
      write({ ...read(), expiresAt: now() + leaseMs })
      send('heartbeat')
    }, 3000)
    return true
  }
  async function request(api, path, options = {}) {
    if (!isOwner()) throw Object.assign(new Error('This examination is already open in another tab.'), { code: 'quick_client_inactive' })
    const controller = new environment.AbortController()
    pending.add(controller)
    try {
      const response = await api(path, { ...options, signal: controller.signal })
      if (!isOwner()) throw Object.assign(new Error('This examination is already open in another tab.'), { code: 'quick_client_inactive' })
      return response
    } finally { pending.delete(controller) }
  }
  return {
    claim, isOwner, release, request,
    dispose() { release(); closed = true; channel?.close(); environment.removeEventListener('storage', storageChange); environment.removeEventListener('pagehide', release) },
  }
}
