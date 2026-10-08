import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import { createRouteScrollManager } from '../src/utils/routeScroll.js'

function fixture() {
  const listeners = new Map(), frames = new Map()
  let observer, target, sequence = 0
  const calls = []
  const env = {
    scrollY: 500,
    document: { documentElement: { style: { scrollBehavior: 'smooth' } }, body: {}, getElementById: () => target, getElementsByName: () => [], querySelector: () => ({ getBoundingClientRect: () => ({ bottom: 60 }) }) },
    addEventListener: (name, callback) => listeners.set(name, callback), removeEventListener: name => listeners.delete(name),
    scrollTo: options => { calls.push(options.top); env.scrollY = options.top },
    requestAnimationFrame: callback => { frames.set(++sequence, callback); return sequence }, cancelAnimationFrame: id => frames.delete(id),
    setTimeout: () => 1, clearTimeout() {},
    MutationObserver: class { constructor(callback) { observer = callback } observe() {} disconnect() {} },
  }
  return { env, calls, listeners, setTarget: () => { target = { getBoundingClientRect: () => ({ top: 300 }) } }, render: () => { for (const callback of [...frames.values()]) callback(); frames.clear() }, mutate: () => observer() }
}
const route = (key, pathname = '/', search = '', hash = '') => ({ key, pathname, search, hash })

test('initial load, normal routes and query navigation start at top; rerenders do not reset', () => {
  const f = fixture(), manager = createRouteScrollManager(f.env)
  manager.navigate(route('a'), 'POP')
  assert.deepEqual(f.calls, [0])
  f.env.scrollY = 300
  manager.navigate(route('a'), 'POP')
  assert.deepEqual(f.calls, [0])
  manager.navigate(route('b', '/pricing'), 'PUSH')
  f.env.scrollY = 200
  manager.navigate(route('c', '/pricing', '?plan=pilot'), 'REPLACE')
  assert.deepEqual(f.calls, [0, 0, 0])
  assert.deepEqual([...f.listeners.keys()], ['scroll'])
  manager.dispose()
  assert.equal(f.listeners.size, 0)
})
test('Back/Forward restores saved positions without forcing hash targets', () => {
  const f = fixture(), manager = createRouteScrollManager(f.env)
  manager.navigate(route('a'), 'POP'); f.env.scrollY = 420
  manager.navigate(route('b', '/contact'), 'PUSH'); f.env.scrollY = 120
  manager.navigate(route('a'), 'POP'); assert.equal(f.calls.at(-1), 420)
  manager.navigate(route('b', '/contact'), 'POP'); assert.equal(f.calls.at(-1), 120)
  manager.dispose()
})
test('hash navigation waits for target and respects header; stale target work is cancelled', () => {
  const f = fixture(), manager = createRouteScrollManager(f.env)
  manager.navigate(route('a', '/', '', '#managed-examinations'), 'PUSH')
  f.render(); assert.equal(f.calls.length, 0)
  f.setTarget(); f.mutate(); assert.equal(f.calls.at(-1), 740)
  manager.navigate(route('b', '/', '', '#institution-workspace'), 'PUSH')
  manager.navigate(route('c', '/contact'), 'PUSH'); f.mutate(); f.render()
  assert.equal(f.calls.at(-1), 0)
  manager.dispose()
})
test('native refresh restoration is disabled before React; no focus or visibility listeners', async () => {
  const source = await readFile(new URL('../public/scroll-init.js', import.meta.url), 'utf8')
  const window = { history: { scrollRestoration: 'auto' } }
  vm.runInNewContext(source, { window })
  assert.equal(window.history.scrollRestoration, 'manual')
  const index = await readFile(new URL('../index.html', import.meta.url), 'utf8')
  assert.ok(index.indexOf('/scroll-init.js') < index.indexOf('/src/main.jsx'))
  const f = fixture(), manager = createRouteScrollManager(f.env)
  assert.deepEqual([...f.listeners.keys()], ['scroll'])
  manager.dispose()
})
