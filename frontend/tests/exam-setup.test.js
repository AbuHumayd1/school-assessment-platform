import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import { setupCopy } from '../src/pages/staff/setup-copy.js'

const t = value => value
const exam = { id: 11, subject: 4, title: 'ISLAMIC QUESTIONS', candidate_access: 'specific_candidates', question_count: 1, total_marks: '1.00', status: 'draft', result_visibility: 'after_submission', result_release_mode: 'manual_release' }
const candidate = { id: 5, candidate_id: 'TEST001', name: 'Test Student', email: 'teststudent@example.com', status: 'active' }
const question = { id: 3, text: 'Approved Islamic question', question_type: 'multiple_choice', status: 'approved', options: [], media: [] }
const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
const ui = await server.ssrLoadModule('/src/pages/staff/ExamSetup.jsx')
const { ExamFields } = await server.ssrLoadModule('/src/pages/staff/ExamFormPage.jsx')
const { default: ExamAccess } = await server.ssrLoadModule('/src/pages/staff/ExamAccess.jsx')
const { useExamCopy } = await server.ssrLoadModule('/src/pages/staff/exam-ui.jsx')
const { LanguageModeProvider } = await server.ssrLoadModule('/src/context/LanguageModeContext.jsx')
await server.close()
const render = (Component, props) => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(Component, { t, ...props })))

test('configuration separates eligibility and question management, with locked subject explanation', () => {
  const markup = render(ExamFields, { values: { ...exam, title: 'Exam', subject: 4 }, options: { subjects: [{ id: 4, name: 'ISLAMIC QUIZ' }], groups: [], choices: {} }, subjectLocked: true, onChange() {} })
  assert.doesNotMatch(markup, /name="candidate_access"|name="group"|Approved question/)
  assert.match(markup, /Remove attached questions before changing the subject/)
  assert.match(markup, /name="subject"[^>]*disabled/)
})
test('attached question offers view, order, marks and safe detach actions only when editable', () => {
  const props = { row: { id: 1, order: 1, marks: '1.00', question }, editable: true }
  const markup = render(ui.AttachedQuestionEditor, props)
  for (const text of ['Approved Islamic question', 'View question', 'Order', 'Marks', 'Remove question']) assert.ok(markup.includes(text))
  assert.doesNotMatch(render(ui.AttachedQuestionEditor, { ...props, editable: false }), /Remove question|Update question/)
})
test('selectable questions distinguish attached items and preserve multi-selection', () => {
  const markup = render(ui.SelectableItems, { kind: 'questions', rows: [question, { ...question, id: 4, attached: true }], selected: [3], onSelect() {} })
  assert.match(markup, /checked/); assert.match(markup, /disabled/); assert.match(markup, /Already attached/)
  assert.equal((markup.match(/type="checkbox"/g) || []).length, 2)
})
test('candidate roster shows real identity and optional email', () => {
  const markup = render(ui.CandidateRows, { rows: [candidate, { ...candidate, id: 6, email: '' }], editable: true, specific: true })
  assert.match(markup, /TEST001/); assert.match(markup, /teststudent@example.com/)
  assert.equal((markup.match(/teststudent@example.com/g) || []).length, 1)
})
test('participated candidate has disabled removal and explanation', () => {
  const markup = render(ui.CandidateRows, { rows: [{ ...candidate, has_participated: true }], editable: true, specific: true })
  assert.match(markup, /cannot be removed/); assert.match(markup, /disabled/)
  assert.doesNotMatch(render(ui.CandidateRows, { rows: [candidate], editable: true, specific: false }), /Remove candidate/)
})
test('portal access explains entry independently of assignment strategy', () => {
  const markup = render(ExamAccess, { institutionId: 7, exam, onUpdate() {} })
  assert.match(markup, /Through their account/); assert.match(markup, /using their platform account/)
  assert.doesNotMatch(markup, /requires access-code|Specific Candidates|Assigned group/)
})
test('Access reflects persisted Quick delivery before and after configuration without a delivery chooser', () => {
  for (const configured of [false, true]) {
    const markup = render(ExamAccess, { institutionId: 7, exam: { ...exam, candidate_access: 'access_code', quick_access_configured: configured }, onUpdate() {} })
    assert.match(markup, /Exam Code \+ Candidate ID \+ PIN/)
    assert.match(markup, /Delivery method is fixed when the exam is created/)
    assert.doesNotMatch(markup, /type="radio"|Through their account/)
  }
  assert.doesNotMatch(render(ExamAccess, { institutionId: 7, exam, onUpdate() {} }), /type="radio"|Reset PIN|Generate credentials|name="delivery"/)
})
test('setup controls use localized English bilingual and Arabic RTL architecture', () => {
  const previous = globalThis.localStorage
  function View() { const { t, direction } = useExamCopy(); return React.createElement('section', { dir: direction }, t('Add Candidates'), t('No approved questions are available for this subject.')) }
  try {
    for (const mode of ['english', 'bilingual', 'arabic']) {
      globalThis.localStorage = { getItem: () => mode }
      const markup = renderToStaticMarkup(React.createElement(LanguageModeProvider, null, React.createElement(View)))
      if (mode !== 'english') assert.ok(markup.includes(setupCopy['Add Candidates']))
      if (mode !== 'arabic') assert.match(markup, /Add Candidates/)
      if (mode === 'arabic') assert.match(markup, /dir="rtl"/)
    }
  } finally { globalThis.localStorage = previous }
})
test('390px layout uses wrapping controls and logical spacing without fixed picker width', async () => {
  const css = await readFile(new URL('../src/pages/staff/exams.css', import.meta.url), 'utf8')
  assert.match(css, /@media\(max-width:767px\)/)
  assert.match(css, /exam-selectable-item[^}]*min-width:0/)
  assert.match(css, /article.exam-selectable-item[^}]*flex-wrap:wrap/)
})

async function controller(run) {
  const fixture = { states: [], calls: [], reads: [], cleanups: [], data: { count: 2, results: [candidate, { ...candidate, id: 6, candidate_id: 'TEST002', email: '' }] } }
  globalThis.__setupTest = fixture
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] }, plugins: [{ name: 'setup-controller', enforce: 'pre',
    resolveId(id) { if (id.startsWith('setup-test-')) return '\0' + id },
    load(id) {
      if (id === '\0setup-test-hooks') return `export * from 'react'; export function useRef(initial){const f=globalThis.__setupTest,i=f.cursor++;if(!(i in f.states))f.states[i]={current:initial};return f.states[i]} export function useEffect(fn){const cleanup=fn();if(cleanup)globalThis.__setupTest.cleanups.push(cleanup)} export function useState(initial){const f=globalThis.__setupTest,i=f.cursor++;if(!(i in f.states))f.states[i]=initial;return[f.states[i],next=>{f.states[i]=typeof next==='function'?next(f.states[i]):next}]} `
      if (id === '\0setup-test-read') return `export * from '/src/pages/staff/exam-ui.jsx'; export function useOwnerRead(key,load){globalThis.__setupTest.reads.push({key,load});return{data:globalThis.__setupTest.data}}`
      if (id === '\0setup-test-service') return `export * from '/src/services/assessments.js';export async function examRequest(institution,path,options,query){const f=globalThis.__setupTest;f.calls.push({institution,path,options,query});if(f.pending)await f.pending;if(f.failure)throw f.failure;return{}}`
    },
    transform(source,id) { if(id.endsWith('/src/pages/staff/ExamSetup.jsx'))return source.replace("from 'react'","from 'setup-test-hooks'").replace("from './exam-ui.jsx'","from 'setup-test-read'").replace("from '../../services/assessments.js'","from 'setup-test-service'") },
  }] })
  try {
    const module = await server.ssrLoadModule('/src/pages/staff/ExamSetup.jsx')
    function walk(node) { return node && typeof node === 'object' ? [node, ...React.Children.toArray(node.props?.children).flatMap(walk)] : [] }
    const draw = (kind='candidates', Component=module.AddItems, extra={}) => { fixture.cursor=0; return walk(Component({ institutionId:7, exam, kind, t, direction:'rtl', editable:true, onUpdate(){fixture.updated=true}, onAdded(){fixture.added=true}, onClose(){fixture.closed=true}, ...extra })) }
    await run(fixture,draw,module)
  } finally { delete globalThis.__setupTest;await server.close() }
}
for (const kind of ['questions','candidates']) test(`${kind} picker multi-select posts one atomic batch and refreshes`, async () => controller(async (fixture, draw) => {
  let nodes=draw(kind)
  let picker=nodes.find(node=>node.type?.name==='SelectableItems')
  picker.props.onSelect(5); nodes=draw(kind); picker=nodes.find(node=>node.type?.name==='SelectableItems');picker.props.onSelect(6)
  nodes=draw(kind);await nodes.find(node=>node.props?.onClick && /^(Add|Assign) selected/.test(String(node.props.children?.[0]))).props.onClick()
  assert.deepEqual(fixture.calls[0].options.body,{[kind]:[5,6]})
  assert.equal(fixture.calls[0].path,`11/${kind==='questions'?'questions/add/':'candidate-assignments/'}`)
  assert.equal(fixture.added,true);assert.equal(fixture.closed,true)
}))
test('candidate search uses TEST001 and preserves selection across pages', async () => controller(async (fixture,draw) => {
  let nodes=draw();nodes.find(node=>node.type==='input').props.onChange({target:{value:'TEST001'}})
  nodes=draw();nodes.find(node=>node.type==='form').props.onSubmit({preventDefault(){}})
  draw();await fixture.reads.at(-1).load()
  assert.equal(fixture.calls[0].query.search,'TEST001')
}))
test('empty question picker explains approval and links to bank', async () => controller(async (fixture,draw) => {
  fixture.data={count:0,results:[]}
  const nodes=draw('questions')
  assert.ok(nodes.some(node=>node.type==='p' && node.props.children==='No approved questions are available for this subject.'))
  assert.ok(nodes.some(node=>node.props?.to==='/app/questions'))
}))

test('Select all covers 151 available questions across pages and posts server selection once', async () => controller(async (fixture,draw) => {
  fixture.data={count:152,available_count:151,results:[{...question,attached:true},{...question,id:4}]}
  let nodes=draw('questions')
  nodes.find(node=>node.props?.children==='Select all').props.onClick()
  nodes=draw('questions')
  assert.equal(nodes.find(node=>node.props?.role==='status').props.children[0],151)
  assert.deepEqual(nodes.find(node=>node.type?.name==='SelectableItems').props.selected,[4])
  nodes.find(node=>node.type?.name==='ExamPagination').props.onChange(2)
  fixture.data={count:152,available_count:151,results:[{...question,id:25}]}
  nodes=draw('questions')
  assert.deepEqual(nodes.find(node=>node.type?.name==='SelectableItems').props.selected,[25])
  const button=nodes.find(node=>node.props?.onClick && node.props.children?.[0]==='Add')
  let resolve;fixture.pending=new Promise(done=>{resolve=done})
  const work=button.props.onClick();await button.props.onClick();resolve();await work
  assert.equal(fixture.calls.length,1)
  assert.deepEqual(fixture.calls[0].options.body,{select_all:true,search:'',expected_count:151})
  assert.equal(fixture.added,true)
}))

test('question search clears Select all and new selection uses the matching search', async () => controller(async (fixture,draw) => {
  fixture.data={count:151,available_count:151,results:[question]}
  let nodes=draw('questions');nodes.find(node=>node.props?.children==='Select all').props.onClick()
  nodes=draw('questions');nodes.find(node=>node.type==='input').props.onChange({target:{value:' Pilot 1 '}})
  nodes=draw('questions');nodes.find(node=>node.type==='form').props.onSubmit({preventDefault(){}})
  fixture.data={count:12,available_count:12,results:[question]}
  nodes=draw('questions');assert.equal(nodes.find(node=>node.props?.role==='status').props.children[0],0)
  nodes.find(node=>node.props?.children==='Select all').props.onClick()
  nodes=draw('questions');await nodes.find(node=>node.props?.onClick && node.props.children?.[0]==='Add').props.onClick()
  assert.deepEqual(fixture.calls[0].options.body,{select_all:true,search:'Pilot 1',expected_count:12})
}))

test('clear selection restores individual selection in both pickers', async () => controller(async (fixture,draw) => {
  fixture.data={count:151,available_count:151,results:[question]}
  let nodes=draw('questions');nodes.find(node=>node.props?.children==='Select all').props.onClick()
  nodes=draw('questions');assert.equal(nodes.find(node=>node.type==='fieldset').props.disabled,true)
  nodes.find(node=>node.props?.children==='Clear selection').props.onClick()
  nodes=draw('questions');assert.equal(nodes.find(node=>node.type==='fieldset').props.disabled,false)
  nodes.find(node=>node.type?.name==='SelectableItems').props.onSelect(3)
  nodes=draw('questions');assert.equal(nodes.find(node=>node.props?.role==='status').props.children[0],1)
  assert.ok(draw('candidates').some(node=>node.props?.children==='Select all'))
}))

test('candidate Select all covers 300 matches across pages excludes assigned and sends one request', async () => controller(async (fixture,draw) => {
  fixture.data={count:301,available_count:300,results:[{...candidate,assigned:true},{...candidate,id:6}]}
  let nodes=draw();nodes.find(node=>node.props?.children==='Select all').props.onClick()
  nodes=draw();assert.equal(nodes.find(node=>node.props?.role==='status').props.children[0],300)
  assert.deepEqual(nodes.find(node=>node.type?.name==='SelectableItems').props.selected,[6])
  nodes.find(node=>node.type?.name==='ExamPagination').props.onChange(2)
  fixture.data={count:301,available_count:300,results:[{...candidate,id:40}]}
  nodes=draw();assert.deepEqual(nodes.find(node=>node.type?.name==='SelectableItems').props.selected,[40])
  await nodes.find(node=>node.props?.onClick && node.props.children?.[0]==='Assign').props.onClick()
  assert.deepEqual(fixture.calls[0].options.body,{select_all:true,search:'',expected_count:300,status:'active'})
  assert.equal(fixture.calls.length,1);assert.equal(fixture.calls[0].path,'11/candidate-assignments/')
}))

test('candidate search resets all selection and assigns only matching active candidates', async () => controller(async (fixture,draw) => {
  fixture.data={count:300,available_count:300,results:[candidate]}
  let nodes=draw();nodes.find(node=>node.props?.children==='Select all').props.onClick()
  nodes=draw();nodes.find(node=>node.type==='input').props.onChange({target:{value:' TEST001 '}})
  nodes=draw();nodes.find(node=>node.type==='form').props.onSubmit({preventDefault(){}})
  fixture.data={count:1,available_count:1,results:[candidate]}
  nodes=draw();assert.equal(nodes.find(node=>node.props?.role==='status').props.children[0],0)
  nodes.find(node=>node.props?.children==='Select all').props.onClick()
  nodes=draw();await nodes.find(node=>node.props?.onClick && node.props.children?.[0]==='Assign').props.onClick()
  assert.deepEqual(fixture.calls[0].options.body,{select_all:true,search:'TEST001',expected_count:1,status:'active'})
}))

test('Quick delivery keeps Candidates direct assignment controls and legacy eligibility marker intact', async () => controller(async (fixture,draw,module) => {
  fixture.data={groups:[],results:[candidate],count:1}
  const nodes=draw('candidates',module.CandidatesSetup,{exam:{...exam,candidate_access:'access_code',quick_access_configured:true}})
  assert.ok(nodes.some(node=>node.props?.children==='Add Candidates'))
  assert.ok(nodes.some(node=>node.type==='option' && node.props.value==='assigned_group' && node.props.disabled))
  await nodes.find(node=>node.type==='form').props.onSubmit({preventDefault(){}})
  assert.deepEqual(fixture.calls[0].options.body,{candidate_access:'access_code',group:null})
}))

test('late picker completion cannot refresh a disposed exam workspace', async () => controller(async (fixture,draw) => {
  let nodes=draw();nodes.find(node=>node.type?.name==='SelectableItems').props.onSelect(5)
  nodes=draw();let resolve;fixture.pending=new Promise(done=>{resolve=done})
  const work=nodes.find(node=>node.props?.onClick && /^(Add|Assign) selected/.test(String(node.props.children?.[0]))).props.onClick()
  fixture.cleanups.forEach(cleanup=>cleanup());resolve();await work
  assert.equal(fixture.added,undefined);assert.equal(fixture.closed,undefined)
}))
test('picker reports genuine backend failures and keeps selection for retry', async () => controller(async (fixture,draw) => {
  let nodes=draw();nodes.find(node=>node.type?.name==='SelectableItems').props.onSelect(5);nodes=draw()
  fixture.failure={status:400,data:{detail:'Select active candidates from the current workspace.'}}
  await nodes.find(node=>node.props?.onClick && /^(Add|Assign) selected/.test(String(node.props.children?.[0]))).props.onClick()
  nodes=draw();assert.ok(nodes.some(node=>node.props?.role==='alert'));assert.equal(fixture.closed,undefined)
  assert.deepEqual(nodes.find(node=>node.type?.name==='SelectableItems').props.selected,[5])
}))
test('readiness shows missing questions candidates schedule and Quick configuration with contextual links', async () => controller(async (fixture,draw,module) => {
  fixture.data={count:0,eligible_count:0,results:[]}
  const nodes=draw('candidates',module.SetupReadiness,{exam:{...exam,question_count:0,candidate_access:'access_code',quick_access_configured:false},administrator:true})
  const strings=nodes.flatMap(node=>React.Children.toArray(node.props?.children)).filter(value=>typeof value==='string').join(' ')
  for(const text of ['No questions added','No candidates assigned','No access method configured','No schedule'])assert.ok(strings.includes(text))
  for(const section of ['questions','candidates','access'])assert.ok(nodes.some(node=>node.props?.to===`?section=${section}`))
}))
test('group readiness warns when no group is assigned and hides unauthorized Access link', async () => controller(async (fixture,draw,module) => {
  fixture.data={count:0,results:[]}
  const nodes=draw('candidates',module.SetupReadiness,{exam:{...exam,candidate_access:'assigned_group',group:null},administrator:false})
  assert.ok(nodes.some(node=>node.type==='li' && React.Children.toArray(node.props.children).includes('Assign a group before scheduling this exam.')))
  assert.ok(!nodes.some(node=>node.props?.to==='?section=access'))
}))
test('candidate strategy save uses specific assignments without a group', async () => controller(async (fixture,draw,module) => {
  fixture.data={groups:[],results:[candidate],count:1}
  const nodes=draw('candidates',module.CandidatesSetup)
  await nodes.find(node=>node.type==='form').props.onSubmit({preventDefault(){}})
  assert.deepEqual(fixture.calls[0].options.body,{candidate_access:'specific_candidates',group:null})
  assert.equal(fixture.updated,true)
}))
test('group candidate eligibility presents required group selection and avoids Add Candidates', async () => controller(async (fixture,draw,module) => {
  fixture.data={groups:[{id:9,name:'Cohort'}],count:1,results:[candidate]}
  const nodes=draw('candidates',module.CandidatesSetup,{exam:{...exam,candidate_access:'assigned_group',group:9,group_name:'Cohort'}})
  assert.ok(nodes.some(node=>node.type==='select' && node.props.required))
  assert.ok(!nodes.some(node=>node.props?.children==='Add Candidates'))
  await nodes.find(node=>node.type==='form').props.onSubmit({preventDefault(){}})
  assert.deepEqual(fixture.calls[0].options.body,{candidate_access:'assigned_group',group:9})
}))
test('question update and removal use attachment API, never delete the bank item', async () => controller(async (fixture,draw,module) => {
  fixture.data={count:1,results:[{id:10,order:1,marks:'1.00',question}]}
  let nodes=draw('questions',module.QuestionsSetup)
  let row=nodes.find(node=>node.type?.name==='AttachedQuestionEditor')
  await row.props.onSave(10,{order:1,marks:'2.00'})
  assert.equal(fixture.calls[0].path,'11/questions/10/');assert.equal(fixture.calls[0].options.method,'PATCH')
  const old=globalThis.window;globalThis.window={confirm:()=>true}
  try{nodes=draw('questions',module.QuestionsSetup);row=nodes.find(node=>node.type?.name==='AttachedQuestionEditor');await row.props.onRemove(10)}finally{globalThis.window=old}
  assert.equal(fixture.calls[1].path,'11/questions/10/');assert.equal(fixture.calls[1].options.method,'DELETE')
}))

const attached = { id: 10, order: 1, marks: '1.00', question }
const action = (nodes, label) => nodes.find(node => node.props?.children === label && node.props?.onClick)
const selectedCount = nodes => nodes.find(node => node.props?.role === 'status').props.children[0]

test('attached question selection is accessible and hidden when editing is unsafe', () => {
  const markup = render(ui.AttachedQuestionEditor, { row: attached, editable: true, selected: true, onSelect() {} })
  assert.match(markup, /type="checkbox"/); assert.match(markup, /aria-label="Select question 1"/); assert.match(markup, /checked/)
  assert.doesNotMatch(render(ui.AttachedQuestionEditor, { row: attached, editable: false, onSelect() {} }), /type="checkbox"/)
})

test('bulk removal selects individual attachments across pages, confirms this exam only, refreshes and clears', async () => controller(async (f, draw, module) => {
  f.data = { count: 151, results: [attached] }
  const view = () => draw('questions', module.QuestionsSetup, { exam: { ...exam, question_count: 151 } })
  let nodes = view(); nodes.find(n => n.type?.name === 'AttachedQuestionEditor').props.onSelect(10)
  nodes = view(); assert.equal(selectedCount(nodes), 1)
  nodes.find(n => n.type?.name === 'ExamPagination').props.onChange(2)
  f.data = { count: 151, results: [{ ...attached, id: 35, order: 26 }] }
  nodes = view(); nodes.find(n => n.type?.name === 'AttachedQuestionEditor').props.onSelect(35)
  nodes = view(); assert.equal(selectedCount(nodes), 2)
  action(nodes, 'Remove selected questions').props.onClick()
  nodes = view()
  assert.equal(f.calls.length, 0)
  assert.ok(nodes.some(n => n.type === 'p' && n.props.children === 'Remove these questions from this exam only? They will remain in the Question Bank.'))
  const modal = nodes.find(n => n.type?.name === 'Modal'); assert.equal(modal.props.dir, 'rtl')
  assert.ok(nodes.some(n => n.type === 'bdi' && n.props.children === exam.title))
  await action(nodes, 'Confirm removal').props.onClick()
  assert.deepEqual(f.calls[0], { institution: 7, path: '11/questions/remove/', options: { method: 'POST', body: { attachments: [10, 35] } }, query: undefined })
  assert.equal(f.updated, true)
  nodes = view(); assert.equal(selectedCount(nodes), 0)
  assert.ok(!nodes.some(n => n.type?.name === 'Modal'))
  assert.equal(nodes.find(n => n.type?.name === 'ExamPagination').props.page, 1)
}))

test('select all matching removes 151 across pagination with server selection and expected count', async () => controller(async (f, draw, module) => {
  f.data = { count: 151, results: [attached] }
  const view = () => draw('questions', module.QuestionsSetup)
  action(view(), 'Select all matching').props.onClick()
  let nodes = view(); assert.equal(selectedCount(nodes), 151)
  assert.equal(nodes.find(n => n.type?.name === 'AttachedQuestionEditor').props.selectionDisabled, true)
  nodes.find(n => n.type?.name === 'ExamPagination').props.onChange(7)
  f.data = { count: 151, results: [{ ...attached, id: 160, order: 151 }] }
  nodes = view(); assert.equal(selectedCount(nodes), 151)
  assert.equal(nodes.find(n => n.type?.name === 'AttachedQuestionEditor').props.selected, true)
  action(nodes, 'Remove selected questions').props.onClick()
  nodes = view(); let resolve; f.pending = new Promise(done => { resolve = done })
  const button = action(nodes, 'Confirm removal')
  const work = button.props.onClick(); await button.props.onClick(); resolve(); await work
  assert.equal(f.calls.length, 1)
  assert.deepEqual(f.calls[0].options.body, { select_all: true, search: '', expected_count: 151 })
  f.data = { count: 0, results: [] }
  nodes = draw('questions', module.QuestionsSetup, { exam: { ...exam, question_count: 0, total_marks: '0.00' } })
  assert.equal(selectedCount(nodes), 0)
  assert.ok(nodes.some(n => n.props?.children === 'No questions attached'))
  assert.ok(!action(nodes, 'Remove selected questions'))
  assert.ok(action(nodes, 'Add Questions'))
}))

test('clear selection and cancel confirmation never detach questions', async () => controller(async (f, draw, module) => {
  f.data = { count: 151, results: [attached] }
  const view = () => draw('questions', module.QuestionsSetup)
  action(view(), 'Select all matching').props.onClick()
  action(view(), 'Clear selection').props.onClick()
  assert.equal(selectedCount(view()), 0)
  view().find(n => n.type?.name === 'AttachedQuestionEditor').props.onSelect(10)
  action(view(), 'Remove selected questions').props.onClick()
  action(view(), 'Cancel').props.onClick()
  assert.equal(selectedCount(view()), 1)
  assert.ok(!view().some(n => n.type?.name === 'Modal'))
  assert.equal(f.calls.length, 0)
}))

test('attached search clears old selection and constrains select-all request', async () => controller(async (f, draw, module) => {
  f.data = { count: 151, results: [attached] }
  const view = () => draw('questions', module.QuestionsSetup, { exam: { ...exam, question_count: 151 } })
  action(view(), 'Select all matching').props.onClick()
  let nodes = view(); nodes.find(n => n.type === 'input').props.onChange({ target: { value: ' Pilot 1 ' } })
  nodes = view(); nodes.find(n => n.type === 'form').props.onSubmit({ preventDefault() {} })
  f.data = { count: 62, results: [attached] }
  nodes = view(); assert.equal(selectedCount(nodes), 0)
  await f.reads.at(-1).load()
  assert.equal(f.calls[0].path, '11/questions/remove/'); assert.equal(f.calls[0].query.search, 'Pilot 1')
  action(nodes, 'Select all matching').props.onClick()
  action(view(), 'Remove selected questions').props.onClick()
  await action(view(), 'Confirm removal').props.onClick()
  assert.deepEqual(f.calls.at(-1).options.body, { select_all: true, search: 'Pilot 1', expected_count: 62 })
}))

test('stale selection failure preserves confirmation and selection and does not claim refresh', async () => controller(async (f, draw, module) => {
  f.data = { count: 151, results: [attached] }
  const view = () => draw('questions', module.QuestionsSetup)
  action(view(), 'Select all matching').props.onClick()
  action(view(), 'Remove selected questions').props.onClick()
  f.failure = { status: 400, data: { questions: ['Attached questions changed. Refresh the list and select again.'] } }
  await action(view(), 'Confirm removal').props.onClick()
  const nodes = view()
  assert.equal(selectedCount(nodes), 151)
  assert.ok(nodes.some(n => n.props?.role === 'alert'))
  assert.ok(nodes.some(n => n.type?.name === 'Modal'))
  assert.equal(f.updated, undefined)
}))

test('late bulk removal completion cannot refresh a disposed workspace', async () => controller(async (f, draw, module) => {
  f.data = { count: 1, results: [attached] }
  const view = () => draw('questions', module.QuestionsSetup)
  view().find(n => n.type?.name === 'AttachedQuestionEditor').props.onSelect(10)
  action(view(), 'Remove selected questions').props.onClick()
  let resolve; f.pending = new Promise(done => { resolve = done })
  const work = action(view(), 'Confirm removal').props.onClick()
  f.cleanups.forEach(cleanup => cleanup()); resolve(); await work
  assert.equal(f.updated, undefined)
}))

test('unsafe question setup hides all selection and removal controls', async () => controller(async (f, draw, module) => {
  f.data = { count: 1, results: [attached] }
  const nodes = draw('questions', module.QuestionsSetup, { editable: false })
  assert.ok(!action(nodes, 'Select all matching')); assert.ok(!action(nodes, 'Remove selected questions'))
  assert.ok(!action(nodes, 'Add Questions'))
  assert.equal(nodes.find(n => n.type?.name === 'AttachedQuestionEditor').props.editable, false)
}))
