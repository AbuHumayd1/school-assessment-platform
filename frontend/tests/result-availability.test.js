import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import { resultAvailability, resultAvailabilityChoices, resultAvailabilityExplanation, canReleaseResults, canEditResultSettings } from '../src/services/resultAvailability.js'
import { outcomesCopy } from '../src/pages/staff/outcomes-copy.js'

const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
const { ExamFields } = await server.ssrLoadModule('/src/pages/staff/ExamFormPage.jsx')
const { ResultsPublication, OutcomeTable } = await server.ssrLoadModule('/src/pages/staff/ExamOutcomes.jsx')
const { ExamOverview } = await server.ssrLoadModule('/src/pages/staff/ExamDetailPage.jsx')
await server.close()
const t = value => value
const render = (component, props) => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(component, props)))
const values = { id: 11, institution: 7, status: 'draft', has_attempt_history: false, title: 'Exam', description: '', assessment_type: 'test', subject: 4, group: '', duration_minutes: 30, pass_mark: '0.00', start_at: '', end_at: '', attempt_limit: 1, resume_allowed: true, review_allowed: false, randomize_questions: false, randomize_options: false, security_level: 'standard', candidate_access: 'assigned_group', result_visibility: 'after_submission', result_release_mode: 'manual_release' }
const summary = { results_count: 1, released_count: 0, unreleased_count: 1, release_pending_count: 1, release_state: 'not_released' }
const options = { subjects: [{ id: 4, name: 'Maths' }], groups: [], choices: {} }
const props = { summary, t, administrator: true, exam: values, allowed: true }

test('manual availability uses existing visibility and manual release fields', () => {
  assert.equal(resultAvailability(values), 'manual')
  const manual = resultAvailabilityChoices.find(choice => choice.value === 'manual')
  assert.equal(manual.result_visibility, 'after_submission'); assert.equal(manual.result_release_mode, 'manual_release')
})
test('legacy approval-required combination displays manual release without changing stored values', () => {
  const exam = { ...values, result_release_mode: 'approval_required' }
  assert.equal(resultAvailability(exam), 'manual')
  assert.equal(exam.result_release_mode, 'approval_required')
})
test('configuration contains one discoverable product setting with four supported choices', () => {
  const html = render(ExamFields, { values, options, t, onChange() {} })
  for (const label of ['Result availability', 'When should candidates see their results?', 'When I release them', 'After they submit', 'After the exam closes', 'Keep results hidden']) assert.match(html, new RegExp(label.replace('?', '\\?')))
  assert.match(html, /id="result-availability"/)
  assert.match(html, /value="manual" selected=""/)
  assert.doesNotMatch(html, /name="result_visibility"|name="result_release_mode"/)
})
test('changing the real selector updates both existing backend fields', () => {
  const changes = []
  const form = ExamFields({ values, options, t, onChange: (key, value) => changes.push([key, value]) })
  const setting = form.props.children[1].find(node => node?.props?.id === 'result-availability')
  setting.props.children[0].props.children[1].props.onChange({ target: { value: 'manual' } })
  assert.deepEqual(changes, [['result_visibility', 'after_submission'], ['result_release_mode', 'manual_release']])
})
for (const [value, label, visibility, mode] of [['after_submit', 'After they submit', 'after_submission', 'immediate'], ['after_close', 'After the exam closes', 'scheduled_release', 'manual_release'], ['hidden', 'Keep results hidden', 'hidden', 'approval_required']]) test(`${label} maps to the existing backend policy`, () => {
  const choice = resultAvailabilityChoices.find(row => row.value === value)
  assert.equal(choice.result_visibility, visibility); assert.equal(choice.result_release_mode, mode)
  assert.equal(resultAvailability({ result_visibility: visibility, result_release_mode: mode }), value)
})
test('manual Results shows release action and candidate publication guidance', () => {
  const html = render(ResultsPublication, props)
  assert.match(html, />Release Results</); assert.match(html, /only after you release them/)
})
test('partial publication clearly offers Release Remaining Results', () => {
  assert.match(render(ResultsPublication, { ...props, summary: { ...summary, results_count: 2, released_count: 1, release_state: 'partially_released' } }), /Release Remaining Results/)
})
test('fully published results have no duplicate release action', () => {
  const html = render(ResultsPublication, { ...props, summary: { ...summary, release_state: 'released', unreleased_count: 0, release_pending_count: 0 } })
  assert.doesNotMatch(html, />Release Results<|>Release Remaining Results</)
})
test('hidden draft explains active policy and links to the editable configuration anchor', () => {
  const exam = { ...values, result_visibility: 'hidden' }
  const html = render(ResultsPublication, { ...props, exam, allowed: canReleaseResults(exam) })
  assert.match(html, /kept hidden from candidates/); assert.match(html, /Change Result Settings/)
  assert.match(html, /href="\/app\/exams\/11\/edit#result-availability"/)
  assert.doesNotMatch(html, />Release Results</)
})
test('future after-close policy explains both close and publication gates', () => {
  const exam = { ...values, result_visibility: 'scheduled_release', end_at: '2099-01-01T00:00:00Z' }
  assert.equal(canReleaseResults(exam), false)
  const html = render(ResultsPublication, { ...props, exam, allowed: false })
  assert.match(html, /after the exam closes and you release them/); assert.match(html, /Change Result Settings/)
  assert.doesNotMatch(html, />Release Results</)
})
test('after-close becomes releasable only at configured end time', () => {
  const exam = { ...values, result_visibility: 'scheduled_release', end_at: '2026-10-01T12:00:00Z' }
  assert.equal(canReleaseResults(exam, Date.parse('2026-10-01T11:59:59Z')), false)
  assert.equal(canReleaseResults(exam, Date.parse(exam.end_at)), true)
  assert.equal(canReleaseResults({ ...exam, end_at: null }), false)
})
test('legacy immediate-after-close copy does not promise background publication', () => {
  assert.match(resultAvailabilityExplanation({ ...values, result_visibility: 'scheduled_release', result_release_mode: 'immediate' }), /marked before closing still need to be released/)
})
test('after-submit copy accurately states that submitted attempts need marking', () => {
  assert.match(resultAvailabilityExplanation({ ...values, result_release_mode: 'immediate' }), /submitted attempts are marked/)
})
test('started exam truthfully explains locked policy and does not expose edit shortcut', () => {
  const html = render(ResultsPublication, { ...props, exam: { ...values, result_visibility: 'hidden', has_attempt_history: true, status: 'scheduled' }, allowed: false })
  assert.match(html, /cannot be changed after an exam attempt has started/)
  assert.match(html, /new draft/)
  assert.doesNotMatch(html, /Change Result Settings|\/edit#result-availability/)
})
test('non-draft without attempts directs admin to Overview without bypassing workflow', () => {
  const html = render(ResultsPublication, { ...props, exam: { ...values, result_visibility: 'hidden', status: 'approved' }, allowed: false })
  assert.match(html, /only be changed on a draft/); assert.match(html, /section=overview/)
  assert.doesNotMatch(html, /Change Result Settings/)
})
test('non-admin sees policy but no configuration or publication action', () => {
  const html = render(ResultsPublication, { ...props, administrator: false })
  assert.match(html, /only after you release them/)
  assert.doesNotMatch(html, /Change Result Settings|>Release Results</)
  assert.equal(canEditResultSettings(values, false), false)
})
test('individual release uses the same policy gate as bulk release', () => {
  const row = { candidate: 1, name: 'Candidate', candidate_id: 'C1', result: 5, publication: 'not_released', submission_status: 'submitted' }
  assert.match(render(OutcomeTable, { rows: [row], t, performance: true, administrator: canReleaseResults(values) }), /Release result/)
  assert.doesNotMatch(render(OutcomeTable, { rows: [row], t, performance: true, administrator: canReleaseResults({ ...values, result_visibility: 'hidden' }) }), /Release result/)
})
test('Overview presents the same product availability label', () => {
  assert.match(render(ExamOverview, { exam: values, t }), /Result availability.*When I release them/)
})
test('new setting policy guidance and remaining release wording have Arabic localization', () => {
  for (const text of ['Result availability', 'When should candidates see their results?', ...resultAvailabilityChoices.map(row => row.label), 'Change Result Settings', 'Release Remaining Results', ...['hidden', 'after_submission', 'scheduled_release'].map(result_visibility => resultAvailabilityExplanation({ ...values, result_visibility }))]) assert.match(outcomesCopy[text], /[\u0600-\u06ff]/)
  const html = render(ResultsPublication, { ...props, t: text => `${text} · ${outcomesCopy[text] || text}` })
  assert.match(html, /نشر النتائج/); assert.match(html, /تغيير إعدادات النتائج/)
})

// Drive the actual edit form: only read/effect hooks and transport are fixtures.
async function editController(run) {
  const fixture = { states: [], effects: [], cursor: 0, pending: [], calls: [], navigations: [], data: { options, exam: { ...values, result_visibility: 'hidden', result_release_mode: 'approval_required' } } }
  globalThis.__visibilityEdit = fixture
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] }, plugins: [{
    name: 'visibility-edit-native', enforce: 'pre',
    resolveId(source) { if (source.startsWith('visibility-test-')) return `\0${source}` },
    load(id) {
      if (id === '\0visibility-test-hooks') return `export function useState(initial){const f=globalThis.__visibilityEdit,i=f.cursor++;if(!(i in f.states))f.states[i]=initial;return[f.states[i],next=>{f.states[i]=typeof next==='function'?next(f.states[i]):next}]} export function useRef(value){return{current:value}} export function useEffect(fn,deps){const f=globalThis.__visibilityEdit,i=f.effectCursor++;if(!f.effects[i]||deps.some((d,j)=>d!==f.effects[i][j])){f.pending.push(fn);f.effects[i]=deps}}`
      if (id === '\0visibility-test-router') return `export * from 'react-router-dom';export function useLocation(){return{hash:''}}export function useNavigate(){return(...args)=>globalThis.__visibilityEdit.navigations.push(args)}`
      if (id === '\0visibility-test-read') return `export * from '/src/pages/staff/exam-ui.jsx';export function useExamCopy(){return{t:value=>value,direction:'rtl'}}export function useOwnerRead(){return{data:globalThis.__visibilityEdit.data}}`
      if (id === '\0visibility-test-service') return `export * from '/src/services/assessments.js';export async function examRequest(institution,path,options){globalThis.__visibilityEdit.calls.push({institution,path,options});return{id:11}}`
    },
    transform(source, id) { if (id.endsWith('/src/pages/staff/ExamFormPage.jsx')) return source.replace("from 'react'", "from 'visibility-test-hooks'").replace("from 'react-router-dom'", "from 'visibility-test-router'").replace("from './exam-ui.jsx'", "from 'visibility-test-read'").replace("from '../../services/assessments.js'", "from 'visibility-test-service'") + '\nexport { Form as TestForm };' },
  }] })
  try {
    const module = await server.ssrLoadModule('/src/pages/staff/ExamFormPage.jsx')
    function walk(node) { if (!node || typeof node !== 'object') return []; return [node, ...React.Children.toArray(node.props?.children).flatMap(walk)] }
    const draw = () => { fixture.cursor = 0; fixture.effectCursor = 0; const nodes = walk(module.TestForm({ institutionId: 7, id: '11' })); fixture.pending.splice(0).forEach(fn => fn()); return nodes }
    draw()
    await run(fixture, draw, module.ExamFields)
  } finally { delete globalThis.__visibilityEdit; await server.close() }
}
test('actual edit controller loads existing fields and saves the selected manual combination', async () => editController(async (fixture, draw, Fields) => {
  let nodes = draw()
  const fields = nodes.find(node => node.type?.name === 'ExamFields')
  assert.equal(fields.props.values.result_visibility, 'hidden')
  assert.equal(fields.props.values.result_release_mode, 'approval_required')
  const element = Fields(fields.props).props.children[1].find(node => node?.props?.id === 'result-availability')
  element.props.children[0].props.children[1].props.onChange({ target: { value: 'manual' } })
  nodes = draw()
  await nodes.find(node => node.type === 'form').props.onSubmit({ preventDefault() {} })
  assert.equal(fixture.calls.length, 1)
  assert.equal(fixture.calls[0].path, '11/'); assert.equal(fixture.calls[0].options.method, 'PATCH')
  assert.equal(fixture.calls[0].options.body.result_visibility, 'after_submission')
  assert.equal(fixture.calls[0].options.body.result_release_mode, 'manual_release')
  assert.ok(!('result_availability' in fixture.calls[0].options.body))
  assert.equal(fixture.navigations[0][0], '/app/exams/11')
}))
test('editing an existing legacy scheduled combination without changing availability preserves both fields', async () => editController(async (fixture, draw) => {
  fixture.data = { ...fixture.data, exam: { ...values, result_visibility: 'scheduled_release', result_release_mode: 'immediate' } }
  draw()
  const nodes = draw()
  await nodes.find(node => node.type === 'form').props.onSubmit({ preventDefault() {} })
  assert.equal(fixture.calls[0].options.body.result_visibility, 'scheduled_release')
  assert.equal(fixture.calls[0].options.body.result_release_mode, 'immediate')
}))
