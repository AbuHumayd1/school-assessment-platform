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
import { outcomesCopy } from '../src/pages/staff/outcomes-copy.js'

const server = await createServer({ configLoader: 'runner', server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
const ui = await server.ssrLoadModule('/src/pages/staff/ExamOutcomes.jsx')
const centre = await server.ssrLoadModule('/src/pages/staff/OutcomesCentrePage.jsx')
const service = await server.ssrLoadModule('/src/services/outcomes.js')
const { LanguageModeProvider } = await server.ssrLoadModule('/src/context/LanguageModeContext.jsx')
const { useExamCopy } = await server.ssrLoadModule('/src/pages/staff/exam-ui.jsx')
await server.close()
const t = text => text
const render = (component, props) => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(component, props)))
const summary = { total_candidates: 3, results_count: 2, passed_count: 1, failed_count: 1, average_percentage: '50.00', pass_rate: '50.00', submitted_count: 2, not_started_count: 1, in_progress_count: 0, auto_submitted_count: 0, not_submitted_count: 0, released_count: 1, unreleased_count: 1, release_pending_count: 1, release_state: 'partially_released' }
const exam = { id: 11, institution: 7, title: 'Real client examination', subject_name: 'EEG', status: 'scheduled', summary, report_available: true, result_visibility: 'after_submission' }

for (const section of ['results', 'reports', 'submissions']) test(`${section} centre groups real assessments and links to contextual screen`, () => {
  const html = render(centre.AssessmentOutcomesList, { rows: [exam], section, t })
  assert.match(html, /Real client examination/)
  assert.match(html, new RegExp(`/app/exams/11\\?section=${section}`))
  assert.match(html, new RegExp(centre.centreCopy[section][2]))
  assert.match(html, /EEG/)
})
test('Results centre displays authoritative performance and pass fail counts', () => {
  const html = render(centre.AssessmentOutcomesList, { rows: [exam], section: 'results', t })
  assert.match(html, /50.00/); assert.match(html, /Passed: 1/); assert.match(html, /Failed: 1/)
})
for (const [state, label] of [['not_released', 'Not released'], ['partially_released', 'Partially released'], ['released', 'Released'], ['no_results', 'No results yet']]) test(`publication badge ${state}`, () => {
  assert.match(render(ui.PublicationStatus, { summary: { ...summary, release_state: state }, t }), new RegExp(label))
})
test('centre empty state has no fake assessments', () => {
  assert.match(render(centre.AssessmentOutcomesList, { rows: [], section: 'results', t }), /No assessments found/)
})
test('no results preserves absent percentage and explains disabled report actions', () => {
  const html = render(centre.AssessmentOutcomesList, { rows: [{ ...exam, report_available: false, summary: { ...summary, results_count: 0, average_percentage: null, pass_rate: null, release_state: 'no_results' } }], section: 'reports', t })
  assert.match(html, /after submissions are marked/)
  assert.equal((html.match(/disabled=""/g) || []).length, 3)
  assert.doesNotMatch(html, /NaN|undefined|50.00/)
})
test('main Submissions shows never started and actual finalized population', () => {
  const html = render(centre.AssessmentOutcomesList, { rows: [exam], section: 'submissions', t })
  assert.match(html, /Not started/); assert.match(html, /In progress/); assert.match(html, /2 \/ 3 Submitted/)
})
test('centre report action callbacks reuse csv pdf docx formats and selected exam', () => {
  const calls = []
  const cards = centre.AssessmentOutcomesList({ rows: [exam], section: 'reports', t, onDownload: (selected, format) => calls.push([selected.id, format]) })
  const article = cards.props.children[0]
  const controls = article.props.children.at(-1).props.children[1]
  ui.ReportButtons(controls.props).props.children.forEach(button => button.props.onClick())
  assert.deepEqual(calls, [[11, 'csv'], [11, 'pdf'], [11, 'docx']])
})
for (const section of ['results', 'reports', 'submissions']) test(`${section} index pins selected workspace, search and pagination`, async () => {
  const expected = { count: 1, results: [exam] }
  const actual = await service.outcomesIndex(7, section, { search: 'EEG', page: 2 }, {}, async path => {
    assert.equal(path, `assessments/outcomes/${section}/?search=EEG&page=2&institution=7`)
    return expected
  })
  assert.equal(actual, expected)
})
test('index rejects unexpected and foreign workspace data', async () => {
  for (const data of [null, [], { count: 1, results: [{ ...exam, institution: 8 }] }]) await assert.rejects(service.outcomesIndex(7, 'results', {}, {}, async () => data), /Workspace context/)
})
test('bulk publication uses exam endpoint while individual release remains distinct', async () => {
  const calls = []
  const request = async (path, options) => { calls.push(path); assert.equal(options.method, 'POST'); assert.deepEqual(options.body, {}); return { released_count: 1 } }
  await service.releaseOutcomes(7, 11, null, request)
  await service.releaseOutcomes(7, 11, 19, request)
  assert.deepEqual(calls, ['assessments/11/results/release/?institution=7', 'assessments/11/results/19/release/?institution=7'])
})
test('Results header makes bulk action primary for permitted admin', () => {
  const html = render(ui.ResultsPublication, { summary, t, administrator: true, allowed: true })
  assert.match(html, /Candidate results/); assert.match(html, /Partially released/); assert.match(html, /Release Remaining Results/)
})
test('bulk action hidden for nonadmin forbidden policy and fully published result population', () => {
  for (const props of [{ administrator: false, allowed: true }, { administrator: true, allowed: false }, { administrator: true, allowed: true, summary: { ...summary, released_count: 2, unreleased_count: 0, release_pending_count: 0, release_state: 'released' } }]) {
    const html = render(ui.ResultsPublication, { summary, t, ...props })
    assert.doesNotMatch(html, />Release Results</)
  }
})
test('bulk dialog explains candidate visibility and has explicit cancel', () => {
  const html = render(ui.ReleaseConfirmation, { release: { bulk: true, count: 39 }, t })
  assert.match(html, /39 candidate results/); assert.match(html, /visibility settings/); assert.match(html, /portal access/); assert.match(html, /Cancel/)
})
test('cancel callback does not publish and confirm invokes publication', () => {
  const events = []
  const dialog = ui.ReleaseConfirmation({ release: { bulk: true, count: 39 }, t, onCancel: () => events.push('cancel'), onPublish: () => events.push('publish') })
  const actions = dialog.props.children.at(-1).props.children
  actions[0].props.onClick(); assert.deepEqual(events, ['cancel'])
  actions[1].props.onClick(); assert.deepEqual(events, ['cancel', 'publish'])
})
test('pending publication disables cancel and confirm and failure stays visible', () => {
  const html = render(ui.ReleaseConfirmation, { release: { bulk: true, count: 2 }, t, busy: true, error: 'Release failed' })
  assert.equal((html.match(/disabled=""/g) || []).length, 2)
  assert.match(html, /role="alert">Release failed/)
})
test('new presentation copy supports English bilingual and Arabic through existing provider', () => {
  const previous = globalThis.localStorage
  function View() { const { t, direction } = useExamCopy(); return React.createElement('section', { dir: direction }, t('Release Results'), t('Review and manage assessment results across your institution.')) }
  try {
    for (const mode of ['english', 'bilingual', 'arabic']) {
      globalThis.localStorage = { getItem: () => mode }
      const html = renderToStaticMarkup(React.createElement(LanguageModeProvider, null, React.createElement(View)))
      assert.match(html, mode === 'arabic' ? /dir="rtl"/ : /dir="ltr"/)
      if (mode !== 'english') assert.match(html, /نشر النتائج/)
      if (mode !== 'arabic') assert.match(html, /Release Results/)
    }
  } finally { globalThis.localStorage = previous }
})
test('every new centre and publication message has Arabic copy', () => {
  for (const message of [...Object.values(centre.centreCopy).flat(), 'Search assessments', 'Partially released', 'Release Results', 'Release results?', 'Results released successfully.', 'Preparing download…']) assert.match(outcomesCopy[message], /[\u0600-\u06ff]/)
})
test('centre cards and publication controls wrap for 390px with logical RTL spacing', async () => {
  const css = await readFile(new URL('../src/pages/staff/outcomes.css', import.meta.url), 'utf8')
  assert.match(css, /outcome-publication-header.*flex-wrap: wrap/)
  assert.match(css, /outcome-assessments article.*min-width: 0.*overflow-wrap: anywhere/)
  assert.match(css, /max-width: 600px/)
  assert.doesNotMatch(css, /margin-left|margin-right|padding-left|padding-right/)
})

// Native tests drive the actual controller callbacks. Only effect/read hooks and
// transport are fixtures; the page, event handlers and confirmation stay real.
async function controllerTest(run) {
  const fixture = { states: [], cursor: 0, refresh: 0, calls: [], data: { summary, results: [], count: 0, delivery_supported: true }, request: async () => ({ released_count: 1 }) }
  globalThis.__outcomeController = fixture
  const server = await createServer({ configLoader: 'runner', server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] }, plugins: [{
    name: 'outcome-native-controller', enforce: 'pre',
    resolveId(source) { if (source === 'outcome-test-hooks') return '\0outcome-hooks'; if (source === 'outcome-test-reads') return '\0outcome-reads'; if (source === 'outcome-test-transport') return '\0outcome-transport' },
    load(id) {
      if (id === '\0outcome-hooks') return `export function useState(initial) { const f=globalThis.__outcomeController; const i=f.cursor++; if (!(i in f.states)) f.states[i]=initial; return [f.states[i], value=>{ f.states[i]=value }] } export function useRef(value) { return {current:value} } export function useEffect() {}`
      if (id === '\0outcome-reads') return `export * from '/src/pages/staff/exam-ui.jsx'; export function useOwnerRead(key) {const f=globalThis.__outcomeController; return {data:key.includes(':submission:')?null:f.data,retry(){f.refresh++}}}`
      if (id === '\0outcome-transport') return `export * from '/src/services/outcomes.js'; export function releaseOutcomes(institution,exam,result) {const f=globalThis.__outcomeController;f.calls.push([institution,exam,result]);return f.request()}`
    },
    transform(source, id) { if (id.endsWith('/src/pages/staff/ExamOutcomes.jsx')) return source.replace("from 'react'", "from 'outcome-test-hooks'").replace("from './exam-ui.jsx'", "from 'outcome-test-reads'").replace("from '../../services/outcomes.js'", "from 'outcome-test-transport'") },
  }] })
  try {
    const { default: Page } = await server.ssrLoadModule('/src/pages/staff/ExamOutcomes.jsx')
    function elements(node) { if (!node || typeof node !== 'object') return []; return [node, ...React.Children.toArray(node.props?.children).flatMap(elements)] }
    const draw = () => { fixture.cursor = 0; return elements(Page({ institutionId: 7, exam, section: 'results', administrator: true, t, direction: 'rtl' })) }
    const get = (nodes, name) => nodes.find(node => node.type?.name === name)
    await run(fixture, draw, get)
  } finally { delete globalThis.__outcomeController; await server.close() }
}
test('actual bulk controller opens confirmation cancel sends no request and success refreshes status', async () => controllerTest(async (fixture, draw, get) => {
  get(draw(), 'ResultsPublication').props.onRelease({ bulk: true, count: 1 })
  get(draw(), 'ReleaseConfirmation').props.onCancel()
  assert.equal(fixture.calls.length, 0)
  get(draw(), 'ResultsPublication').props.onRelease({ bulk: true, count: 1 })
  await get(draw(), 'ReleaseConfirmation').props.onPublish()
  assert.deepEqual(fixture.calls, [[7, 11, null]])
  assert.equal(fixture.refresh, 2)
  fixture.data = { ...fixture.data, summary: { ...summary, release_state: 'released', released_count: 2, unreleased_count: 0, release_pending_count: 0 } }
  const nodes = draw()
  assert.equal(get(nodes, 'ReleaseConfirmation').props.release, null)
  const html = render(ui.ResultsPublication, get(nodes, 'ResultsPublication').props)
  assert.match(html, /Released/); assert.doesNotMatch(html, />Release Results</)
  assert.ok(nodes.some(node => node.props?.role === 'status' && node.props.children === 'Results released successfully.'))
}))
test('actual publication failure leaves confirmation open and does not refresh', async () => controllerTest(async (fixture, draw, get) => {
  fixture.request = async () => { throw new Error('Network unavailable') }
  get(draw(), 'ResultsPublication').props.onRelease({ bulk: true, count: 1 })
  await get(draw(), 'ReleaseConfirmation').props.onPublish()
  const dialog = get(draw(), 'ReleaseConfirmation')
  assert.ok(dialog.props.release.bulk)
  assert.match(dialog.props.error, /could not complete/)
  assert.equal(dialog.props.busy, false); assert.equal(fixture.refresh, 0)
}))
test('actual individual publication sends result id and refreshes rows and detail', async () => controllerTest(async (fixture, draw, get) => {
  fixture.data.results = [{ candidate: 1, result: 19, name: 'Candidate', publication: 'not_released' }]
  get(draw(), 'OutcomeTable').props.onRelease(fixture.data.results[0])
  await get(draw(), 'ReleaseConfirmation').props.onPublish()
  assert.deepEqual(fixture.calls, [[7, 11, 19]]); assert.equal(fixture.refresh, 2)
}))
