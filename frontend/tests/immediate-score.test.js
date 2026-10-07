import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import { readFile } from 'node:fs/promises'

test('completion discloses only a server-provided score and configuration persists independently', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  try {
    const { default: ImmediateScore } = await server.ssrLoadModule('/src/components/student/ImmediateScore.jsx')
    const { QuickCompletionView } = await server.ssrLoadModule('/src/pages/public/QuickExamPages.jsx')
    const { ExamFields } = await server.ssrLoadModule('/src/pages/staff/ExamFormPage.jsx')
    const { examFields } = await server.ssrLoadModule('/src/services/assessments.js')
    const render = (Component, props) => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(Component, props)))
    const score = { marks_obtained: '7.00', total_marks: '10.00', grade: 'A', passed: true, percentage: '70', answer_key: 'Private marking key' }
    const html = render(QuickCompletionView, { status: 'submitted', score })
    assert.match(html, /Your score/)
    assert.match(html, /Exam submitted successfully/)
    assert.match(html, /7 \/ 10/)
    assert.doesNotMatch(html, /Private marking key|passed|percentage|70|Grade/)
    assert.equal(render(ImmediateScore, { score: null }), '')
    assert.doesNotMatch(render(QuickCompletionView, { status: 'submitted' }), /Your score/)
    assert.doesNotMatch(render(QuickCompletionView, { status: 'in_progress', score }), /Your score/)
    for (const invalid of [{ marks_obtained: '11', total_marks: '10' }, { marks_obtained: 'NaN', total_marks: '10' }, { marks_obtained: '0', total_marks: '0' }, {}]) {
      assert.equal(render(ImmediateScore, { score: invalid }), '')
    }
    const values = { title: 'Synthetic exam', subject: 1, duration_minutes: 5, attempt_limit: 1,
      result_visibility: 'after_submission', result_release_mode: 'manual_release', show_score_immediately: true }
    const options = { subjects: [], groups: [], choices: {} }
    const form = render(ExamFields, { values, options, t: text => text, onChange() {} })
    assert.match(form, /Show score immediately after submission/)
    assert.match(form, /full results remain hidden until results are released/)
    assert.match(form, /name="show_score_immediately"[^>]*checked=""/)
    const changes = []
    const tree = ExamFields({ values, options, t: text => text, onChange: (...args) => changes.push(args) })
    const setting = tree.props.children[1].find(node => node?.key === 'show_score_immediately')
    setting.props.children[0].props.children[0].props.onChange({ target: { checked: false } })
    assert.deepEqual(changes, [['show_score_immediately', false]])
    const persisted = examFields(values)
    assert.equal(persisted.show_score_immediately, true)
    assert.equal(persisted.result_visibility, 'after_submission')
    assert.equal(persisted.result_release_mode, 'manual_release')
    assert.equal(examFields({ ...values, show_score_immediately: false }).show_score_immediately, false)
    const accountSource = await readFile(new URL('../src/pages/student/StudentExamPage.jsx', import.meta.url), 'utf8')
    assert.match(accountSource, /immediate_score: result.immediate_score/)
    assert.match(accountSource, /<ImmediateScore score=\{attempt.immediate_score\}/)
  } finally { await server.close() }
})
