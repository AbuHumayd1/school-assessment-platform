import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer as createViteServer } from 'vite'
// These tests render server-side only; skip the client dependency pre-bundle.
const createServer = options => createViteServer({ ...options, plugins: [...(options.plugins || []), {
  name: 'ssr-only-test-server',
  configResolved(config) { config.optimizeDeps.include = []; config.optimizeDeps.noDiscovery = true },
}] })
import { readFile } from 'node:fs/promises'
import postcss from 'postcss'
const server = await createServer({ configLoader: 'runner', server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
const { SubjectCollection, SubjectCreateForm } = await server.ssrLoadModule('/src/pages/staff/SubjectsPage.jsx')
const { ExamList } = await server.ssrLoadModule('/src/pages/staff/ExamsPage.jsx')
const { AssessmentOutcomesList } = await server.ssrLoadModule('/src/pages/staff/OutcomesCentrePage.jsx')
test.after(() => server.close())
const t = text => text
const render = (component, props) => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(component, props)))
const subjects = [{ id: 5, name: 'Mathematics', code: 'MAT', description: 'Learning area' }, { id: 9, name: 'Arabic', code: 'ARA', is_active: false }]
test('subject cards show only existing metadata with stable accents after reorder', () => {
  const html = render(SubjectCollection, { subjects, label: t })
  for (const text of ['Mathematics', 'MAT', 'Arabic', 'ARA', 'Learning area', 'Inactive']) assert.ok(html.includes(text))
  assert.ok(!html.includes('<ul'))
  const reversed = render(SubjectCollection, { subjects: [...subjects].reverse(), label: t })
  const classes = markup => [...markup.matchAll(/<article class="([^"]+)"/g)].map(match => match[1])
  assert.deepEqual(classes(html), classes(reversed).reverse())
  assert.ok(!html.includes('questions'))
})
test('subject form retains validation, safe error display and busy state', () => {
  const html = render(SubjectCreateForm, { fields: { name: 'Maths', code: 'MAT' }, label: t, busy: true, error: 'Subject already exists', setFields() {}, create() {}, close() {} })
  assert.ok(html.toLowerCase().includes('maxlength="160"'))
  assert.ok(html.toLowerCase().includes('maxlength="64"'))
  assert.ok(html.includes('required=""'))
  assert.ok(html.includes('disabled=""'))
  assert.ok(html.includes('role="alert"'))
  assert.ok(html.includes('Subject already exists'))
})
test('exam table keeps all supported lifecycle values and existing detail links', () => {
  const rows = ['draft', 'review', 'approved', 'scheduled', 'archived'].map((status, id) => ({ id, title: 'Assessment ' + id, status, subject_name: 'Maths', question_count: 3, duration_minutes: 30, candidate_access: 'assigned_group' }))
  const html = render(ExamList, { rows, t })
  for (const row of rows) {
    assert.ok(html.includes('status-pill--' + row.status))
    assert.ok(html.includes('href="/app/exams/' + row.id + '"'))
  }
  assert.ok(html.includes('tabindex="0"'))
  assert.ok(html.includes('role="region"'))
  assert.ok(html.includes('<table'))
})
test('submissions preserve real counts, six semantic metrics and context navigation', () => {
  const summary = { total_candidates: 10, not_started_count: 2, in_progress_count: 1, submitted_count: 6, auto_submitted_count: 1, not_submitted_count: 0 }
  const html = render(AssessmentOutcomesList, { rows: [{ id: 7, title: 'Real assessment', subject_name: 'Maths', status: 'scheduled', summary }], section: 'submissions', t })
  for (const family of ['indigo', 'neutral', 'blue', 'emerald', 'amber', 'rose']) assert.ok(html.includes('metric-card accent--' + family))
  assert.ok(html.includes('6 / 10 Submitted'))
  assert.ok(html.includes('href="/app/exams/7?section=submissions"'))
  assert.ok(html.includes('View Submissions'))
  assert.ok(!html.includes('NaN'))
})
test('shared accents have dark-mode counterparts and feature styles parse', async () => {
  const theme = await readFile(new URL('../src/styles/theme.css', import.meta.url), 'utf8')
  for (const family of ['indigo', 'violet', 'blue', 'teal', 'emerald', 'amber', 'rose']) assert.equal(theme.split('--accent-' + family + '-surface:').length, 3)
  for (const file of ['styles/components.css', 'styles/theme.css', 'pages/staff/subjects.css', 'pages/staff/exams.css', 'pages/staff/outcomes.css']) postcss.parse(await readFile(new URL('../src/' + file, import.meta.url), 'utf8'))
  const css = await readFile(new URL('../src/styles/components.css', import.meta.url), 'utf8')
  assert.ok(css.includes('prefers-reduced-motion'))
  assert.ok(css.includes('inset-inline-start'))
})

async function subjectController(run) {
  const fixture = { values: [], cursor: 0, cleanups: [], calls: [], role: 'institution_admin', mode: 'institution_workspace', rows: subjects.map(subject => ({ ...subject, institution: 7 })) }
  globalThis.__subjectPolish = fixture
  const mock = await createServer({ configLoader: 'runner', server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] }, plugins: [{ name: 'subject-controller', enforce: 'pre',
    transform(source, id) { if (id.endsWith('/SubjectsPage.jsx')) return source.replace("from 'react'", "from 'subject-polish-hooks'") },
    resolveId(source, importer) {
      if (source === 'subject-polish-hooks') return '\0subject-hooks'
      if (source.endsWith('/context/WorkspaceContext.jsx')) return '\0subject-workspace'
      if (source.endsWith('/context/LanguageModeContext.jsx')) return '\0subject-language'
      if (source.endsWith('/services/api.js')) return '\0subject-api'
    },
    load(id) {
      if (id === '\0subject-hooks') return "export function useState(initial){const f=globalThis.__subjectPolish;const i=f.cursor++;if(!(i in f.values))f.values[i]=initial;return [f.values[i],v=>{f.values[i]=typeof v==='function'?v(f.values[i]):v}]} export function useRef(initial){const f=globalThis.__subjectPolish;const i=f.cursor++;if(!(i in f.values))f.values[i]={current:initial};return f.values[i]} export function useEffect(effect){const f=globalThis.__subjectPolish;const i=f.cursor++;if(!(i in f.values)){f.values[i]=true;f.cleanups.push(effect())}}"
      if (id === '\0subject-workspace') return 'export function useWorkspace(){const f=globalThis.__subjectPolish;return {currentRole:f.role,currentWorkspace:{institution:{id:7,workspace_mode:f.mode}}}}'
      if (id === '\0subject-language') return "export function useLanguageMode(){return {label:s=>s,direction:'ltr'}}"
      if (id === '\0subject-api') return "export async function staffApiFetch(path,options){const f=globalThis.__subjectPolish;f.calls.push({path,options});if(options.method==='POST'){if(f.failure)throw f.failure;return {id:12,institution:7,...options.body}}return f.rows}"
    },
  }] })
  try {
    const module = await mock.ssrLoadModule('/src/pages/staff/SubjectsPage.jsx')
    const draw = () => { fixture.cursor=0;const page=module.default();const nodes=[];const visit=node=>{if(!node||typeof node!=='object')return;if(Array.isArray(node)){node.forEach(visit);return}nodes.push(node);visit(node.props?.children)};visit(page.type(page.props));return nodes }
    await run(fixture, draw)
  } finally {fixture.cleanups.forEach(fn=>fn?.());delete globalThis.__subjectPolish;await mock.close()}
}
const flush = () => new Promise(resolve => setImmediate(resolve))
test('subject modal opens on demand, preserves rejection fields, and appends successful tenant-scoped creation', async () => subjectController(async (f, draw) => {
  let nodes=draw();assert.ok(!nodes.some(n=>n.type?.name==='Modal'));await flush()
  nodes=draw();nodes.find(n=>n.props?.['aria-haspopup']==='dialog').props.onClick()
  nodes=draw();let form=nodes.find(n=>n.type?.name==='SubjectCreateForm');form.props.setFields({name:'Science',code:'SCI'})
  f.failure={status:400,data:{name:['Existing subject']}}
  form=draw().find(n=>n.type?.name==='SubjectCreateForm');await form.props.create({preventDefault(){}})
  form=draw().find(n=>n.type?.name==='SubjectCreateForm');assert.equal(form.props.fields.name,'Science');assert.equal(form.props.error,'Existing subject')
  delete f.failure;await form.props.create({preventDefault(){}})
  nodes=draw();assert.ok(!nodes.some(n=>n.type?.name==='Modal'))
  assert.equal(nodes.find(n=>n.type?.name==='SubjectCollection').props.subjects.at(-1).code,'SCI')
  const call=f.calls.at(-1);assert.equal(call.path,'subjects/?institution=7');assert.deepEqual(call.options.body,{institution:7,name:'Science',code:'SCI'})
}))
test('subject creation action follows workspace capabilities', async () => subjectController(async (f, draw) => {
  draw();await flush()
  for(const role of ['institution_admin','teacher','examiner']) {
    f.role=role;const nodes=draw();assert.ok(nodes.some(n=>n.props?.['aria-haspopup']==='dialog'))
    const links=nodes.filter(n=>['/app/exams/new','/app/questions'].includes(n.props?.to))
    assert.deepEqual(links.map(n=>n.props.to),['/app/exams/new','/app/questions'])
    for(const link of links) {assert.equal(link.props.variant,'outline');assert.equal(link.props.size,'small')}
  }
  f.role='student';assert.ok(!draw().some(n=>n.props?.['aria-haspopup']==='dialog' || n.props?.className==='subject-related'))
  f.role='institution_admin';f.mode='managed_exam';assert.ok(!draw().some(n=>n.props?.['aria-haspopup']==='dialog' || n.props?.className==='subject-related'))
}))
