import test from 'node:test'
import assert from 'node:assert/strict'
import { registerAccount, createWorkspace, createdWorkspaceContext, onboardingDestination } from '../src/services/onboarding.js'
import { signInDestination } from '../src/utils/signInDestination.js'
import { onboardingAr } from '../src/context/onboardingTranslations.js'

const user = { id: 7, email: 'organizer@example.com' }
const oldWorkspace = { institution: { id: 1, name: 'Existing' }, role: 'teacher' }
const newWorkspace = { institution: { id: 9, name: 'New' }, role: 'institution_admin' }

test('registration only returns an account after a confirmed session response', async () => {
  const fields = { email: user.email, password: 'secret', password_confirmation: 'secret' }
  const request = async (path, options) => {
    assert.equal(path, 'auth/register/')
    assert.equal(options.method, 'POST')
    assert.deepEqual(options.body, fields)
    return { user, csrfToken: 'rotated' }
  }
  assert.deepEqual(await registerAccount(request, fields), user)
  for (const response of [null, {}, { user: { id: '7' } }, { user: { id: 7 } }]) {
    await assert.rejects(registerAccount(async () => response, fields))
  }
})

test('failed registration cannot run the successful account transition', async () => {
  let account = null
  await assert.rejects(async () => { account = await registerAccount(async () => { throw new Error('Invalid password') }, {}) })
  assert.equal(account, null)
})

test('creation requires backend confirmation and sends only the submitted setup data', async () => {
  const fields = { name: 'New', institution_type: 'training', timezone: 'Africa/Lagos' }
  assert.equal(await createWorkspace(async (path, options) => {
    assert.equal(path, 'institutions/create-workspace/')
    assert.deepEqual(options, { method: 'POST', body: fields })
    return { id: 9 }
  }, fields), 9)
  await assert.rejects(createWorkspace(async () => ({}), fields))
  await assert.rejects(createWorkspace(async () => { throw new Error('Server unavailable') }, fields))
})

test('authoritative context selects the newly created workspace among existing ones', async () => {
  const result = await createdWorkspaceContext(async path => {
    assert.equal(path, 'auth/context/')
    return { user, workspaces: [oldWorkspace, newWorkspace] }
  }, user.id, 9)
  assert.deepEqual(result.workspaces, [oldWorkspace, newWorkspace])
  assert.equal(result.selected, newWorkspace)
})

test('missing membership, wrong account or wrong role cannot fake workspace selection', async () => {
  let selected = null
  for (const response of [
    { user, workspaces: [oldWorkspace] },
    { user: { id: 8 }, workspaces: [newWorkspace] },
    { user, workspaces: [{ ...newWorkspace, role: 'student' }] },
    { user, workspaces: null },
  ]) {
    await assert.rejects(async () => { selected = (await createdWorkspaceContext(async () => response, user.id, 9)).selected })
    assert.equal(selected, null)
  }
  await assert.rejects(createdWorkspaceContext(async () => { throw new Error('Session expired') }, user.id, 9))
})

test('existing platform administrators retain their authoritative context role', async () => {
  const platformWorkspace = { ...newWorkspace, role: 'platform_admin' }
  const result = await createdWorkspaceContext(async () => ({ user, workspaces: [platformWorkspace] }), user.id, 9)
  assert.equal(result.selected.role, 'platform_admin')
})

test('context retry uses discovery only after creation is confirmed', async () => {
  let creations = 0
  const id = await createWorkspace(async () => { creations++; return { id: 9 } }, {})
  await assert.rejects(createdWorkspaceContext(async () => { throw new Error('Temporary connection failure') }, user.id, id))
  assert.equal((await createdWorkspaceContext(async () => ({ user, workspaces: [newWorkspace] }), user.id, id)).selected.institution.id, 9)
  assert.equal(creations, 1)
})

test('no-context setup and deliberate setup returns coexist with existing account routing', () => {
  assert.equal(onboardingDestination, '/setup')
  assert.equal(signInDestination(user, [], null, false), null)
  for (const [workspaces, candidate] of [[[], false], [[], true], [[oldWorkspace], false], [[oldWorkspace], true]]) {
    assert.equal(signInDestination(user, workspaces, { pathname: '/setup' }, candidate), '/setup')
  }
  assert.equal(signInDestination(user, [oldWorkspace], null, false), '/app')
  assert.equal(signInDestination(user, [], null, true), '/student')
  assert.equal(signInDestination(user, [oldWorkspace], null, true), null)
  for (const pathname of ['//evil.test/setup', '/setup/../app', '/setup%2f', '/setup?next=evil']) {
    assert.equal(signInDestination(user, [], { pathname }, false), null)
  }
})

test('onboarding Arabic copy covers key actions, generic categories and failure states', () => {
  for (const text of ['Create account', 'Create workspace', 'Get Started', 'School / College', 'Course / Training Provider', 'Professional / Certification Exams', 'Madrasah / Islamic Institute', 'CBT / Tutorial Centre', 'Competition / Educational Programme', 'This email is already registered. Sign in with your existing account.', 'Passwords must match.', 'Your session has expired. Sign in again to set up your workspace.']) {
    assert.match(onboardingAr[text], /[\u0600-\u06ff]/)
  }
})
