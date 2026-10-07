import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { createServer } from 'vite'

async function controller(run) {
  const fixture = { cells: [], calls: [], options: { subjects: [], groups: [], choices: {} } }
  globalThis.__examDelivery = fixture
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] }, plugins: [{
    name: 'exam-delivery-controller', enforce: 'pre',
    resolveId(id) { if (id.startsWith('delivery-fixture-')) return '\0' + id },
    load(id) {
      if (id === '\0delivery-fixture-hooks') return `export * from 'react';
        export function useState(initial) { const f=globalThis.__examDelivery,i=f.cursor++;if(!(i in f.cells))f.cells[i]=initial;return[f.cells[i],next=>f.cells[i]=typeof next==='function'?next(f.cells[i]):next] }
        export function useRef(initial) { const f=globalThis.__examDelivery,i=f.cursor++;if(!(i in f.cells))f.cells[i]={current:initial};return f.cells[i] }
        export function useEffect() {}`
      if (id === '\0delivery-fixture-router') return `export { Link } from 'react-router-dom';export function useLocation(){return {hash:''}};export function useNavigate(){return (...args)=>globalThis.__examDelivery.navigation=args}`
      if (id === '\0delivery-fixture-read') return `export * from '/src/pages/staff/exam-ui.jsx';export function useExamCopy(){return {t:v=>v,direction:'ltr'}};export function useOwnerRead(){const f=globalThis.__examDelivery;return {data:{options:f.options,exam:f.exam}}}`
      if (id === '\0delivery-fixture-service') return `export * from '/src/services/assessments.js';export async function examRequest(institution,path,options){const f=globalThis.__examDelivery;f.calls.push({institution,path,options});if(f.failure)throw f.failure;return {id:22}}`
    },
    transform(source, id) {
      if (id.endsWith('/src/pages/staff/ExamFormPage.jsx')) return source.replace("from 'react'", "from 'delivery-fixture-hooks'").replace("from 'react-router-dom'", "from 'delivery-fixture-router'").replace("from './exam-ui.jsx'", "from 'delivery-fixture-read'").replace("from '../../services/assessments.js'", "from 'delivery-fixture-service'")
    },
  }] })
  try {
    const { Form } = await server.ssrLoadModule('/src/pages/staff/ExamFormPage.jsx')
    function walk(node) { return node && typeof node === 'object' ? [node, ...React.Children.toArray(node.props?.children).flatMap(walk)] : [] }
    const draw = (id) => { fixture.cursor = 0; return walk(Form({ institutionId: 7, id })) }
    await run(fixture, draw)
  } finally { delete globalThis.__examDelivery; await server.close() }
}

for (const delivery of ['quick_exam', 'account_login']) {
  test(`Create starts with delivery and persists ${delivery} in the create request`, async () => controller(async (f, draw) => {
    let nodes = draw()
    const choice = nodes.find(n => n.type?.name === 'DeliveryChoice')
    assert.ok(choice)
    assert.ok(!nodes.some(n => n.type?.name === 'ExamFields' || n.type === 'form'))
    assert.equal(f.calls.length, 0)
    choice.props.onChoose(delivery)
    nodes = draw()
    assert.ok(!nodes.some(n => n.type?.name === 'DeliveryChoice'))
    const fields = nodes.find(n => n.type?.name === 'ExamFields')
    fields.props.onChange('title', 'Isolated delivery fixture')
    fields.props.onChange('subject', '4')
    nodes = draw()
    await nodes.find(n => n.type === 'form').props.onSubmit({ preventDefault() {} })
    assert.equal(f.calls.length, 1)
    assert.equal(f.calls[0].options.method, 'POST')
    assert.equal(f.calls[0].options.body.delivery_mode, delivery)
    assert.ok(!('candidate_access' in f.calls[0].options.body))
    assert.deepEqual(f.navigation, ['/app/exams/22?section=questions', { replace: true }])
  }))
}

test('failed creation retains the delivery decision for retry', async () => controller(async (f, draw) => {
  draw().find(n => n.type?.name === 'DeliveryChoice').props.onChoose('quick_exam')
  f.failure = { status: 400, data: { title: ['Required'] } }
  await draw().find(n => n.type === 'form').props.onSubmit({ preventDefault() {} })
  const nodes = draw()
  assert.ok(nodes.some(n => n.props?.role === 'alert'))
  assert.ok(!nodes.some(n => n.type?.name === 'DeliveryChoice'))
  f.failure = null
  await nodes.find(n => n.type === 'form').props.onSubmit({ preventDefault() {} })
  assert.ok(f.calls.every(c => c.options.body.delivery_mode === 'quick_exam'))
}))

test('editing a saved exam does not ask for or write another delivery choice', async () => controller(async (f, draw) => {
  f.exam = { id: 22, status: 'draft', delivery_mode: 'quick_exam', candidate_access: 'access_code', subject: 4 }
  const nodes = draw(22)
  assert.ok(!nodes.some(n => n.type?.name === 'DeliveryChoice'))
  await nodes.find(n => n.type === 'form').props.onSubmit({ preventDefault() {} })
  assert.equal(f.calls[0].options.method, 'PATCH')
  assert.ok(!('delivery_mode' in f.calls[0].options.body))
  assert.ok(!('candidate_access' in f.calls[0].options.body))
}))
