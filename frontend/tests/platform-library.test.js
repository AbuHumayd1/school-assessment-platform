import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'

const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
const ui = await server.ssrLoadModule('/src/pages/platform/PlatformLibrary.jsx')
const platform = await server.ssrLoadModule('/src/pages/platform/PlatformPages.jsx')
const service = await server.ssrLoadModule('/src/services/platformLibrary.js')
const api = await server.ssrLoadModule('/src/services/api.js')
await server.close()
const render = (component, props = {}) => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(component, props)))
const question = { id: 12, subject: 3, text: 'Disposable platform question', question_type: 'multiple_choice', status: 'approved', content_locked: true, revision_number: 1, revision_family: 'family', available_for_new_assessments: false, options: [{ id: 1, text: 'Correct', is_correct: true }], media: [] }

test('library routes inherit platform authority and never require a workspace', async () => {
  const app = await readFile(new URL('../src/App.jsx', import.meta.url), 'utf8')
  const start = app.indexOf('<Route path="platform"')
  const end = app.indexOf('<Route path="app"', start)
  const routes = app.slice(start, end)
  assert.match(routes, /RequirePlatform/)
  assert.match(routes, /path="library" element={<PlatformLibrary/)
  assert.match(routes, /path="institution-banks" element={<InstitutionBanks/)
  assert.equal(platform.platformAccessState({ id: 1 }, false, { isPlatformAdmin: false }), 'denied')
  assert.equal(platform.platformAccessState({ id: 1 }, false, { isPlatformAdmin: true }), 'ready')
})

test('library has subject creation and question search filters', () => {
  const html = render(ui.default)
  for (const label of ['Platform Library', 'Create a platform subject', 'Subject name', 'Subject code', 'Create subject', 'Search questions', 'Difficulty', 'Status', 'Create question']) assert.ok(html.includes(label), label)
  assert.doesNotMatch(html, /owner_scope|CRUD|tenant/)
})

test('institution banks provides client selection instead of mixed question data', () => {
  const html = render(ui.InstitutionBanks)
  assert.match(html, /href="\/platform\/clients"/)
  assert.match(html, /only that client/)
  assert.doesNotMatch(html, /Disposable platform question|<table/)
})

test('approved card displays revision identity and disables direct editing', () => {
  const html = render(ui.LibraryQuestionCard, { question })
  assert.match(html, /Approved · Revision 1/)
  assert.match(html, /disabled="">Edit/)
  assert.match(html, /Create new revision/)
  assert.match(html, /Existing references remain valid/)
  assert.match(html, /Revision family family/)
  assert.doesNotMatch(html, /Submit for review/)
})

test('draft and review cards expose their supported transitions', () => {
  const draft = render(ui.LibraryQuestionCard, { question: { ...question, status: 'draft', content_locked: false } })
  assert.match(draft, /Submit for review/)
  assert.doesNotMatch(draft, /Create new revision/)
  const review = render(ui.LibraryQuestionCard, { question: { ...question, status: 'review', content_locked: false } })
  assert.match(review, /Request changes/)
  assert.match(review, />Approve</)
})

test('editor reuses objective types and subject-specific topic choices', () => {
  const html = render(ui.LibraryQuestionForm, { initial: ui.blankQuestion(3), subjects: [{ id: 3, name: 'Subject', code: 'CODE' }], topics: [{ id: 4, subject: 3, name: 'Own topic' }, { id: 5, subject: 9, name: 'Foreign topic' }] })
  for (const label of ['Multiple choice', 'Multiple select', 'True / False', 'Own topic', 'Correct answer', 'Add option', 'Save question']) assert.ok(html.includes(label), label)
  assert.doesNotMatch(html, /Foreign topic/)
})

test('question payload preserves objective answer flags without client ownership', () => {
  const payload = ui.questionPayload(ui.blankQuestion(3))
  assert.equal(payload.subject, 3)
  assert.equal(payload.topic, null)
  assert.deepEqual(payload.options.map(option => [option.order, option.is_correct]), [[1, true], [2, false]])
  assert.equal('owner_scope' in payload, false)
  assert.equal('institution' in payload, false)
})

test('platform calls list/create/workflow on separate endpoints without workspace header', async () => {
  const original = globalThis.fetch
  const calls = []
  api.clearSessionContext()
  api.setInstitutionContext(99)
  globalThis.fetch = async (url, options) => {
    calls.push({ url, options })
    return new Response(JSON.stringify(url.endsWith('auth/csrf/') ? { csrfToken: 'test-token' } : { results: [], next: null, id: 12 }), { headers: { 'Content-Type': 'application/json' } })
  }
  try {
    await service.libraryList('questions', { subject: 3, search: 'EEG', page: 2 })
    await service.librarySave('subjects', { name: 'Disposable', code: 'NEW' })
    await service.librarySave('questions', ui.questionPayload(ui.blankQuestion(3)))
    await service.libraryAction(12, 'new-revision')
    assert.match(calls[0].url, /platform\/library\/questions\/\?subject=3&search=EEG&page=2/)
    for (const call of calls) assert.equal(call.options.headers.has('X-Institution-ID'), false)
    assert.ok(calls.some(call => call.url.endsWith('platform/library/subjects/') && call.options.method === 'POST'))
    const revision = calls.find(call => call.url.endsWith('12/new-revision/'))
    assert.equal(revision.options.body, '{}')
  } finally { globalThis.fetch = original; api.clearSessionContext() }
})

test('institution navigation never adds platform library for institution-only users', async () => {
  const staff = await readFile(new URL('../src/layouts/StaffLayout.jsx', import.meta.url), 'utf8')
  assert.doesNotMatch(staff, /\/platform\/library|\/platform\/institution-banks/)
})
