import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer as createViteServer } from 'vite'
// These tests render server-side only; skip the client dependency pre-bundle.
const createServer = options => createViteServer({ ...options, plugins: [...(options.plugins || []), {
  name: 'ssr-only-test-server',
  configResolved(config) { config.optimizeDeps.include = []; config.optimizeDeps.noDiscovery = true },
}] })
const serviceServer = await createServer({ configLoader: 'runner', server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
const { listExams, getExam, examRequest, examFields, credentialState, examError, createOwnerScope, pinDisclosureReducer, localDateValue } = await serviceServer.ssrLoadModule('/src/services/assessments.js')
await serviceServer.close()
import { canManageQuickAccess, examWorkflowActions } from '../src/utils/staffCapabilities.js'
import { examCopy } from '../src/pages/staff/exam-copy.js'

const exam = { id: 11, institution: 7, title: 'Client examination', status: 'draft', subject_name: 'Mathematics', group_name: 'Cohort', assessment_type: 'test', question_count: 1, duration_minutes: 30, total_marks: '2.00', pass_mark: '1.00', candidate_access: 'access_code', quick_access_configured: true, has_attempt_history: false, start_at: '2026-10-03T00:00:00Z', end_at: '2026-10-04T00:00:00Z', created_at: '2026-10-01T00:00:00Z', updated_at: '2026-10-01T00:00:00Z' }
const question = { id: 3, text: 'Inspection question', question_type: 'multiple_choice', explanation: 'Owner explanation', status: 'approved', difficulty: 'easy', options: [{ id: 1, text: 'First', is_correct: true }, { id: 2, text: 'Second', is_correct: false }] }
const t = text => text
const html = (component, props) => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(component, props)))

async function modules(run) {
  const server = await createServer({ configLoader: 'runner', server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  try { await run(path => server.ssrLoadModule(path)) } finally { await server.close() }
}

test('assessment requests pin selected workspace and validate returned ownership', async () => {
  const paths = []
  const request = async (path, options) => { paths.push([path, options]); return { count: 1, results: [exam] } }
  assert.equal((await listExams(7, { page: '2', search: 'Client' }, {}, request)).count, 1)
  assert.match(paths[0][0], /page=2.*search=Client.*institution=7/)
  await assert.rejects(listExams(8, {}, {}, request), /Workspace context/)
  await assert.rejects(getExam(7, 11, {}, async () => ({ ...exam, institution: 8 })), /Workspace context/)
  assert.equal((await getExam(7, 11, {}, async () => exam)).id, 11)
  assert.match(examError({ status: 409, data: { code: 'credential_exists' } }), /Use Reset PIN/)
  assert.doesNotMatch(examError({ status: 500, data: { detail: 'Private server detail' } }), /Private server detail/)
  await examRequest(7, '11/approve/', { method: 'POST', body: {} }, {}, async (path, options) => {
    assert.equal(path, 'assessments/11/approve/?institution=7')
    assert.deepEqual(options, { method: 'POST', body: {} })
  })
})

test('cancelled workspace scopes ignore late success and failure', async () => {
  let resolve, reject
  const results = []
  const old = createOwnerScope()
  const run = old.run(() => new Promise(done => { resolve = done }), data => results.push(data), error => results.push(error))
  old.cancel(); resolve('Client A'); await run
  assert.deepEqual(results, [])
  const failing = createOwnerScope()
  const failed = failing.run(() => new Promise((_, fail) => { reject = fail }), data => results.push(data), error => results.push(error))
  failing.cancel(); reject(new Error('Old client')); await failed
  const current = createOwnerScope()
  await current.run(async () => 'Client B', data => results.push(data), error => results.push(error))
  assert.deepEqual(results, ['Client B'])
})

test('PIN reducer holds only current disclosure and clears on dismissal/navigation/context disposal', () => {
  const disclosure = { initial_pin: 'TEST-ONE-TIME', credential: { candidate_name: 'Amina', candidate_identifier: 'C-1' } }
  const issued = pinDisclosureReducer(null, { type: 'issued', disclosure })
  assert.equal(issued, disclosure)
  for (const type of ['dismiss', 'navigation', 'workspace']) assert.equal(pinDisclosureReducer(issued, { type }), null)
})

test('credential status remains independent of exam availability', () => {
  const credential = { active: true, candidate_status: 'active', expires_at: null, revoked_at: null }
  assert.equal(credentialState(credential), 'Valid credential')
  assert.equal(credentialState({ ...credential, active: false }), 'Revoked')
  assert.equal(credentialState({ ...credential, expires_at: '2020-01-01T00:00:00Z' }), 'Expired')
  assert.equal(credentialState({ ...credential, candidate_status: 'inactive' }), 'Candidate inactive')
})

test('workflow visibility preserves roles, states, and attempt-history restrictions', () => {
  assert.deepEqual(examWorkflowActions('student', exam), [])
  for (const role of ['platform_admin', 'institution_admin', 'teacher', 'examiner']) assert.deepEqual(examWorkflowActions(role, exam), ['edit', 'submit-review'])
  assert.deepEqual(examWorkflowActions('teacher', { ...exam, status: 'review' }), [])
  assert.deepEqual(examWorkflowActions('examiner', { ...exam, status: 'review' }), ['request-changes'])
  assert.deepEqual(examWorkflowActions('institution_admin', { ...exam, status: 'review' }), ['request-changes', 'approve'])
  assert.deepEqual(examWorkflowActions('platform_admin', { ...exam, status: 'approved', has_attempt_history: true }), ['schedule', 'archive'])
  assert.deepEqual(examWorkflowActions('institution_admin', { ...exam, status: 'draft', has_attempt_history: true }), [])
  assert.deepEqual(examWorkflowActions('teacher', { ...exam, question_count: 0 }), ['edit'])
  assert.deepEqual(examWorkflowActions('institution_admin', { ...exam, status: 'approved', start_at: null }), ['reopen', 'archive'])
  assert.equal(canManageQuickAccess('teacher'), false)
  assert.equal(canManageQuickAccess('examiner'), false)
  assert.equal(canManageQuickAccess('platform_admin'), true)
  assert.equal(canManageQuickAccess('institution_admin'), true)
})

test('form fields exclude server-controlled state and serialize local dates with timezone offsets', () => {
  const values = { ...exam, subject: '4', group: '', duration_minutes: '30', attempt_limit: '1', start_at: '2026-10-03T10:00', end_at: '', title: 'Configured exam' }
  const data = examFields(values)
  assert.equal(data.subject, 4)
  assert.equal(data.group, null)
  assert.equal(data.end_at, null)
  assert.match(data.start_at, /Z$/)
  assert.equal(localDateValue(data.start_at), values.start_at)
  for (const field of ['status', 'institution', 'total_marks', 'created_by', 'questions']) assert.equal(field in data, false)
})

test('real exam list and loading/error/empty states render', async () => modules(async load => {
  const { ExamList } = await load('/src/pages/staff/ExamsPage.jsx')
  const { ReadState } = await load('/src/pages/staff/exam-ui.jsx')
  const listing = html(ExamList, { rows: [exam], t })
  assert.match(listing, /Client examination/)
  assert.match(listing, /app\/exams\/11/)
  assert.match(listing, /Mathematics/)
  assert.match(html(ExamList, { rows: [], t }), /No exams found/)
  assert.match(html(ReadState, { state: { loading: true }, t }), /role="status"/)
  const error = html(ReadState, { state: { error: new Error('Private internal failure'), retry() {} }, t })
  assert.match(error, /Retry/)
  assert.doesNotMatch(error, /Private internal/)
}))

test('Overview, staff correctness inspection and candidate roster use real fields', async () => modules(async load => {
  const { ExamOverview, QuestionInspection, EligibilityRoster } = await load('/src/pages/staff/ExamDetailPage.jsx')
  assert.match(html(ExamOverview, { exam, t }), /2.00/)
  const inspection = html(QuestionInspection, { rows: [{ id: 1, order: 1, marks: '2.00', question }], t })
  assert.match(inspection, /Correct answer/)
  assert.match(inspection, /Owner explanation/)
  const roster = html(EligibilityRoster, { data: { mode: 'access_code', workflow_status: 'draft', window: 'open', results: [{ id: 5, candidate_id: 'C-1', name: 'Amina Candidate', status: 'active' }] }, t })
  assert.match(roster, /Amina Candidate/)
  assert.match(roster, /managed separately in Access/)
  assert.doesNotMatch(roster, /Reset PIN/)
}))

test('section navigation is deep-linked and Quick Access is admin-only', async () => modules(async load => {
  const { ExamSections } = await load('/src/pages/staff/ExamDetailPage.jsx')
  const teacher = html(ExamSections, { section: 'questions', administrator: canManageQuickAccess('teacher'), t })
  assert.doesNotMatch(teacher, /section=access/)
  assert.match(teacher, /aria-current="page"/)
  assert.match(teacher, /section=questions/)
  const admin = html(ExamSections, { section: 'access', administrator: canManageQuickAccess('institution_admin'), t })
  assert.match(admin, /section=access/)
  assert.match(admin, /Submissions/); assert.match(admin, /Results/); assert.match(admin, /Reports/)
}))

test('one-time disclosure and reset/revoke confirmations identify the candidate', async () => modules(async load => {
  const { PinDisclosure, CredentialConfirmation } = await load('/src/pages/staff/ExamAccess.jsx')
  const credential = { candidate_name: 'Amina Candidate', candidate_identifier: 'C-1' }
  const pin = html(PinDisclosure, { disclosure: { initial_pin: 'TEST-ONE-TIME', credential }, t })
  assert.match(pin, /cannot be viewed again/)
  assert.match(pin, /Dismiss PIN/)
  assert.equal(html(PinDisclosure, { disclosure: null, t }), '')
  assert.match(html(CredentialConfirmation, { action: 'reset', credential, t }), /previous PIN and active sessions/)
  assert.match(html(CredentialConfirmation, { action: 'revoke', credential, t }), /prevents access/)
}))

test('preview renders pure presentation without answer key, submission or timer UI', async () => modules(async load => {
  const { default: Preview } = await load('/src/components/staff/ExamPreview.jsx')
  const markup = html(Preview, { t, paper: { title: 'Preview paper', randomize_questions: true, questions: [{ id: 3, prompt: question.text, type: question.question_type, options: question.options.map(row => ({ id: row.id, label: row.text })) }] } })
  assert.match(markup, /PREVIEW MODE/)
  assert.match(markup, /No attempt is created/)
  assert.match(markup, /may vary/)
  assert.match(markup, /Inspection question/)
  assert.doesNotMatch(markup, /Correct answer|Owner explanation|Submit|role="timer"/)
  const source = await readFile(new URL('../src/components/staff/ExamPreview.jsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /StudentExamPage|apiFetch|examRequest|setInterval|integrity|startAttempt/)
}))

test('create/edit configuration supports real safe choices and does not expose editable status', async () => modules(async load => {
  const { ExamFields } = await load('/src/pages/staff/ExamFormPage.jsx')
  const values = { title: 'Draft exam', subject: 4, duration_minutes: 30, pass_mark: 0, attempt_limit: 1, resume_allowed: true, start_at: '', end_at: '' }
  const options = { subjects: [{ id: 4, name: 'Selected subject' }], groups: [], choices: { assessment_type: [{ value: 'test' }], candidate_access: [{ value: 'assigned_group' }, { value: 'access_code' }] } }
  const markup = html(ExamFields, { values, options, t, onChange() {} })
  assert.match(markup, /Draft exam/)
  assert.match(markup, /Selected subject/)
  assert.match(markup, /name="duration_minutes"/)
  assert.doesNotMatch(markup, /name="status"/)
  const source = await readFile(new URL('../src/pages/staff/ExamFormPage.jsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /QuestionAttachment|Approved question/ )
  assert.match(source, /Manage Questions/)
  assert.doesNotMatch(source, /fetch\(/)
}))

test('Arabic RTL and bilingual mode use existing language architecture', async () => modules(async load => {
  const { useExamCopy } = await load('/src/pages/staff/exam-ui.jsx')
  const { LanguageModeProvider } = await load('/src/context/LanguageModeContext.jsx')
  const previous = globalThis.localStorage
  function View() { const { t, direction } = useExamCopy(); return React.createElement('section', { dir: direction }, t('Overview')) }
  try {
    globalThis.localStorage = { getItem: () => 'arabic' }
    const arabic = renderToStaticMarkup(React.createElement(LanguageModeProvider, null, React.createElement(View)))
    assert.match(arabic, /dir="rtl"/)
    assert.ok(arabic.includes(examCopy.Overview))
    globalThis.localStorage = { getItem: () => 'bilingual' }
    const bilingual = renderToStaticMarkup(React.createElement(LanguageModeProvider, null, React.createElement(View)))
    assert.match(bilingual, /Overview/)
    assert.ok(bilingual.includes(examCopy.Overview))
    assert.equal(examCopy['Correct answer'], '\u0627\u0644\u0625\u062c\u0627\u0628\u0629 \u0627\u0644\u0635\u062d\u064a\u062d\u0629')
  } finally { globalThis.localStorage = previous }
}))

test('routes remain behind workspace guard and responsive scrolling is contained', async () => {
  const app = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8')
  const shell = await readFile(new URL('../src/layouts/StaffLayout.jsx', import.meta.url), 'utf8')
  const styles = await readFile(new URL('../src/pages/staff/exams.css', import.meta.url), 'utf8')
  assert.match(app, /RequireWorkspace><StaffLayout/)
  assert.match(app, /path="exams" element={<ExamsPage/)
  assert.match(app, /path="exams\/:assessmentId\/edit"/)
  assert.doesNotMatch(app, /\['exams', 'Exams', 'assessments'\]/)
  assert.match(shell, /Outlet key={currentWorkspace\?\.institution.id}/)
  assert.match(styles, /exam-sections.*overflow-x:auto/)
  assert.match(styles, /exam-table-scroll.*max-width:100%; overflow:auto/)
  assert.match(styles, /grid-template-columns:minmax\(0,1fr\)/)
})

// Resolve the real App/Routes/StaffLayout and real page components. Only session,
// workspace and async read state are fixtures: native SSR does not run effects.
async function applicationRoutes(run, obsoleteExams = false) {
  const server = await createServer({ configLoader: 'runner',
    server: { middlewareMode: true, hmr: false }, appType: 'custom',
    optimizeDeps: { noDiscovery: true, include: [] },
    plugins: [{
      name: 'exam-application-route-fixtures', enforce: 'pre',
      resolveId(source) {
        if (source.endsWith('/context/AuthContext.jsx')) return '\0exam-route-auth'
        if (source.endsWith('/context/WorkspaceContext.jsx')) return '\0exam-route-workspace'
        if (source.endsWith('/staff/exam-ui.jsx') || source === './exam-ui.jsx') return '\0exam-route-read'
      },
      load(id) {
        if (id === '\0exam-route-auth') return 'export function useAuth() { return globalThis.__examRouteFixture.auth }'
        if (id === '\0exam-route-workspace') return 'export function useWorkspace() { return globalThis.__examRouteFixture.workspace }'
        if (id === '\0exam-route-read') return `
          export * from '/src/pages/staff/exam-ui.jsx?actual-route-ui';
          export function useOwnerRead(key) { return globalThis.__examRouteFixture.read(key) }
        `
      },
      transform(source, id) {
        if (obsoleteExams && id.endsWith('/src/App.jsx')) {
          return source.replace('<Route path="exams" element={<ExamsPage />} />', '<Route path="exams" element={<PlaceholderPage title="Exams" />} />')
        }
      },
    }],
  })
  const calls = []
  const workspace = { institution: { id: 7, name: 'Demo Training Institute', institution_type: 'training_provider' }, role: 'institution_admin' }
  const options = { subjects: [{ id: 4, name: 'Selected subject' }], groups: [], choices: { assessment_type: [{ value: 'test' }], candidate_access: [{ value: 'assigned_group' }, { value: 'access_code' }] } }
  const fixtureExam = { ...exam, subject: 4 }
  globalThis.__examRouteFixture = {
    auth: { user: { id: 1, email: 'admin@route.test' }, loading: false },
    workspace: { currentWorkspace: workspace, currentRole: workspace.role, workspaces: [workspace], accessState: 'ready', loading: false },
    read(key) {
      calls.push(key)
      let data
      if (key === '7:::1') data = { count: 1, results: [fixtureExam] }
      else if (/^7:(results|reports|submissions)::1$/.test(key)) data = { count: 1, results: [{ ...fixtureExam, report_available: false, summary: { total_candidates: 1, not_started_count: 1, in_progress_count: 0, submitted_count: 0, auto_submitted_count: 0, not_submitted_count: 0, results_count: 0, passed_count: 0, failed_count: 0, average_percentage: null, pass_rate: null, release_state: 'no_results' } }] }
      else if (key === '7:11') data = fixtureExam
      else if (key === '7:new:form') data = { options, exam: null }
      else if (key === '7:11:form') data = { options, exam: fixtureExam }
      else if (key.startsWith('7:11:readiness:')) data = { count: 1, results: [] }
      else if (key.startsWith('7:11:access-eligibility:')) data = { count: 1, eligible_count: 1, results: [] }
      else if (key === '7:setup-options') data = options
      else if (key.startsWith('7:11:questions')) data = { count: 1, results: [{ id: 1, order: 1, marks: '2.00', question }] }
      else if (key.startsWith('7:11:candidates:')) data = { mode: 'access_code', workflow_status: 'draft', window: 'open', count: 1, results: [{ id: 5, candidate_id: 'C-1', name: 'Amina Candidate', status: 'active' }] }
      else if (/^7:11:(overview|submissions|results|reports):/.test(key)) data = { count: 1, results: [{ candidate: 5, candidate_id: 'C-1', name: 'Amina Candidate', submission_status: 'not_started', result: null }], summary: { total_candidates: 1, not_started_count: 1, in_progress_count: 0, submitted_count: 0, auto_submitted_count: 0, not_submitted_count: 0, results_count: 0, average_percentage: null, pass_rate: null, highest_percentage: null, lowest_percentage: null }, delivery_supported: true }
      else if (key.endsWith(':submission:undefined')) data = null
      else if (key.includes(':config:')) data = { exam_code: 'ROUTE-EXAM', enabled: true }
      else if (key.includes(':credentials:')) data = { count: 1, results: [{ id: 91, candidate: 5, candidate_name: 'Amina Candidate', candidate_identifier: 'C-1', candidate_status: 'active', active: true, version: 987654, expires_at: null, generated_at: '2026-10-01T00:00:00Z', revoked_at: null }] }
      else if (key === '7::1') data = { count: 0, results: [] }
      else if (key.includes(':links:')) data = []
      else if (key.startsWith('7:4:')) data = { count: 1, results: [question] }
      else if (key.endsWith(':preview:false')) data = null
      else throw new Error(`Unexpected route/page read: ${key}`)
      return { data, loading: false, retry() {} }
    },
  }
  try {
    const { default: App } = await server.ssrLoadModule('/src/App.jsx')
    const { LanguageModeProvider } = await server.ssrLoadModule('/src/context/LanguageModeContext.jsx')
    const render = (path, role = 'institution_admin') => {
      calls.length = 0
      globalThis.__examRouteFixture.workspace.currentRole = role
      const markup = renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: [path] },
        React.createElement(LanguageModeProvider, null, React.createElement(App))))
      return { markup, calls: [...calls] }
    }
    await run(render)
  } finally {
    delete globalThis.__examRouteFixture
    await server.close()
  }
}

function assertRealExamList(markup) {
  assert.match(markup, /Manage examinations in this workspace/)
  assert.match(markup, /Client examination/)
  assert.match(markup, /Search exams/)
  assert.match(markup, /All statuses/)
  assert.match(markup, /Create Exam/)
  assert.doesNotMatch(markup, /Content will appear here|This area is ready for its page content/)
}

test('actual application routes render Exams list, create, detail and edit pages', async () => applicationRoutes(async render => {
  const list = render('/app/exams')
  assertRealExamList(list.markup)
  assert.deepEqual(list.calls, ['7:::1'])
  const create = render('/app/exams/new')
  assert.match(create.markup, /<h1>Create Exam<\/h1>/)
  assert.match(create.markup, /How will candidates enter this exam/)
  assert.match(create.markup, /Quick Exam/)
  assert.match(create.markup, /Through their account/)
  assert.doesNotMatch(create.markup, /name="title"/)
  assert.deepEqual(create.calls, ['7:new:form']) // The literal new route wins over :assessmentId.
  const detail = render('/app/exams/11')
  assert.match(detail.markup, /Exam sections/)
  assert.match(detail.markup, /Client examination/)
  assert.ok(detail.calls.includes('7:11'))
  const edit = render('/app/exams/11/edit')
  assert.match(edit.markup, /<h1>Edit Exam<\/h1>/)
  assert.match(edit.markup, /Manage Questions/)
  assert.doesNotMatch(edit.markup, /Attached questions|Approved question/)
  assert.ok(edit.calls.includes('7:11:form'))
  for (const result of [create, detail, edit]) assert.doesNotMatch(result.markup, /Content will appear here/)
}))

test('actual main Results Reports and Submissions routes render assessment centres instead of placeholders', async () => applicationRoutes(async render => {
  for (const section of ['results', 'reports', 'submissions']) {
    const { markup, calls } = render(`/app/${section}`)
    assert.match(markup, /Client examination/)
    assert.match(markup, /Search assessments/)
    assert.match(markup, new RegExp(`/app/exams/11\\?section=${section}`))
    assert.deepEqual(calls, [`7:${section}::1`])
    assert.doesNotMatch(markup, /Content will appear here|This area is ready for its page content/)
  }
}))

test('actual detail query routing selects sections and protects Access', async () => applicationRoutes(async render => {
  for (const section of ['overview', 'questions', 'candidates', 'access', 'submissions', 'results', 'reports']) {
    const { markup, calls } = render(`/app/exams/11?section=${section}`)
    assert.match(markup, /Client examination/)
    const selectedLink = [...markup.matchAll(/<a\b[^>]*>/g)].find(match => match[0].includes(`href="/app/exams/11?section=${section}"`))
    assert.ok(selectedLink, `Missing section link: ${section}`)
    assert.match(selectedLink[0], /aria-current="page"/)
    assert.ok(calls.includes('7:11'))
    if (section === 'overview') assert.match(markup, /Total marks/)
    if (section === 'questions') { assert.match(markup, /Inspection question/); assert.match(markup, /View question/); assert.match(markup, /Add Questions/) }
    if (section === 'candidates') assert.match(markup, /Amina Candidate/)
    if (section === 'access') assert.match(markup, /Generate credential/)
  }
  for (const role of ['teacher', 'examiner']) {
    const { markup, calls } = render('/app/exams/11?section=access', role)
    assert.doesNotMatch(markup, /Generate credential|section=access/)
    assert.match(markup, /Total marks/)
    assert.ok(calls.every(key => !key.includes(':config:') && !key.includes(':credentials:')))
  }
  const candidate = globalThis.__examRouteFixture.workspace
  candidate.accessState = 'no_workspace'; candidate.currentWorkspace = null
  const denied = render('/app/exams', 'student')
  assert.match(denied.markup, /No workspace access/)
  assert.deepEqual(denied.calls, [])
}))

test('route regression assertions reject the obsolete placeholder while deferred routes retain it', async () => {
  await applicationRoutes(async render => {
    for (const path of ['/app/staff', '/app/classes', '/app/settings']) assert.match(render(path).markup, /Content will appear here/)
  })
  await applicationRoutes(async render => {
    const obsolete = render('/app/exams')
    assert.match(obsolete.markup, /Content will appear here/)
    assert.throws(() => assertRealExamList(obsolete.markup), assert.AssertionError)
  }, true)
})


test('detail header and authorized credential table omit internal IDs and versions', async () => applicationRoutes(async render => {
  const detail = render('/app/exams/11?section=overview')
  const header = detail.markup.match(/<header class="exam-heading">[\s\S]*?<\/header>/)?.[0]
  assert.ok(header)
  assert.match(header, /<p>Draft<\/p>/)
  assert.doesNotMatch(header, /Workspace|Institution|>7<|Workspace: 7/)
  for (const role of ['institution_admin', 'platform_admin']) {
    const access = render('/app/exams/11?section=access', role)
    const table = access.markup.match(/<table class="exam-table">[\s\S]*?<\/table>/)?.[0]
    assert.ok(table)
    assert.match(table, /Amina Candidate/)
    assert.match(table, /Valid credential/)
    assert.match(table, /Reset PIN/)
    assert.match(table, />Revoke</)
    assert.doesNotMatch(table, /Version|987654/)
  }
}))
