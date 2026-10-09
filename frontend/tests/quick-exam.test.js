import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { createServer } from 'vite'
import { readFile } from 'node:fs/promises'
import postcss from 'postcss'
import { createExamAdapter, verifyQuickAccess, loadQuickAccess, startQuickAccess, endQuickAccess, endQuickAccessBeforeStart, rememberQuickAttempt, getQuickAttemptPath, clearQuickAttempt } from '../src/services/examAdapters.js'
import { quickExamTranslate } from '../src/utils/quickExamLocale.js'
import { installPublicReveal } from '../src/utils/publicReveal.js'

const context = {
  candidate: { candidate_id: 'TEST-CANDIDATE', first_name: 'Example', last_name: 'Candidate' },
  assessment: { id: 12, title: 'Objective examination', description: 'Read carefully.', duration_minutes: 45, question_count: 3, start_at: '2026-10-03T08:00:00Z', end_at: '2026-10-03T12:00:00Z' },
  availability: { state: 'available', can_start: true, can_resume: false, attempts_remaining: 1 },
}

test('verification bootstraps CSRF, sends only credentials, and never starts an attempt', async () => {
  const calls = []
  const response = await verifyQuickAccess(async (path, options) => { calls.push([path, options]); return path === 'auth/csrf/' ? { csrfToken: 'test-csrf' } : { verified: true } }, { exam_code: ' TEST ', candidate_id: ' TEST-CANDIDATE ', pin: ' test-pin ', assessment: 99, user: 5 })
  assert.equal(response.verified, true)
  assert.deepEqual(calls, [['auth/csrf/', undefined], ['quick-exam/verify/', { method: 'POST', body: { exam_code: 'TEST', candidate_id: 'TEST-CANDIDATE', pin: ' test-pin ' } }]])
  await assert.rejects(verifyQuickAccess(async () => ({}), { exam_code: 'TEST', candidate_id: 'TEST', pin: 'test' }), /Unexpected verification/)
})

test('invalid credentials remain an error; raw failure details are not needed by the entry view', async () => {
  const error = Object.assign(new Error('Sensitive server detail'), { status: 401 })
  await assert.rejects(verifyQuickAccess(async path => { if (path.endsWith('verify/')) throw error; return {} }, { exam_code: 'TEST', candidate_id: 'TEST', pin: 'test' }), caught => caught.status === 401)
})

test('cookie recovery treats only Quick 401 as expired and does not fall back to normal account auth', async () => {
  const calls = []
  assert.equal(await loadQuickAccess(async path => { calls.push(path); return context }), context)
  assert.deepEqual(calls, ['quick-exam/session/'])
  assert.equal(await loadQuickAccess(async () => { throw Object.assign(new Error(), { status: 401 }) }), null)
  for (const error of [new Error('network'), Object.assign(new Error(), { status: 500 }), Object.assign(new Error(), { status: 403 })]) await assert.rejects(loadQuickAccess(async () => { throw error }), caught => caught === error)
  for (const value of [null, {}, { ...context, availability: {} }]) await assert.rejects(loadQuickAccess(async () => value), /Unexpected examination/)
})

test('start and resume use the cookie context with an empty body; malformed starts do not produce an attempt URL', async () => {
  let call
  const attempt = await startQuickAccess(async (path, options) => { call = [path, options]; return { id: 31, status: 'in_progress' } })
  assert.equal(attempt.id, 31)
  assert.deepEqual(call, ['quick-exam/start/', { method: 'POST', body: {} }])
  for (const value of [{}, { id: '../student', status: 'in_progress' }, { id: 31, status: 'submitted' }]) await assert.rejects(startQuickAccess(async () => value), /Unexpected attempt/)
})

test('all shared runner operations stay inside their access mode and retain answer/review/integrity semantics', async () => {
  for (const mode of ['portal', 'quick']) {
    const calls = []; const api = createExamAdapter(async (path, options) => { calls.push([path, options]); return { status: 'in_progress' } }, { mode })
    await api.getAttempt(31); await api.getAttemptQuestions(31); await api.getAttemptQuestion(31, 7)
    await api.saveAttemptAnswer(31, 7, [5, 3]); await api.setAttemptReview(31, 7, true); await api.setAttemptReview(31, 7, false)
    await api.getAttemptIntegrity(31); await api.recordAttemptIntegrity(31, 'page_hidden'); await api.submitAttempt(31)
    const base = mode === 'quick' ? 'quick-exam/attempt/31' : 'attempts/31'
    assert.deepEqual(calls.map(([path]) => path), [`${base}/`, `${base}/questions/`, `${base}/questions/7/`, `${base}/questions/7/answer/`, `${base}/questions/7/review/`, `${base}/questions/7/review/`, 'auth/csrf/', `${base}/integrity/`, `${base}/integrity/`, `${base}/submit/`])
    assert.deepEqual(calls[3][1], { method: 'PUT', body: { selected_options: [5, 3] } })
    assert.deepEqual(calls[5][1].body, { marked_for_review: false })
    assert.deepEqual(calls[8][1], { method: 'POST', body: { signal: 'page_hidden' }, keepalive: true })
    assert.deepEqual(calls[9][1].body, {})
    assert.throws(() => api.getAttempt('../99'), /not valid/)
  }
})

test('Quick expiry triggers reverification; wrong IDs, network failures and backend errors disclose no raw detail or local termination', async () => {
  for (const status of [401, 403, 404, 500, undefined]) {
    let expired = 0
    const api = createExamAdapter(async () => { throw Object.assign(new Error('Private detail /api/trace'), { status }) }, { mode: 'quick', onAccessExpired: () => expired++ })
    await assert.rejects(api.getAttempt(31), error => error.status === status && !error.message.includes('Private') && !error.message.includes('/api/'))
    assert.equal(expired, status === 401 ? 1 : 0)
  }
  const original = new Error('Portal error')
  await assert.rejects(createExamAdapter(async () => { throw original }).getAttempt(31), caught => caught === original)
})

test('Done ends only Quick access, and navigation state contains only a transient path', async () => {
  const calls = []
  await endQuickAccess(async (path, options) => { calls.push([path, options]) })
  assert.deepEqual(calls, [['auth/csrf/', undefined], ['quick-exam/logout/', { method: 'POST', body: {} }]])
  rememberQuickAttempt('/take-exam/attempt/31'); assert.equal(getQuickAttemptPath(), '/take-exam/attempt/31')
  clearQuickAttempt(32); assert.equal(getQuickAttemptPath(), '/take-exam/attempt/31')
  clearQuickAttempt(31); assert.equal(getQuickAttemptPath(), null)
})

test('real API transport sends cookies and CSRF on Quick mutations without an institution header or credential persistence', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  const originalFetch = globalThis.fetch
  try {
    const { apiFetch, setInstitutionContext } = await server.ssrLoadModule('/src/services/api.js')
    setInstitutionContext(99)
    const calls = []
    globalThis.fetch = async (url, options) => {
      calls.push([url, options])
      const body = url.endsWith('/auth/csrf/') ? { csrfToken: 'test-csrf' } : url.endsWith('/verify/') ? { verified: true } : url.endsWith('/session/') ? context : { id: 31, status: 'in_progress' }
      return new Response(JSON.stringify(body), { status: 200, headers: { 'content-type': 'application/json' } })
    }
    await verifyQuickAccess(apiFetch, { exam_code: 'TEST', candidate_id: 'TEST', pin: 'test' })
    await loadQuickAccess(apiFetch); await startQuickAccess(apiFetch)
    const api = createExamAdapter(apiFetch, { mode: 'quick' })
    await api.saveAttemptAnswer(31, 7, [3]); await api.setAttemptReview(31, 7, true); await api.recordAttemptIntegrity(31, 'page_hide'); await api.submitAttempt(31); await endQuickAccess(apiFetch)
    for (const [url, options] of calls) {
      assert.equal(options.credentials, 'include')
      assert.equal(options.headers.has('X-Institution-ID'), false)
      assert.ok(url.endsWith('/auth/csrf/') || url.includes('/quick-exam/'))
      if (['POST', 'PUT', 'PATCH'].includes(options.method)) assert.equal(options.headers.get('X-CSRFToken'), 'test-csrf')
      if (!url.endsWith('/verify/')) assert.doesNotMatch(options.body || '', /"pin"|"candidate_id"|"exam_code"/)
    }
  } finally { globalThis.fetch = originalFetch; await server.close() }
})

test('real Quick views render accessible credentials, authoritative availability, objective controls and score-free completion in both languages', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  try {
    const views = await server.ssrLoadModule('/src/pages/public/QuickExamPages.jsx')
    const components = await server.ssrLoadModule('/src/components/student/StudentComponents.jsx')
    const render = (Component, props) => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(Component, props)))
    for (const locale of ['en', 'ar']) {
      const t = text => quickExamTranslate(locale, text)
      const form = render(views.QuickCredentialForm, { t, busy: true, error: t('We could not verify these details. Check them and try again.') })
      for (const name of ['exam_code', 'candidate_id', 'pin']) assert.match(form, new RegExp(`name="${name}"`))
      assert.match(form, /type="password"/); assert.match(form, /type="submit" disabled="" aria-busy="true"/); assert.match(form, /aria-describedby="quick-access-error"/)
      assert.doesNotMatch(form, /name="email"|name="assessment"|name="institution"/)
      assert.match(form, new RegExp(t('Show PIN')))
      for (const [state, start, resume] of [['available', true, false], ['in_progress', false, true], ['upcoming', false, false], ['ended', false, false], ['attempt_limit_reached', false, false], ['unavailable', false, false]]) {
        const html = render(views.QuickInstructionsView, { session: { ...context, availability: { ...context.availability, state, can_start: start, can_resume: resume } }, t, locale })
        assert.match(html, /Objective examination/); assert.match(html, /TEST-CANDIDATE/)
        if (start || resume) assert.match(html, new RegExp(t(resume ? 'Resume examination' : 'Start examination')))
        else assert.doesNotMatch(html, /<button/)
        assert.doesNotMatch(html, /role="timer"|proctor|passing score/i)
      }
      for (const type of ['multiple_choice', 'multiple_select', 'true_false']) {
        const html = render(components.QuestionRenderer, { question: { id: 7, type, prompt: 'Authored question', options: [{ id: 5, label: 'True' }, { id: 3, label: 'False' }] }, value: [3], translate: t })
        assert.match(html, /Authored question/); assert.match(html, new RegExp(`type="${type === 'multiple_select' ? 'checkbox' : 'radio'}"`))
        assert.match(html, /value|checked=""/); assert.ok(html.indexOf('True') < html.indexOf('False'))
      }
      const navigator = render(components.QuestionNavigator, { questions: [{ id: 7, answered: true }, { id: 8 }], answers: {}, marked: new Set([1]), current: 0, translate: t })
      assert.match(navigator, /aria-current="step"/); assert.match(navigator, /question-number--marked/)
      assert.match(render(components.ExamTimer, { seconds: 125, translate: t }), /02:05/)
      for (const status of ['submitted', 'expired']) {
        const complete = render(views.QuickCompletionView, { status, t })
        assert.match(complete, new RegExp(t('Done'))); assert.doesNotMatch(complete, /href="\/"/)
        assert.doesNotMatch(complete, /score|percentage|correct answers|My Results/i)
      }
    }
  } finally { await server.close() }
})

test('public reveal is progressive, once per group, and immediately visible for reduced motion, unavailable observers or observation failure', () => {
  function group(top = 900) {
    const classes = new Set()
    return { className: 'landing-section', parentElement: { closest: () => null }, classList: { add: (...names) => names.forEach(name => classes.add(name)), remove: (...names) => names.forEach(name => classes.delete(name)) }, style: { setProperty() {}, removeProperty() {} }, getBoundingClientRect: () => ({ top }), classes }
  }
  for (const environment of [{}, { matchMedia: () => ({ matches: true }) }]) {
    const element = group(); installPublicReveal({ querySelectorAll: () => [element] }, environment)()
    assert.equal(element.classes.has('public-reveal--pending'), false)
  }
  const element = group(); let callback; let observed = 0; let unobserved = 0; let preferenceChange
  class Observer { constructor(fn) { callback = fn } observe() { observed++ } unobserve() { unobserved++ } disconnect() {} }
  const cleanup = installPublicReveal({ querySelectorAll: () => [element] }, { innerHeight: 600, IntersectionObserver: Observer, matchMedia: () => ({ matches: false, addEventListener: (_, fn) => { preferenceChange = fn }, removeEventListener() {} }) })
  assert.equal(observed, 1); assert.equal(element.classes.has('public-reveal--pending'), true)
  callback([{ isIntersecting: true, target: element }]); assert.equal(unobserved, 1); assert.equal(element.classes.has('public-reveal--pending'), false)
  preferenceChange(); cleanup(); assert.equal(element.classes.has('public-reveal'), false)
  const broken = group(); installPublicReveal({ querySelectorAll: () => [broken] }, { innerHeight: 600, IntersectionObserver: class { observe() { throw new Error('observer failed') } disconnect() {} } })()
  assert.equal(broken.classes.has('public-reveal--pending'), false)
})


test('public navigation promotes candidate access into desktop/mobile actions and keeps acquisition primary in both languages', async () => {
  const server = await createServer({ plugins: [{ name: 'navigation-test-whatsapp', enforce: 'pre', transform(source, id) {
    if (id.endsWith('/ManagedExamCTA.jsx')) return source.replace('import.meta.env.VITE_PUBLIC_WHATSAPP_NUMBER', JSON.stringify('12345678901'))
  } }], server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  const previousStorage = globalThis.localStorage
  try {
    const { default: Layout } = await server.ssrLoadModule('/src/layouts/PublicLayout.jsx')
    const { managedExamMessage } = await server.ssrLoadModule('/src/components/common/ManagedExamCTA.jsx')
    for (const locale of ['en', 'ar']) {
      globalThis.localStorage = { getItem: () => locale }
      const route = React.createElement(Route, { element: React.createElement(Layout) }, React.createElement(Route, { path: '*', element: React.createElement('p', null, 'Content') }))
      const html = renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: ['/'] }, React.createElement(Routes, null, route)))
      assert.ok(html.includes(`lang="${locale}" dir="${locale === 'ar' ? 'rtl' : 'ltr'}"`))
      const navs = [...html.matchAll(/<nav class="public-nav"[^>]*>([\s\S]*?)<\/nav>/g)]
      assert.equal(navs.length, 2)
      for (const [, nav] of navs) assert.doesNotMatch(nav, /href="\/take-exam"/)
      const header = html.slice(html.indexOf('class="public-header__actions"'), html.indexOf('</header>'))
      const drawer = html.slice(html.indexOf('<dialog'), html.indexOf('</dialog>'))
      const mobile = drawer.slice(drawer.indexOf('class="public-mobile-drawer__actions"'), drawer.indexOf('class="public-language-switcher"'))
      for (const actions of [header, mobile]) {
        const links = [...actions.matchAll(/<a([^>]+)>(.*?)<\/a>/g)]
        const hrefs = links.map(([, attrs]) => attrs.match(/href="([^"]+)"/)[1].replaceAll('&#x27;', "'"))
        assert.deepEqual(hrefs.slice(0, 2), ['/take-exam', '/signin'])
        const destination = new URL(hrefs[2])
        assert.equal(destination.origin, 'https://wa.me')
        assert.equal(destination.pathname, '/12345678901')
        assert.equal(destination.searchParams.get('text'), managedExamMessage)
        assert.match(links[2][1], /target="_blank"/)
        assert.match(links[2][1], /rel="noopener noreferrer"/)
        assert.match(links[0][1], /button--outline.*public-exam-cta/)
        assert.equal(links[0][2], quickExamTranslate(locale, 'Take an Exam'))
        assert.match(links[1][1], /button--ghost/)
        assert.match(links[2][1], /button--primary/)
      }
      assert.ok(drawer.indexOf('public-mobile-drawer__actions') < drawer.indexOf('public-nav'))
    }
  } finally { if (previousStorage === undefined) delete globalThis.localStorage; else globalThis.localStorage = previousStorage; await server.close() }
})

test('actual Quick entry has localized supporting content, credential fields, continue, and recovery state', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  const previousStorage = globalThis.localStorage
  try {
    const { QuickEntryPage } = await server.ssrLoadModule('/src/pages/public/QuickExamPages.jsx')
    const { PublicLocaleProvider, PublicLocaleTree } = await server.ssrLoadModule('/src/context/PublicLocaleContext.jsx')
    for (const locale of ['en', 'ar']) {
      globalThis.localStorage = { getItem: () => locale }
      const t = text => quickExamTranslate(locale, text)
      const html = renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: [{ pathname: '/take-exam', state: { reverify: true } }] }, React.createElement(PublicLocaleProvider, null, React.createElement(PublicLocaleTree, null, React.createElement(QuickEntryPage)))))
      assert.match(html, /class="quick-exam-entry" aria-labelledby="quick-entry-title"/)
      assert.match(html, /quick-exam-entry__copy/); assert.match(html, /quick-exam-entry__card/)
      for (const text of ['Take an Exam', 'Ready to begin?', 'Enter the examination details provided by your institution or examination organiser.', 'You will review the examination details and instructions before your timer begins.', 'Continue']) assert.ok(html.includes(t(text)))
      assert.match(html, /role="status"/); assert.ok(html.includes(t('Your access has expired. Verify your details again to continue.')))
      for (const name of ['exam_code', 'candidate_id', 'pin']) assert.ok(html.includes(`name="${name}"`))
      assert.match(html, /type="password"/); assert.match(html, /aria-controls="quick-pin" aria-pressed="false"/)
      assert.ok(html.includes(t('Show PIN'))); assert.match(html, /type="submit"/); assert.match(html, /href="\/"/)
      assert.doesNotMatch(html, /role="timer"|data-public-reveal/)
      assert.ok(html.includes(`dir="${locale === 'ar' ? 'rtl' : 'ltr'}"`))
    }
  } finally { if (previousStorage === undefined) delete globalThis.localStorage; else globalThis.localStorage = previousStorage; await server.close() }
})

test('entry CSS stacks at tablet/mobile widths and uses mirrored logical spacing without fixed heights', async () => {
  const sheet = postcss.parse(await readFile(new URL('../src/styles/quick-exam.css', import.meta.url), 'utf8'))
  const rules = []; sheet.walkRules(rule => { if (rule.selector.includes('quick-exam-entry')) rules.push(rule) })
  const entry = rules.find(rule => rule.selector === '.quick-exam-entry')
  assert.ok(entry.nodes.some(node => node.prop === 'grid-template-columns' && node.value === 'minmax(0, 1fr) minmax(0, 1fr)'))
  const stacked = rules.find(rule => rule.selector === '.quick-exam-entry' && rule.parent.params === '(max-width: 767px)')
  assert.ok(stacked.nodes.some(node => node.prop === 'grid-template-columns' && node.value === 'minmax(0, 1fr)'))
  assert.ok(rules.some(rule => rule.parent.params === '(max-width: 480px)'))
  assert.ok(rules.some(rule => rule.selector === '[dir="rtl"] .quick-exam-entry'))
  assert.ok(rules.some(rule => rule.nodes.some(node => node.prop === 'border-inline-start')))
  for (const rule of rules) assert.ok(rule.nodes.every(node => !['height', 'min-height', 'margin-left', 'margin-right'].includes(node.prop)))
})


test('actual application routes keep entry public and place every verified Quick route outside marketing layout in both languages', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  const previousStorage = globalThis.localStorage
  try {
    const { default: App } = await server.ssrLoadModule('/src/App.jsx')
    for (const locale of ['en', 'ar']) {
      globalThis.localStorage = { getItem: () => locale }
      for (const path of ['/take-exam', '/take-exam/instructions', '/take-exam/attempt/31', '/take-exam/complete']) {
        const html = renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: [path] }, React.createElement(App)))
        assert.ok(html.includes(`lang="${locale}" dir="${locale === 'ar' ? 'rtl' : 'ltr'}"`))
        if (path === '/take-exam') {
          assert.match(html, /public-header|public-footer|quick-exam-entry__card/)
          assert.match(html, /href="\/#managed-examinations"/); assert.match(html, /href="\/signin"/); assert.match(html, /href="\/contact"/)
        } else {
          assert.match(html, /quick-exam-layout/)
          assert.doesNotMatch(html, /public-nav|public-header|public-footer|public-marketing-motion|data-public-reveal/)
          assert.doesNotMatch(html, /href="\/(features|how-it-works|pricing|about|contact|signin|setup)"/)
          if (path.includes('/attempt/')) assert.doesNotMatch(html, /class="quick-exam-header"/)
          else assert.match(html, /class="quick-exam-header"/)
        }
      }
    }
  } finally { if (previousStorage === undefined) delete globalThis.localStorage; else globalThis.localStorage = previousStorage; await server.close() }
})

test('verified briefing/frame show candidate summary, authoritative states and distinct Start/Resume timing, with no marketing', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  const previousStorage = globalThis.localStorage
  try {
    const views = await server.ssrLoadModule('/src/pages/public/QuickExamPages.jsx')
    const { PublicLocaleProvider, PublicLocaleTree } = await server.ssrLoadModule('/src/context/PublicLocaleContext.jsx')
    for (const locale of ['en', 'ar']) {
      globalThis.localStorage = { getItem: () => locale }
      const t = text => quickExamTranslate(locale, text)
      const render = props => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(PublicLocaleProvider, null, React.createElement(PublicLocaleTree, null, React.createElement(views.QuickExamFrame, { ...props, t })))))
      for (const resume of [false, true]) {
        const session = { ...context, availability: { ...context.availability, state: resume ? 'in_progress' : 'available', can_resume: resume, can_start: !resume } }
        const html = render({ session, children: React.createElement(views.QuickInstructionsView, { session, t, locale }) })
        assert.match(html, /quick-exam-briefing__grid/); assert.match(html, /quick-exam-briefing__summary/)
        assert.doesNotMatch(html, /quick-exam-panel|public-header|public-nav|public-footer|data-public-reveal/)
        for (const text of ['Candidate', 'Candidate ID', 'Duration', 'Questions', 'Attempts remaining', 'Starts', 'Ends']) assert.ok(html.includes(t(text)))
        assert.match(html, /TEST-CANDIDATE/); assert.match(html, /Example Candidate/); assert.match(html, /Objective examination/)
        assert.ok(html.includes(t('45 min')))
        assert.ok(html.includes(t(resume ? 'An existing attempt keeps its original deadline when resumed.' : 'Your examination timer will begin when you select Start Exam.')))
        if (resume) { assert.ok(!html.includes(t('Your examination timer will begin when you select Start Exam.'))); assert.ok(!html.includes(t('End Session'))) }
        else assert.ok(html.includes(t('End Session')))
        assert.ok(html.includes(t(resume ? 'Resume examination' : 'Start examination')))
      }
      for (const props of [{ live: true }, { complete: true }]) {
        const html = render({ session: context, ...props, children: React.createElement(views.QuickCompletionView, { t, status: 'submitted' }) })
        assert.ok(!html.includes(t('End Session')))
        assert.doesNotMatch(html, /href="\/"|score|percentage|correct answers|My Results/i)
        assert.ok(html.includes(t('Done')))
        if (props.live) assert.doesNotMatch(html, /class="quick-exam-header"/)
      }
      const inactive = render({ session: context, live: true, children: React.createElement(views.QuickClientNotice, { t, inactive: true, onTakeover() {} }) })
      assert.ok(inactive.includes(t('Take over this exam'))); assert.match(inactive, /href="\/take-exam"/)
      const expired = render({ session: context, live: true, children: React.createElement(views.QuickClientNotice, { t, expiredAccess: true, onTakeover() {} }) })
      assert.ok(!expired.includes(t('Take over this exam')))
    }
  } finally { if (previousStorage === undefined) delete globalThis.localStorage; else globalThis.localStorage = previousStorage; await server.close() }
})

test('pre-start End Session rechecks server availability and calls only Quick logout; active attempts cannot be ended this way', async () => {
  for (const active of [false, true]) {
    const calls = []
    const ended = await endQuickAccessBeforeStart(async (path, options) => { calls.push([path, options]); return path === 'quick-exam/session/' ? { ...context, availability: { ...context.availability, state: active ? 'in_progress' : 'available', can_resume: active } } : null })
    assert.equal(ended, !active)
    assert.deepEqual(calls.map(([path]) => path), active ? ['quick-exam/session/'] : ['quick-exam/session/', 'auth/csrf/', 'quick-exam/logout/'])
    assert.ok(calls.every(([path]) => path !== 'auth/logout/'))
  }
  await assert.rejects(endQuickAccessBeforeStart(async () => { throw new Error('network') }), /network/)
})

test('briefing and focused header CSS stack on mobile and use logical RTL spacing', async () => {
  const sheet = postcss.parse(await readFile(new URL('../src/styles/quick-exam.css', import.meta.url), 'utf8'))
  const rules = []; sheet.walkRules(rule => rules.push(rule))
  assert.ok(rules.some(rule => rule.selector === '.quick-exam-briefing__grid' && rule.parent.params === '(max-width: 767px)' && rule.nodes.some(node => node.prop === 'grid-template-columns' && node.value === 'minmax(0, 1fr)')))
  assert.ok(rules.some(rule => rule.selector === '.quick-exam-briefing__actions > .button' && rule.parent.params === '(max-width: 767px)' && rule.nodes.some(node => node.prop === 'width' && node.value === '100%')))
  assert.ok(rules.some(rule => rule.selector === '.quick-exam-header' && rule.parent.params === '(max-width: 480px)'))
  assert.ok(rules.some(rule => rule.selector === '.quick-exam-briefing__timer' && rule.nodes.some(node => node.prop === 'border-inline-start')))
})
