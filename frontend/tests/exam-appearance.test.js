import test from 'node:test'
import assert from 'node:assert/strict'
import { createServer } from 'vite'
import { applyTheme } from '../src/utils/theme.js'

// Exercise the actual runner's hook identities/dependencies without running any
// attempt effects or network writes. The fixture starts with an active attempt.
test('changing visual theme and interface copy preserves active runner state and schedules no attempt effects', async () => {
  const question = { id: 9, order: 1, question: { text: 'Authored English question', question_type: 'multiple_choice' }, options: [{ id: 44, text: 'Authored option' }] }
  const answers = { 0: [44] }, order = [question], marked = new Set([0])
  const f = { cursor: 0, cells: [], effects: [], languageMode: 'english' }
  Object.assign(f.cells, { 1: { id: 7, status: 'in_progress', assessment_title: 'ACTIVUS fixture', attempt_number: 1 }, 2: order, 3: 0, 4: question, 5: answers, 6: marked, 7: 123, 10: false })
  globalThis.__appearanceRunner = f
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] }, plugins: [{
    name: 'exam-appearance-hooks', enforce: 'pre',
    resolveId(id) { if (id.startsWith('appearance-fixture-')) return '\0' + id },
    load(id) {
      if (id === '\0appearance-fixture-language') return 'export function useOptionalLanguageMode() { return globalThis.__appearanceRunner }'
      if (id === '\0appearance-fixture-router') return "export { Link } from 'react-router-dom'; export function useParams() { return { attemptId: '7' } }"
      if (id === '\0appearance-fixture-react') return `export * from 'react';
        export function useState(initial) { const f=globalThis.__appearanceRunner,i=f.cursor++;if(!(i in f.cells))f.cells[i]=typeof initial==='function'?initial():initial;return [f.cells[i],value=>f.cells[i]=typeof value==='function'?value(f.cells[i]):value] }
        export function useRef(initial) { const f=globalThis.__appearanceRunner,i=f.cursor++;if(!(i in f.cells))f.cells[i]={current:initial};return f.cells[i] }
        export function useMemo(fn,deps) { const f=globalThis.__appearanceRunner,i=f.cursor++,old=f.cells[i];if(!old||deps.some((v,n)=>v!==old.deps[n]))f.cells[i]={deps,value:fn()};return f.cells[i].value }
        export function useCallback(fn,deps) { return useMemo(()=>fn,deps) }
        export function useEffect(fn,deps) { const f=globalThis.__appearanceRunner,i=f.cursor++,old=f.cells[i];if(!old||deps.some((v,n)=>v!==old[n])){f.cells[i]=deps;f.effects.push(fn)} }
      `
    },
    transform(source, id) {
      if (id.endsWith('/StudentExamPage.jsx')) return source.replace("from 'react'", "from 'appearance-fixture-react'").replace("from 'react-router-dom'", "from 'appearance-fixture-router'").replace("from '../../context/LanguageModeContext.jsx'", "from 'appearance-fixture-language'")
    },
  }] })
  try {
    const { default: Runner } = await server.ssrLoadModule('/src/pages/student/StudentExamPage.jsx')
    const api = { mode: 'portal', clearPath() {}, backPath: '/student/exams' }
    const render = () => { f.cursor = 0; return Runner({ api }) }
    render(); assert.ok(f.effects.length > 0); f.effects.length = 0
    const state = { document: { documentElement: { dataset: {}, style: {} } } }
    applyTheme('dark', state, true)
    f.languageMode = 'arabic'; render()
    assert.equal(f.effects.length, 0, 'no lifecycle/read/save/submit effect restarts after appearance changes')
    assert.equal(f.cells[1].id, 7); assert.equal(f.cells[5], answers); assert.equal(f.cells[2], order)
    assert.equal(f.cells[6], marked); assert.equal(f.cells[7], 123)
    assert.equal(question.question.text, 'Authored English question')
    f.languageMode = 'english'; applyTheme('light', state); render(); assert.equal(f.effects.length, 0)
  } finally { delete globalThis.__appearanceRunner; await server.close() }
})
