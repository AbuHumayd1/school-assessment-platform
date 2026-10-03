import test from 'node:test'
import assert from 'node:assert/strict'
import { signInDestination } from '../src/utils/signInDestination.js'
import { candidateAccess, endSession } from '../src/services/session.js'

const user = { id: 1, is_candidate: true }
const staff = [{ institution: { id: 1 }, role: 'institution_admin' }]

test('staff-only, candidate-only, mixed and no-context accounts choose honestly', () => {
  assert.equal(signInDestination(user, staff, null, false), '/app')
  assert.equal(signInDestination(user, [], null, true), '/student')
  assert.equal(signInDestination(user, staff, null, true), null)
  assert.equal(signInDestination(user, [], null, false), null)
})

test('mixed accounts preserve permitted application return routes', () => {
  assert.equal(signInDestination(user, staff, { pathname: '/app/questions', search: '?subject=1', hash: '#bank' }, true), '/app/questions?subject=1#bank')
  assert.equal(signInDestination(user, staff, { pathname: '/student/exam/42', search: '?resume=1' }, true), '/student/exam/42?resume=1')
})

test('return destinations cannot cross account contexts', () => {
  assert.equal(signInDestination(user, [], { pathname: '/app' }, true), '/student')
  assert.equal(signInDestination(user, staff, { pathname: '/student' }, false), '/app')
  assert.equal(signInDestination(user, [], { pathname: '/student' }, false), null)
})

test('external, malformed, encoded and unknown return paths are ignored', () => {
  for (const pathname of ['https://evil.test', '//evil.test', '/app/../../outside', '/app\\evil', '/app/%2e%2e/outside', '/app/%2f%2fevil.test', '/app?next=x', '/application', '/student/unknown']) {
    assert.equal(signInDestination(user, staff, { pathname }, true), null, pathname)
  }
  assert.equal(signInDestination(user, staff, { pathname: '/app', search: '//evil.test', hash: 'https://evil.test' }, true), '/app')
})

test('staff returns respect selected workspace role and pending selection', () => {
  const teacher = [{ institution: { id: 2 }, role: 'teacher' }]
  assert.equal(signInDestination(user, teacher, { pathname: '/app/staff' }, true), null)
  assert.equal(signInDestination(user, teacher, { pathname: '/app/questions' }, true), '/app/questions')
  assert.equal(signInDestination(user, [...staff, ...teacher], { pathname: '/app/staff' }, true, 'teacher'), null)
  assert.equal(signInDestination(user, [...staff, ...teacher], { pathname: '/app/staff' }, true), null)
})

test('candidate access is verified through the existing candidate context', async () => {
  let calls = 0
  const request = async path => { calls++; assert.equal(path, 'candidate/me/'); return { candidate: { id: 3 }, institution: { id: 4 } } }
  assert.equal(await candidateAccess(request, { is_candidate: false }), false)
  assert.equal(calls, 0)
  assert.equal(await candidateAccess(request, user), true)
  assert.equal(await candidateAccess(async () => ({}), user), false)
  for (const status of [403, 404, 409]) {
    assert.equal(await candidateAccess(async () => { throw { status } }, user), false)
  }
  await assert.rejects(candidateAccess(async () => { throw new Error('offline') }, user), /offline/)
})

test('logout posts to server before clearing frontend state', async () => {
  const events = []
  await endSession(async (path, options) => {
    assert.equal(path, 'auth/logout/')
    assert.equal(options.method, 'POST')
    events.push('server')
  }, () => events.push('clear'))
  assert.deepEqual(events, ['server', 'clear'])
})

test('failed logout retains authenticated state and can be retried', async () => {
  let cleared = false
  for (const status of [403, 500, undefined]) {
    await assert.rejects(endSession(async () => { throw { status } }, () => { cleared = true }))
    assert.equal(cleared, false)
  }
  await endSession(async () => {}, () => { cleared = true })
  assert.equal(cleared, true)
})

test('an already expired server session clears frontend authentication', async () => {
  let cleared = false
  await endSession(async () => { throw { status: 401 } }, () => { cleared = true })
  assert.equal(cleared, true)
  cleared = false
  await endSession(async path => { throw { status: path === 'auth/me/' ? 401 : 403 } }, () => { cleared = true })
  assert.equal(cleared, true)
})

test('a CSRF rejection with an active session never clears authentication', async () => {
  let cleared = false
  await assert.rejects(endSession(async path => {
    if (path === 'auth/logout/') throw { status: 403 }
    assert.equal(path, 'auth/me/')
    return { id: 1 }
  }, () => { cleared = true }))
  assert.equal(cleared, false)
})
