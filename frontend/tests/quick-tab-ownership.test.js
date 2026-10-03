import test from 'node:test'
import assert from 'node:assert/strict'
import { createQuickTabOwner, QUICK_CLIENT_KEY } from '../src/utils/quickTabOwnership.js'

function browser({ storage = true, broadcast = true, locks = true } = {}) {
  const values = new Map(), tabs = [], channels = new Set(), writes = [], messages = []
  let time = 1000, sequence = 0, queue = Promise.resolve()
  function tab() {
    const listeners = new Map(), intervals = new Set()
    const env = {
      crypto: { randomUUID: () => `random-tab-${++sequence}` }, Date: { now: () => time }, AbortController,
      setTimeout: callback => setTimeout(callback, 0), clearTimeout,
      setInterval: callback => { intervals.add(callback); return callback }, clearInterval: callback => intervals.delete(callback),
      addEventListener: (name, fn) => { if (!listeners.has(name)) listeners.set(name, new Set()); listeners.get(name).add(fn) },
      removeEventListener: (name, fn) => listeners.get(name)?.delete(fn),
      emit: (name, event) => { for (const fn of listeners.get(name) || []) fn(event) },
      tick: () => { for (const fn of [...intervals]) fn() },
      localStorage: {
        getItem: key => { if (!storage) throw new Error('Unavailable'); return values.get(key) || null },
        setItem: (key, value) => { if (!storage) throw new Error('Unavailable'); writes.push([key, value]); values.set(key, value); for (const other of tabs) if (other !== env) queueMicrotask(() => other.emit('storage', { key })) },
        removeItem: key => { if (!storage) throw new Error('Unavailable'); values.delete(key); for (const other of tabs) if (other !== env) queueMicrotask(() => other.emit('storage', { key })) },
      },
      BroadcastChannel: class {
        constructor(name) { if (!broadcast) throw new Error('Unavailable'); this.name = name; channels.add(this) }
        postMessage(message) { messages.push(message); for (const other of channels) if (other !== this && other.name === this.name) queueMicrotask(() => other.onmessage?.({ data: structuredClone(message) })) }
        close() { channels.delete(this) }
      },
      navigator: locks ? { locks: { request: (_name, fn) => { const next = queue.then(fn); queue = next.catch(() => {}); return next } } } : {},
    }
    tabs.push(env); return env
  }
  return { tab, writes, messages, values, advance: ms => { time += ms } }
}

for (const options of [{}, { locks: false }, { broadcast: false }, { storage: false, locks: false }]) {
  test(`second tab detection and explicit takeover fence old operations: ${JSON.stringify(options)}`, async () => {
    const platform = browser(options); let lost = 0
    const old = createQuickTabOwner(platform.tab(), () => lost++), next = createQuickTabOwner(platform.tab())
    try {
      assert.equal(await old.claim(), true); assert.equal(await next.claim(), false)
      assert.equal(old.isOwner(), true); assert.equal(await next.claim({ takeover: true }), true)
      assert.equal(old.isOwner(), false); assert.equal(lost, 1)
      let calls = 0
      for (const suffix of ['questions/', 'questions/7/answer/', 'questions/7/review/', 'integrity/', 'submit/']) await assert.rejects(old.request(async () => { calls++ }, `quick-exam/attempt/31/${suffix}`), error => error.code === 'quick_client_inactive')
      assert.equal(calls, 0)
      assert.equal(await next.request(async () => 'same-attempt', 'quick-exam/attempt/31/'), 'same-attempt')
    } finally { old.dispose(); next.dispose() }
  })
}
for (const locks of [true, false]) {
  test(`near-simultaneous claims admit one local runner (Web Locks: ${locks})`, async () => {
    const platform = browser({ locks }), a = createQuickTabOwner(platform.tab()), b = createQuickTabOwner(platform.tab())
    try { assert.deepEqual((await Promise.all([a.claim(), b.claim()])).sort(), [false, true]); assert.notEqual(a.isOwner(), b.isOwner()) } finally { a.dispose(); b.dispose() }
  })
}
test('takeover aborts in-flight requests and rejects stale responses without submitting or integrity events', async () => {
  const platform = browser(), old = createQuickTabOwner(platform.tab()), next = createQuickTabOwner(platform.tab())
  try {
    await old.claim(); let signal, resolve
    const response = old.request((_path, options) => { signal = options.signal; return new Promise(done => { resolve = done }) }, 'quick-exam/attempt/31/questions/')
    const rejected = assert.rejects(response, error => error.code === 'quick_client_inactive')
    await next.claim({ takeover: true }); assert.equal(signal.aborted, true)
    resolve({ outdated: true }); await rejected
    assert.ok(platform.messages.every(message => ['probe', 'claim', 'heartbeat'].includes(message.type)))
  } finally { old.dispose(); next.dispose() }
})
test('refresh/pagehide releases ownership and permits recovery without creating another attempt', async () => {
  const platform = browser(), env = platform.tab(), old = createQuickTabOwner(env)
  await old.claim(); env.emit('pagehide', {}); old.dispose()
  const refreshed = createQuickTabOwner(env)
  try { assert.equal(await refreshed.claim(), true); assert.equal(refreshed.isOwner(), true) } finally { refreshed.dispose() }
})
test('crashed or suspended clients expire and allow recovery without changing server timing', async () => {
  const platform = browser(); let lost = 0
  const old = createQuickTabOwner(platform.tab(), () => lost++), recovered = createQuickTabOwner(platform.tab())
  try { await old.claim(); platform.advance(16000); assert.equal(old.isOwner(), false); assert.equal(lost, 1); assert.equal(await recovered.claim(), true) } finally { old.dispose(); recovered.dispose() }
})
test('heartbeats renew only the owning lease and cannot reclaim it after takeover', async () => {
  const platform = browser(), firstTab = platform.tab(), secondTab = platform.tab(), first = createQuickTabOwner(firstTab), second = createQuickTabOwner(secondTab)
  try { await first.claim(); platform.advance(10000); firstTab.tick(); platform.advance(10000); assert.equal(first.isOwner(), true); await second.claim({ takeover: true }); firstTab.tick(); assert.equal(first.isOwner(), false); assert.equal(second.isOwner(), true) } finally { first.dispose(); second.dispose() }
})
test('network failure keeps ownership and allows retry without automatic logout or submission', async () => {
  const platform = browser(), owner = createQuickTabOwner(platform.tab())
  try { await owner.claim(); await assert.rejects(owner.request(async () => { throw new Error('network') }, 'quick-exam/attempt/31/'), /network/); assert.equal(owner.isOwner(), true); assert.equal(await owner.request(async () => 31, 'quick-exam/attempt/31/'), 31) } finally { owner.dispose() }
})
test('coordination contains only random client ID and lease timestamps, never credentials or tokens', async () => {
  const platform = browser(), owner = createQuickTabOwner(platform.tab())
  try {
    await owner.claim()
    for (const [key, value] of platform.writes) { assert.equal(key, QUICK_CLIENT_KEY); assert.deepEqual(Object.keys(JSON.parse(value)).sort(), ['claimedAt', 'expiresAt', 'owner']); assert.match(JSON.parse(value).owner, /^random-tab-/) }
    assert.doesNotMatch(JSON.stringify([...platform.writes, ...platform.messages]), /exam_code|candidate_id|pin|token|credential|attempt_id/i)
  } finally { owner.dispose() }
})
test('unavailable coordination APIs degrade without breaking recovery and disposal prevents late claims', async () => {
  const platform = browser({ storage: false, broadcast: false, locks: false }), owner = createQuickTabOwner(platform.tab())
  assert.equal(await owner.claim(), true); owner.dispose(); assert.equal(await owner.claim(), false)
  await assert.rejects(owner.request(async () => 'not reached', 'quick-exam/attempt/31/'), error => error.code === 'quick_client_inactive')
})
