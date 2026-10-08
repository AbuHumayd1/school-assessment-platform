import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import { canAccessWorkspaceCapability, canPrepareWorkspace } from '../src/utils/staffCapabilities.js'
import { signInDestination } from '../src/utils/signInDestination.js'

const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
const ui = await server.ssrLoadModule('/src/pages/platform/PlatformPages.jsx')
const { platformCopy } = await server.ssrLoadModule('/src/pages/platform/platform-copy.js')
const outcomes = await server.ssrLoadModule('/src/pages/staff/ExamOutcomes.jsx')
const { ExamSections } = await server.ssrLoadModule('/src/pages/staff/ExamDetailPage.jsx')
await server.close()
const render = (component, props) => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(component, props)))
const t = text => text
const client = { id: 7, name: 'Real Client', workspace_mode: 'managed_exam', is_active: true, can_release_candidate_results: false }

test('platform navigation includes the separate content libraries', () => {
  assert.deepEqual(ui.platformNavigation.map(([, label]) => label), ['Overview', 'Clients', 'Exams', 'Reports', 'Platform Library', 'Institution Banks'])
  const html = render(ui.PlatformNavigation, { t })
  for (const path of ['/platform', '/platform/clients', '/platform/exams', '/platform/reports']) assert.ok(html.includes(`href="${path}"`))
  assert.doesNotMatch(html, /Billing|Analytics|Subscriptions/)
})

test('platform overview summary displays real small values with semantic labels', () => {
  const html = render(ui.CompactSummary, { t, data: { clients: 3, candidates: 53 }, fields: [['clients', 'Clients'], ['candidates', 'Candidates']] })
  assert.match(html, /<dt>Clients<\/dt><dd>3<\/dd>/)
  assert.match(html, /<dt>Candidates<\/dt><dd>53<\/dd>/)
  const unavailable = render(ui.CompactSummary, { t, data: {}, fields: [['submissions', 'Submissions']] })
  assert.match(unavailable, /<dd>—<\/dd>/)
  assert.doesNotMatch(unavailable, /<dd>0<\/dd>/)
})

test('client directory presents friendly modes, status and detail link', () => {
  const html = render(ui.ClientTable, { rows: [client, { ...client, id: 8, name: 'Full Client', workspace_mode: 'full_workspace' }], t })
  for (const text of ['Real Client', 'Managed Exam', 'Full Workspace', 'Active', '/platform/clients/7']) assert.ok(html.includes(text))
  assert.doesNotMatch(html, /managed_exam|full_workspace|tenant|entitlement/)
})

test('empty search results remain readable and reports keep client links', () => {
  assert.match(render(ui.ClientTable, { rows: [], t }), /No clients found/)
  assert.match(render(ui.ClientTable, { rows: [client], reports: true, t }), /Open client reports/)
})

test('administrator provisioning uses own credentials and never requests platform credentials', () => {
  const html = render(ui.AdministratorForm, { t, onSubmit() {}, busy: false })
  for (const label of ['Name', 'Email', 'Initial Password', 'Add Administrator']) assert.ok(html.includes(label))
  assert.match(html, /type="password"/)
  assert.match(html, /autoComplete="new-password"/)
  assert.match(html, /Existing accounts keep their password/)
  assert.doesNotMatch(html, /Platform Password|Create account|Invitation/)
})

test('release permission is one accessible persisted-setting control', () => {
  const off = render(ui.ReleasePermission, { client, t, onChange() {} })
  const on = render(ui.ReleasePermission, { client: { ...client, can_release_candidate_results: true }, t, onChange() {} })
  assert.match(off, /type="checkbox"/)
  assert.match(off, /Allow client administrators to release results to candidates/)
  assert.doesNotMatch(off, /checked=""/)
  assert.match(on, /checked=""/)
  assert.match(on, / · On/)
})

test('managed navigation allows all six operational boards for client and platform administrators', () => {
  for (const role of ['institution_admin', 'platform_admin']) {
    for (const capability of ['dashboard', 'assessments', 'candidates', 'submissions', 'results', 'reports']) assert.equal(canAccessWorkspaceCapability(role, capability, 'managed_exam'), true)
    for (const capability of ['memberships', 'groups', 'subjects', 'questions', 'institution_settings']) assert.equal(canAccessWorkspaceCapability(role, capability, 'managed_exam'), false)
  }
})

test('full workspace keeps existing broader navigation', () => {
  for (const capability of ['dashboard', 'memberships', 'groups', 'subjects', 'questions', 'assessments', 'reports', 'institution_settings']) assert.equal(canAccessWorkspaceCapability('institution_admin', capability, 'full_workspace'), true)
})

test('managed preparation remains platform-only without fabricating a role', () => {
  assert.equal(canPrepareWorkspace('institution_admin', 'managed_exam'), false)
  assert.equal(canPrepareWorkspace('platform_admin', 'managed_exam'), true)
  assert.equal(canPrepareWorkspace('institution_admin', 'full_workspace'), true)
})

test('managed client exam navigation keeps reports and excludes preparation', () => {
  const html = render(ExamSections, { section: 'results', administrator: false, preparation: false, t })
  for (const label of ['Overview', 'Candidates', 'Submissions', 'Results', 'Reports']) assert.ok(html.includes(label))
  assert.doesNotMatch(html, />Questions<|>Access</)
})

test('release action disappears while score and publication status remain', () => {
  const summary = { release_state: 'not_released', results_count: 3, released_count: 0, release_pending_count: 3 }
  const off = render(outcomes.ResultsPublication, { summary, t, administrator: false, allowed: true })
  assert.doesNotMatch(off, /Release Results|Contact your platform|permission|disabled/)
  assert.match(off, /Not released/)
  const on = render(outcomes.ResultsPublication, { summary, t, administrator: true, allowed: true })
  assert.match(on, /Release Results/)
})

test('report downloads remain available with no published results', () => {
  const html = render(outcomes.ReportButtons, { t, available: true, busy: false, onDownload() {} })
  for (const format of ['CSV', 'PDF', 'Word']) assert.ok(html.includes(format))
  assert.doesNotMatch(html, /disabled/)
})

test('platform login works even before first client, while candidate routing is preserved', () => {
  assert.equal(signInDestination({ id: 1 }, [], null, false, null, true), '/platform')
  assert.equal(signInDestination({ id: 1 }, [], { pathname: '/platform/clients' }, false, null, true), '/platform/clients')
  assert.equal(signInDestination({ id: 1 }, [], null, true), '/student')
  assert.equal(signInDestination({ id: 1 }, [], null, true, null, true), null)
  assert.equal(signInDestination({ id: 1 }, [], { pathname: '/student' }, true, null, true), '/student')
  assert.equal(signInDestination({ id: 1 }, [{ role: 'institution_admin' }], null, false), '/app')
  assert.equal(signInDestination({ id: 1 }, [{ role: 'institution_admin' }], null, true), null)
  assert.equal(signInDestination({ id: 1 }, [], { pathname: '//evil.test' }, false, null, true), '/platform')
})

test('English bilingual and Arabic labels preserve useful client data', () => {
  for (const text of ['Overview', 'Clients', 'Exams', 'Reports', 'Create Client', 'Manage Client', 'Return to Platform', 'Add Administrator', 'Initial Password', 'Allow client administrators to release results to candidates']) assert.ok(platformCopy[text])
  const arabic = text => platformCopy[text] || text
  const html = render(ui.ClientTable, { rows: [client], t: arabic })
  assert.ok(html.includes(platformCopy.Client))
  assert.ok(html.includes(platformCopy['Managed Exam']))
  assert.match(html, /<bdi>Real Client<\/bdi>/)
  const bilingual = text => `${text} · ${platformCopy[text] || text}`
  assert.ok(render(ui.PlatformNavigation, { t: bilingual }).includes(`Clients · ${platformCopy.Clients}`))
})

test('Return to Platform clears selected institution, and Manage uses server-authorized refresh', async () => {
  const layout = await readFile(new URL('../src/layouts/StaffLayout.jsx', import.meta.url), 'utf8')
  const pages = await readFile(new URL('../src/pages/platform/PlatformPages.jsx', import.meta.url), 'utf8')
  const workspace = await readFile(new URL('../src/context/WorkspaceContext.jsx', import.meta.url), 'utf8')
  assert.match(layout, /to="\/platform" onClick={clearSelection}/)
  assert.match(pages, /await refreshAndSelect\(Number\(clientId\)\)/)
  assert.match(workspace, /setInstitutionContext\(null\)/)
  assert.match(workspace, /initialWorkspace\(available, response\.is_platform_admin === true, storedSelection\)/)
  assert.match(pages, /workspace\.isPlatformAdmin \? children/)
})

test('new layouts wrap at tablet/mobile widths and use logical RTL spacing', async () => {
  const css = await readFile(new URL('../src/pages/platform/platform.css', import.meta.url), 'utf8')
  assert.match(css, /flex-wrap: wrap/)
  assert.match(css, /@media \(max-width: 650px\)/)
  assert.match(css, /grid-template-columns: minmax\(0, 1fr\)/)
  assert.match(css, /padding-inline/)
  assert.match(css, /margin-inline-start/)
  assert.doesNotMatch(css, /min-width: 390px|font-size: [3-9]rem/)
})

test('release UI uses fresh summary authorization independently from preparation', async () => {
  const source = await readFile(new URL('../src/pages/staff/ExamOutcomes.jsx', import.meta.url), 'utf8')
  assert.match(source, /data\?\.summary\.can_release_results === true/)
  assert.match(source, /settingsAdministrator={administrator}/)
  assert.match(source, /administrator={allowed}/)
})

test('Manage refresh keeps the authorized console mounted without trusting a different account', () => {
  const workspace = { isPlatformAdmin: true, resolvedUserId: 1, loading: true }
  assert.equal(ui.platformAccessState({ id: 1 }, false, workspace), 'ready')
  assert.equal(ui.platformAccessState({ id: 2 }, false, workspace), 'loading')
  assert.equal(ui.platformAccessState({ id: 1 }, false, { ...workspace, resolvedUserId: null }), 'loading')
  assert.equal(ui.platformAccessState({ id: 1 }, false, { isPlatformAdmin: false, loading: false }), 'denied')
  assert.equal(ui.platformAccessState(null, false, workspace), 'signin')
  assert.equal(ui.platformAccessState({ id: 1 }, false, { ...workspace, loading: false, error: new Error('Failed') }), 'error')
})
