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
import { outcomesCopy, submissionLabels } from '../src/pages/staff/outcomes-copy.js'

const server = await createServer({ configLoader: 'runner', server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
const ui = await server.ssrLoadModule('/src/pages/staff/ExamOutcomes.jsx')
const { ExamSections } = await server.ssrLoadModule('/src/pages/staff/ExamDetailPage.jsx')
const { CandidateResults } = await server.ssrLoadModule('/src/pages/student/StudentResultsPage.jsx')
const { ownerOutcomes, downloadReport, ownResults } = await server.ssrLoadModule('/src/services/outcomes.js')
await server.close()
const t = text => text
const render = (component, props) => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(component, props)))
const summary = { total_candidates: 3, not_started_count: 1, in_progress_count: 1, submitted_count: 1, auto_submitted_count: 0, not_submitted_count: 0, results_count: 1, average_percentage: '75.00', highest_percentage: '75.00', lowest_percentage: '75.00', pass_rate: '100.00' }
const idle = { candidate: 1, candidate_id: 'C-1', name: 'Never Started', submission_status: 'not_started', score: null, total_marks: null, percentage: null, grade: null, passed: null, result: null }
const active = { ...idle, candidate: 2, candidate_id: 'C-2', name: 'Working Candidate', submission_status: 'in_progress', started_at: '2026-10-01T09:00:00Z' }
const submitted = { ...active, candidate: 3, candidate_id: 'C-3', name: 'Submitted Candidate', submission_status: 'submitted', submitted_at: '2026-10-01T09:30:00Z', time_used_seconds: 1800, attempt: 4, result: 5, score: '3.00', total_marks: '4.00', percentage: '75.00', passed: true, grade: 'A', publication: 'not_released' }
const props = { rows: [idle, active, submitted], t, onOpen() {}, onRelease() {}, administrator: true }

test('owner navigation includes submissions results reports and respects admin access', () => {
  const html = render(ExamSections, { section: 'results', administrator: false, t })
  for (const label of ['Submissions', 'Results', 'Reports']) assert.match(html, new RegExp(label))
  assert.doesNotMatch(html, />Access</)
  assert.match(html, /aria-current="page"/)
})
test('participation summary distinguishes each state', () => {
  const html = render(ui.OutcomeSummary, { summary, t })
  for (const label of ['Candidates', 'Not started', 'In progress', 'Submitted', 'Auto-submitted', 'Not submitted']) assert.match(html, new RegExp(label))
  assert.match(html, /<strong>3<\/strong>/)
})
test('performance summary uses server values', () => {
  const html = render(ui.OutcomeSummary, { summary, t, performance: true })
  assert.match(html, /Average %/); assert.match(html, /75.00/); assert.match(html, /100.00/)
})
test('zero-result performance contains no fake zero or NaN', () => {
  const html = render(ui.OutcomeSummary, { summary: { ...summary, average_percentage: null, highest_percentage: null, lowest_percentage: null, pass_rate: null }, t, performance: true })
  assert.doesNotMatch(html, /NaN|undefined|null/); assert.match(html, /—/)
})
test('submissions show unstarted active submitted and truthful times', () => {
  const html = render(ui.OutcomeTable, props)
  for (const text of ['Never Started', 'In progress', 'Submitted Candidate', '1800 seconds', 'View submission']) assert.match(html, new RegExp(text))
  assert.equal((html.match(/View submission/g) || []).length, 1)
})
test('result table shows stored score grade pass and blank non-submitter', () => {
  const html = render(ui.OutcomeTable, { ...props, performance: true })
  assert.match(html, /3.00/); assert.match(html, /75.00/); assert.match(html, />Pass</); assert.match(html, /View result/)
  assert.match(html, /Never Started/); assert.match(html, /—/)
})
test('release visible only for authorized admins and available unpublished result', () => {
  assert.match(render(ui.OutcomeTable, { ...props, performance: true }), /Release result/)
  assert.doesNotMatch(render(ui.OutcomeTable, { ...props, performance: true, administrator: false }), /Release result/)
  assert.doesNotMatch(render(ui.OutcomeTable, { ...props, rows: [{ ...submitted, publication: 'released' }], performance: true }), /Release result/)
})
test('failed result and auto-submission remain readable', () => {
  const html = render(ui.OutcomeTable, { ...props, rows: [{ ...submitted, passed: false, submission_status: 'auto_submitted' }], performance: true })
  assert.match(html, />Fail</); assert.match(html, /Auto-submitted/)
})
test('staff breakdown shows actual selections correct answers marks and unanswered', () => {
  const question = { order: 1, question: { text: 'Real extracted question', media: [] }, options: [{ text: 'Actual answer', selected: true, is_correct: false }, { text: 'Answer key', selected: false, is_correct: true }], marks_available: '2.00', marks_obtained: '0.00', status: 'incorrect' }
  const html = render(ui.SubmissionBreakdown, { data: { exam: 'Exam', candidate: submitted, questions: [question, { ...question, order: 2, status: 'unanswered', options: [] }] }, t })
  for (const label of ['Real extracted question', 'Candidate response', 'Correct answer', 'Incorrect', 'Unanswered', '2.00']) assert.match(html, new RegExp(label))
})
for (const format of ['csv', 'pdf', 'docx']) test(`${format} download pins workspace and asks for a binary response`, async () => {
  const blob = new Blob(['report'])
  const result = await downloadReport(7, 9, format, {}, async (path, options) => {
    assert.equal(path, `assessments/9/reports/${format}/?institution=7`)
    assert.equal(options.responseType, 'blob'); return blob
  })
  assert.equal(result, blob)
})
test('reports contain three professional download actions', () => {
  const html = render(ui.ReportButtons, { t, onDownload() {} })
  for (const format of ['CSV', 'PDF', 'Word']) assert.match(html, new RegExp(format))
})
test('invalid report format never sends a request', async () => {
  await assert.rejects(downloadReport(7, 9, 'html', {}, () => assert.fail()), /Unsupported/)
})
test('filters search pagination and sorting forwarded to selected assessment', async () => {
  await ownerOutcomes(7, 9, 'results', { search: 'Ada', status: 'passed', page: 2, sort: '-score' }, {}, async path => {
    assert.match(path, /search=Ada/); assert.match(path, /status=passed/); assert.match(path, /page=2/); assert.match(path, /sort=-score/); assert.match(path, /institution=7/)
  })
})
test('candidate API never uses staff result endpoints', async () => {
  await ownResults({}, async path => { assert.equal(path, 'results/my/'); return [] })
})
test('real candidate results render no answer keys or internal marking notes', () => {
  const html = render(CandidateResults, { t, rows: [{ id: 1, assessment_title: 'Released exam', marks_obtained: '3', total_marks: '4', percentage: '75', passed: true, grade: 'A', questions: [{ is_correct: true }], validation_note: 'PRIVATE' }] })
  assert.match(html, /Released exam/); assert.match(html, /75%/); assert.doesNotMatch(html, /is_correct|PRIVATE|Correct answer/)
})
test('candidate empty state is released-only', () => {
  assert.match(render(CandidateResults, { t, rows: [] }), /No released results yet/)
})
test('malformed candidate response and genuine server failures reach retry state', async () => {
  await assert.rejects(ownResults({}, async () => ({ detail: 'unexpected' })), /unexpected response/)
  await assert.rejects(ownResults({}, async () => [{ id: 1 }]), /unexpected response/)
  await assert.rejects(ownResults({}, async () => { throw new Error('network failure') }), /network failure/)
})
test('production candidate page has no preview data', async () => {
  const source = await readFile(new URL('../src/pages/student/StudentResultsPage.jsx', import.meta.url), 'utf8')
  assert.doesNotMatch(source, /previewResults|studentPreviewData|ResultDetails/)
})
test('operational empty partial and no-results copy exists with Arabic localization', () => {
  for (const label of ['No candidates have been added to this exam yet.', 'No submissions yet.', 'Results will appear here after submissions are marked.', 'Only available results contribute to performance statistics.']) assert.match(outcomesCopy[label], /[\u0600-\u06ff]/)
})
test('every submission state is localized', () => {
  for (const label of Object.values(submissionLabels)) assert.match(outcomesCopy[label], /[\u0600-\u06ff]/)
})
test('Arabic and bilingual tables preserve readable names and controls', () => {
  for (const translate of [text => outcomesCopy[text] || text, text => `${text} · ${outcomesCopy[text] || text}`]) {
    const html = render(ui.OutcomeTable, { ...props, t: translate, performance: true })
    assert.match(html, /الدرجة/); assert.match(html, /<bdi>Never Started<\/bdi>/); assert.match(html, /نشر النتيجة/)
  }
})
test('desktop mobile RTL use scrollable tables logical spacing and wrapping filters', async () => {
  const css = await readFile(new URL('../src/pages/staff/outcomes.css', import.meta.url), 'utf8')
  assert.match(css, /overflow-x: auto/); assert.match(css, /max-width: 600px/); assert.match(css, /flex-wrap: wrap/); assert.match(css, /margin-block/)
  assert.doesNotMatch(css, /margin-left|margin-right|padding-left|padding-right/)
  assert.match(render(ui.OutcomeTable, props), /tabindex="0"/)
})

test('report buttons invoke their corresponding format download', () => {
  const formats = []
  const element = ui.ReportButtons({ t, onDownload: format => formats.push(format), busy: false })
  element.props.children.forEach(child => child.props.onClick())
  assert.deepEqual(formats, ['csv', 'pdf', 'docx'])
})
test('report download controls disable while a request is pending', () => {
  assert.equal((render(ui.ReportButtons, { t, onDownload() {}, busy: true }).match(/disabled=""/g) || []).length, 3)
})
test('genuine zero score remains visible and failed', () => {
  const html = render(ui.OutcomeTable, { ...props, performance: true, rows: [{ ...submitted, score: '0.00', percentage: '0.00', passed: false }] })
  assert.match(html, /0.00/); assert.match(html, />Fail</)
})
test('not submitted after window remains accessible without a fabricated result', () => {
  const html = render(ui.OutcomeTable, { ...props, performance: true, rows: [{ ...idle, submission_status: 'not_submitted' }] })
  assert.match(html, /Not submitted/); assert.doesNotMatch(html, /View result|Release result|>0</)
})
test('empty roster table is valid and has no fabricated candidate rows', () => {
  const html = render(ui.OutcomeTable, { ...props, rows: [] })
  assert.match(html, /<tbody><\/tbody>/); assert.doesNotMatch(html, /Never Started|NaN/)
})
test('finalized but unmarked response remains available as submission without fake result', () => {
  const html = render(ui.OutcomeTable, { ...props, performance: true, rows: [{ ...submitted, result: null, score: null, total_marks: null, percentage: null, passed: null }] })
  assert.match(html, /View submission/); assert.doesNotMatch(html, /View result|Release result/)
})
