import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { initialWorkspace, validWorkspaces } from '../src/utils/workspaceSelection.js'
import { canAccessWorkspaceCapability } from '../src/utils/staffCapabilities.js'

const full = { institution: { id: 1, name: 'Full', workspace_mode: 'full_workspace' }, role: 'institution_admin' }
const managed = { institution: { id: 3, name: 'Activus', workspace_mode: 'managed_exam' }, role: 'institution_admin' }

test('sole actual client always wins over stale stored selection', () => {
  assert.equal(initialWorkspace([managed], false, full), managed)
  assert.equal(initialWorkspace([full], false, managed), full)
})
test('multiple institutions require explicit choice and switching changes capabilities', () => {
  assert.equal(initialWorkspace([full, managed], false, full), null)
  for (const selected of [managed, full, managed]) {
    assert.equal(canAccessWorkspaceCapability(selected.role, 'questions', selected.institution.workspace_mode), selected === full)
    for (const capability of ['dashboard', 'candidates', 'assessments', 'submissions', 'results', 'reports']) {
      assert.equal(canAccessWorkspaceCapability(selected.role, capability, selected.institution.workspace_mode), true)
    }
  }
  assert.equal(initialWorkspace([full, managed], true, managed), managed)
})
test('missing or unknown institution mode fails closed', () => {
  assert.deepEqual(validWorkspaces({ workspaces: [managed, full] }), [managed, full])
  for (const mode of [undefined, 'unknown']) assert.throws(() => validWorkspaces({ workspaces: [{ ...managed, institution: { ...managed.institution, workspace_mode: mode } }] }), /configuration/)
})
test('preview displays candidates and row errors without answers or accounts', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  try {
    const { CandidateImportPreview, candidateTemplate } = await server.ssrLoadModule('/src/pages/staff/CandidateImport.jsx')
    assert.match(candidateTemplate, /^first_name,last_name,candidate_id,email/)
    const html = renderToStaticMarkup(React.createElement(CandidateImportPreview, { preview: { count: 1, rows: [{ row: 2, first_name: 'Amina', last_name: 'Person', candidate_id: '001', email: '' }], errors: [{ row: 2, errors: { candidate_id: ['Already used.'] } }] } }))
    for (const text of ['No records have been created', 'Amina', '001', 'Not provided', 'Row 2', 'Already used']) assert.ok(html.includes(text))
    assert.doesNotMatch(html, /PIN|password|is_correct/)
  } finally { await server.close() }
})
