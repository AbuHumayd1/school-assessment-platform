import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import { readFile } from 'node:fs/promises'
import postcss from 'postcss'

const server = await createServer({ configLoader: 'runner', server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
const { WorkspaceDashboardView } = await server.ssrLoadModule('/src/pages/staff/WorkspaceDashboardPage.jsx')
test.after(() => server.close())
const assessment = { id: 47, title: 'Term assessment', subject: 'Mathematics', group: 'Cohort A', status: 'scheduled', start_at: '2026-10-10T08:00:00Z', end_at: '2026-10-10T10:00:00Z', duration_minutes: 30 }
const summaryData = { institution: { id: 3, timezone: 'Africa/Lagos' }, counts: { active_candidates: 12, questions: 60, assessments: 7, results: 4, published_results: 2, submitted_attempts: 5 }, assessment_status_counts: { draft: 2, review: 1, approved: 1, scheduled: 3, archived: 0 } }
const props = { currentWorkspace: { institution: { id: 3, name: 'Example Academy', workspace_mode: 'full' } }, currentRole: 'institution_admin', t: en => en, languageMode: 'english', now: new Date(2026, 9, 10, 18), summary: { data: summaryData }, assessments: { data: { timezone: 'Africa/Lagos', upcoming_assessments: [assessment], recent_assessments: [{ ...assessment, id: 81, title: 'New preparation', status: 'draft', group: null }] } }, results: { data: { recent_results: [{ id: 5, assessment_title: 'Completed assessment', candidate_id: 'C-004', marks_obtained: '8.00', total_marks: '10.00', status: 'published', marked_at: '2026-10-10T09:00:00Z' }] } } }
const render = extra => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(WorkspaceDashboardView, { ...props, ...extra })))

test('dashboard presents institution, real counts, assessment IDs and safe result fields', () => {
  const html = render()
  for (const text of ['Good evening', 'Example Academy', 'Term assessment', 'Mathematics', 'Cohort A', 'C-004', 'Completed assessment', '8 / 10', 'Published results', 'Submitted attempts']) assert.ok(html.includes(text), text)
  assert.ok(html.includes('href="/app/exams/47"'))
  assert.ok(html.includes('href="/app/exams/81"'))
  assert.match(html, /aria-label="View assessment: Term assessment"/)
  assert.ok(html.includes('href="/app/results"'))
  assert.ok(html.indexOf('Upcoming &amp; active assessments') < html.indexOf('Assessment pipeline'))
  assert.ok(html.indexOf('Assessment pipeline') < html.indexOf('Recently created assessments'))
  assert.doesNotMatch(html, /NaN|undefined|[+]12%/)
})

test('zero workspace retains onboarding and all designed empty states without fake counts', () => {
  const html = render({ summary: { data: { ...summaryData, counts: Object.fromEntries(Object.keys(summaryData.counts).map(key => [key, 0])), assessment_status_counts: { draft: 0, review: 0, approved: 0, scheduled: 0, archived: 0 } } }, assessments: { data: { upcoming_assessments: [], recent_assessments: [] } }, results: { data: { recent_results: [] } } })
  for (const text of ['Ready for your first assessment', 'Candidates', 'Questions', 'Conduct', 'No scheduled assessments yet', 'No results yet', 'ready for its first assessment']) assert.ok(html.includes(text), text)
  assert.doesNotMatch(html, /NaN|Infinity|undefined/)
})

test('actions follow existing capabilities for workspace roles and exclude unauthorized roles', () => {
  for (const currentRole of ['institution_admin', 'teacher', 'examiner']) {
    const html = render({ currentRole })
    for (const route of ['/app/exams/new', '/app/questions', '/app/students', '/app/reports']) assert.ok(html.includes('href="' + route + '"'), currentRole + route)
  }
  const unauthorized = render({ currentRole: 'student' })
  assert.ok(!unauthorized.includes('href="/app/'))
  assert.ok(!unauthorized.includes('Quick actions'))
  const managed = render({ currentWorkspace: { institution: { ...props.currentWorkspace.institution, workspace_mode: 'managed_exam' } } })
  assert.ok(!managed.includes('href="/app/exams/new"') && !managed.includes('href="/app/questions"'))
})

test('independent loading and error states do not fabricate data or hide available sections', () => {
  const loading = render({ summary: { loading: true }, assessments: { loading: true }, results: { loading: true } })
  assert.match(loading, /aria-busy="true"/)
  assert.match(loading, /role="status"/)
  assert.doesNotMatch(loading, /Term assessment|C-004|Ready for your first assessment/)
  const error = render({ summary: { error: new Error(), retry() {} }, assessments: { error: new Error(), retry() {} } })
  assert.match(error, /role="alert"/)
  assert.match(error, /Try again/)
  assert.ok(error.includes('Completed assessment'))
  assert.doesNotMatch(error, /Term assessment|Published results/)
})

test('Arabic labels, localized counts and isolated user text remain supported', () => {
  const html = render({ t: (en, ar) => ar, languageMode: 'arabic' })
  assert.ok(html.includes('مساء الخير'))
  assert.ok(html.includes('إنشاء اختبار'))
  assert.ok(html.includes(new Intl.NumberFormat('ar').format(12)))
  assert.ok(html.includes('<bdi>Example Academy</bdi>'))
  assert.ok(html.includes('<bdi>C-004</bdi>'))
})

test('greeting follows local time without a backend dependency', () => {
  assert.ok(render({ now: new Date(2026, 9, 10, 8) }).includes('Good morning'))
  assert.ok(render({ now: new Date(2026, 9, 10, 14) }).includes('Good afternoon'))
})

test('dashboard stylesheet uses responsive grids and logical spacing', async () => {
  const css = await readFile(new URL('../src/pages/staff/workspace-dashboard.css', import.meta.url), 'utf8')
  const ast = postcss.parse(css)
  assert.ok(ast.nodes.length)
  assert.match(css, /border-inline-start/)
  assert.match(css, /max-width: 700px/)
  assert.match(css, /max-width: 380px/)
  assert.match(css, /focus-visible/)
  assert.doesNotMatch(css, /min-width: [3-9][0-9]{2}px/)
})

test('recent assessments show only the first three compact rows and link to all assessments', () => {
  const recent = Array.from({ length: 5 }, (_, i) => ({ ...assessment, id: 100 + i, title: 'Recent item ' + i }))
  const html = render({ assessments: { data: { upcoming_assessments: [], recent_assessments: recent } } })
  for (const i of [0, 1, 2]) assert.ok(html.includes('href="/app/exams/' + (100 + i) + '"'))
  for (const i of [3, 4]) assert.ok(!html.includes('Recent item ' + i))
  assert.ok(html.includes('View all assessments'))
  assert.ok(html.includes('href="/app/exams"'))
  assert.ok(html.includes('Cohort A'))
  assert.ok(html.includes('30 minutes'))
  assert.ok(!html.includes('class="wd-dates"'))
  assert.equal(recent.length, 5)
})
