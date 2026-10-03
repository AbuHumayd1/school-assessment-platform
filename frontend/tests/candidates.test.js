import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { candidateFields, candidateDeletionError, deleteCandidate, deletionHistoryMessage, getCandidate, listCandidates, portalAccessState, provisionCandidate, saveCandidate } from '../src/services/candidates.js'
import { candidateCopy } from '../src/pages/staff/candidate-copy.js'

const record = { id: 1, institution: 7, candidate_id: 'C-001', first_name: 'Amina', last_name: 'Learner', email: '', phone: '', date_of_birth: null, status: 'active', portal_account: null }
const values = { ...record, date_of_birth: '' }

test('deletion uses DELETE with selected workspace and requires no-content confirmation', async () => {
  let rows = [record]
  await deleteCandidate(async (path, options) => {
    assert.equal(path, 'candidates/1/?institution=7')
    assert.deepEqual(options, { method: 'DELETE' })
    rows = []
    return null
  }, 7, 1)
  assert.deepEqual((await listCandidates(async () => ({ count: 0, results: rows, next: null }), 7)).results, [])
  await assert.rejects(deleteCandidate(async () => ({}), 7, 1), /could not be confirmed/)
})

test('protected history and failed deletion preserve records and provide safe guidance', async () => {
  const rows = [record]
  const conflict = Object.assign(new Error('Conflict'), { status: 409, data: { code: 'candidate_has_assessment_history' } })
  await assert.rejects(deleteCandidate(async () => { throw conflict }, 7, 1), error => error === conflict)
  assert.deepEqual(rows, [record])
  assert.equal(candidateDeletionError(conflict), deletionHistoryMessage)
  assert.match(candidateDeletionError(conflict), /Deactivate the candidate instead/)
  assert.equal(candidateDeletionError({ status: 500, data: { detail: 'Raw database error' } }), 'We could not complete this request. Please try again.')
})

test('delete control is admin-only and confirmation identifies candidate with localized copy', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  try {
    const { CandidateDeleteAction, CandidateDeleteConfirmation } = await server.ssrLoadModule('/src/pages/staff/CandidatesPage.jsx')
    const t = value => value
    assert.match(renderToStaticMarkup(React.createElement(CandidateDeleteAction, { administrator: true, t })), /Delete candidate/)
    assert.equal(renderToStaticMarkup(React.createElement(CandidateDeleteAction, { administrator: false, t })), '')
    const props = { candidate: { ...record, portal_account: { email: 'learner@example.com' } }, t }
    const confirmation = renderToStaticMarkup(React.createElement(CandidateDeleteConfirmation, props))
    assert.match(confirmation, /Amina Learner/)
    assert.match(confirmation, /C-001/)
    assert.match(confirmation, /cannot be undone/)
    assert.match(confirmation, /linked user account will remain/)
    const arabic = renderToStaticMarkup(React.createElement(CandidateDeleteConfirmation, { ...props, t: value => candidateCopy[value] || value }))
    assert.match(arabic, /حذف المرشح/)
    assert.match(arabic, /لا يمكن التراجع/)
    const bilingual = renderToStaticMarkup(React.createElement(CandidateDeleteConfirmation, { ...props, t: value => `${value} · ${candidateCopy[value] || value}` }))
    assert.match(bilingual, /Delete candidate · حذف المرشح/)
    const blocked = renderToStaticMarkup(React.createElement(CandidateDeleteConfirmation, { ...props, error: deletionHistoryMessage }))
    assert.match(blocked, /role="alert"/)
    assert.match(blocked, /Deactivate/)
  } finally { await server.close() }
})

test('confirmation cancel is separate from deletion and pending controls prevent duplicate clicks', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  try {
    const { CandidateDeleteConfirmation } = await server.ssrLoadModule('/src/pages/staff/CandidatesPage.jsx')
    let cancelled = 0
    let deleted = 0
    const props = { candidate: record, t: value => value, onCancel: () => { cancelled++ }, onConfirm: () => { deleted++ } }
    const tree = CandidateDeleteConfirmation(props)
    const actions = tree.props.children.at(-1).props.children
    actions[0].props.onClick()
    assert.equal(cancelled, 1)
    assert.equal(deleted, 0)
    actions[1].props.onClick()
    assert.equal(deleted, 1)
    const pending = renderToStaticMarkup(React.createElement(CandidateDeleteConfirmation, { ...props, busy: true }))
    assert.equal((pending.match(/disabled=""/g) || []).length, 2)
    assert.match(pending, /aria-busy="true"/)
    assert.match(pending, /Deleting/)
  } finally { await server.close() }
})

test('candidate creation uses real confirmation and permits empty email', async () => {
  const saved = await saveCandidate(async (path, options) => {
    assert.equal(path, 'candidates/')
    assert.equal(options.method, 'POST')
    assert.equal(options.body.institution, 7)
    assert.equal(options.body.email, '')
    assert.equal(options.body.date_of_birth, null)
    assert.equal(options.body.user, undefined)
    return record
  }, 7, null, values)
  assert.equal(saved, record)
  assert.equal(candidateFields({ ...values, candidate_id: ' C-001 ' }).candidate_id, 'C-001')
})

test('validation failure cannot fake candidate creation', async () => {
  let saved = null
  await assert.rejects(async () => { saved = await saveCandidate(async () => { throw Object.assign(new Error('Duplicate ID'), { status: 400 }) }, 7, null, values) })
  assert.equal(saved, null)
  await assert.rejects(saveCandidate(async () => ({}), 7, null, values))
})

test('list requests include search, status, page and selected workspace', async () => {
  const response = await listCandidates(async path => {
    const query = new URLSearchParams(path.split('?')[1])
    assert.equal(query.get('institution'), '7')
    assert.equal(query.get('search'), 'Amina Learner')
    assert.equal(query.get('status'), 'active')
    assert.equal(query.get('page'), '2')
    return { count: 1, results: [record], next: null }
  }, 7, { search: 'Amina Learner', status: 'active', page: 2 })
  assert.deepEqual(response.results, [record])
})

test('workspace switching rejects records from the old workspace', async () => {
  await assert.rejects(listCandidates(async () => ({ count: 1, results: [record] }), 8))
  await assert.rejects(getCandidate(async () => record, 8, 1))
  await assert.rejects(saveCandidate(async () => record, 8, 1, values))
  assert.equal(await getCandidate(async () => record, 7, 1), record)
})

test('teachers profile edits omit administrator-only identity and status fields', async () => {
  await saveCandidate(async (path, options) => {
    assert.equal(options.method, 'PATCH')
    assert.equal(options.body.candidate_id, undefined)
    assert.equal(options.body.status, undefined)
    assert.equal(options.body.first_name, 'Amina')
    return record
  }, 7, 1, values, { profileOnly: true })
})

test('account-access state distinguishes linkage, disabled accounts and inactive candidates', () => {
  assert.equal(portalAccessState(record), 'not_enabled')
  const linked = { ...record, portal_account: { email: 'amina@example.com', is_active: true } }
  assert.equal(portalAccessState(linked), 'enabled')
  assert.equal(portalAccessState({ ...linked, status: 'archived' }), 'candidate_inactive')
  assert.equal(portalAccessState({ ...linked, portal_account: { is_active: false } }), 'account_inactive')
})

test('provisioning returns credentials only after success and preserves collision/already-linked errors', async () => {
  const credentials = { account: { id: 2, email: 'amina@example.com' }, initial_password: 'one-time-test-credential' }
  assert.equal(await provisionCandidate(async (path, options) => {
    assert.match(path, /candidates\/1\/provision-access\/\?institution=7/)
    assert.deepEqual(options, { method: 'POST', body: {} })
    return credentials
  }, 7, 1), credentials)
  for (const code of ['email_exists', 'already_linked', 'email_required']) {
    let shown = null
    const failure = Object.assign(new Error('Provisioning rejected'), { status: 400, data: { code } })
    await assert.rejects(async () => { shown = await provisionCandidate(async () => { throw failure }, 7, 1) }, error => error === failure)
    assert.equal(shown, null)
  }
  await assert.rejects(provisionCandidate(async () => ({ account: {} }), 7, 1))
})

test('real roster renders empty/data states and credentials disappear when immediate success is dismissed', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  try {
    const { CandidateRoster, InitialCredentials } = await server.ssrLoadModule('/src/pages/staff/CandidatesPage.jsx')
    const t = value => value
    const empty = renderToStaticMarkup(React.createElement(CandidateRoster, { rows: [], t }))
    assert.match(empty, /No candidates yet/)
    assert.match(empty, /Add candidate/)
    const populated = renderToStaticMarkup(React.createElement(CandidateRoster, { rows: [record], t }))
    assert.match(populated, /Amina/)
    assert.match(populated, /C-001/)
    assert.match(populated, /Portal access not enabled/)
    assert.doesNotMatch(populated, /GPA|Examination History|Class assignment/)
    const credentials = { account: { email: 'amina@example.com' }, initial_password: 'immediate-only-test-password' }
    assert.match(renderToStaticMarkup(React.createElement(InitialCredentials, { credentials, t })), /immediate-only-test-password/)
    assert.equal(renderToStaticMarkup(React.createElement(InitialCredentials, { credentials: null, t })), '')
    const arabic = renderToStaticMarkup(React.createElement(CandidateRoster, { rows: [], t: value => candidateCopy[value] || value }))
    assert.match(arabic, /إضافة مرشح/)
    const bilingual = renderToStaticMarkup(React.createElement(CandidateRoster, { rows: [], t: value => `${value} · ${candidateCopy[value] || value}` }))
    assert.match(bilingual, /Add candidate · إضافة مرشح/)
  } finally { await server.close() }
})

test('workspace header is captured before awaiting CSRF rather than switched mid-request', async () => {
  const server = await createServer({ server: { middlewareMode: true }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  const originalFetch = globalThis.fetch
  try {
    const api = await server.ssrLoadModule('/src/services/api.js')
    let resolveCsrf
    const requests = []
    globalThis.fetch = async (url, options) => {
      requests.push({ url, options })
      if (url.endsWith('auth/csrf/')) return new Promise(resolve => { resolveCsrf = resolve })
      return new Response(JSON.stringify(record), { status: 201, headers: { 'Content-Type': 'application/json' } })
    }
    api.clearSessionContext()
    api.setInstitutionContext(7)
    const pending = api.staffApiFetch('candidates/', { method: 'POST', body: candidateFields(values) })
    api.setInstitutionContext(8)
    resolveCsrf(new Response(JSON.stringify({ csrfToken: 'test-csrf' }), { headers: { 'Content-Type': 'application/json' } }))
    await pending
    assert.equal(requests[1].options.headers.get('X-Institution-ID'), '7')
    assert.equal(requests[1].options.headers.get('X-CSRFToken'), 'test-csrf')
    assert.equal(requests[1].options.credentials, 'include')
    await api.staffApiFetch('candidates/')
    assert.equal(requests[2].options.headers.get('X-Institution-ID'), '8')
  } finally { globalThis.fetch = originalFetch; await server.close() }
})
