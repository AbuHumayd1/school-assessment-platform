import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import { canAccessWorkspaceCapability } from '../src/utils/staffCapabilities.js'
import { examCopy } from '../src/pages/staff/exam-copy.js'

const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
const { SubjectEmptyState, listWorkspaceSubjects } = await server.ssrLoadModule('/src/pages/staff/SubjectsPage.jsx')
const { LanguageModeProvider } = await server.ssrLoadModule('/src/context/LanguageModeContext.jsx')
const { ExamFields } = await server.ssrLoadModule('/src/pages/staff/ExamFormPage.jsx')
await server.close()
const render = element => renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(LanguageModeProvider, null, element)))

test('empty subject state provides a direct bootstrap route', () => {
  const html = renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(SubjectEmptyState)))
  assert.match(html, /No subjects have been created for this institution yet/)
  assert.match(html, /href="\/app\/subjects"/)
})
test('independent empty state uses caller-provided Arabic localization', () => {
  const html = renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(SubjectEmptyState, { t: text => examCopy[text] || text })))
  assert.match(html, /لم تُنشأ أي مواد لهذه المؤسسة بعد/)
  assert.match(html, /إنشاء مادة/)
  assert.match(html, /href="\/app\/subjects"/)
})
test('Create Exam empty subject list explains how to bootstrap', () => {
  const html = render(React.createElement(ExamFields, { values: {}, options: { subjects: [], groups: [], choices: {} }, t: text => text, onChange: () => {} }))
  assert.match(html, /No subjects have been created/)
  assert.match(html, /href="\/app\/subjects"/)
})
test('subject listing includes every page with explicit workspace context', async () => {
  const paths = []
  const rows = await listWorkspaceSubjects(7, undefined, async path => {
    paths.push(path)
    return paths.length === 1 ? { results: [{ id: 1, institution: 7 }], next: '/next' } : { results: [{ id: 2, institution: 7 }], next: null }
  })
  assert.deepEqual(rows.map(row => row.id), [1, 2])
  assert.deepEqual(paths, ['subjects/?institution=7&page=1', 'subjects/?institution=7&page=2'])
})
test('subject listing rejects a mismatched tenant response', async () => {
  await assert.rejects(listWorkspaceSubjects(7, undefined, async () => ({ results: [{ id: 1, institution: 8 }] })), /Workspace context changed/)
})
test('platform subject preparation preserves managed-client owner restrictions', () => {
  assert.equal(canAccessWorkspaceCapability('platform_admin', 'subjects', 'managed_exam'), true)
  assert.equal(canAccessWorkspaceCapability('institution_admin', 'subjects', 'managed_exam'), false)
  assert.equal(canAccessWorkspaceCapability('institution_admin', 'subjects', 'institution_workspace'), true)
})
