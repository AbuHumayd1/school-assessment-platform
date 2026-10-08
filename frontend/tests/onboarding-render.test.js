import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import { loadSessionUser } from '../src/services/session.js'

test('anonymous setup offers pilot enquiry without registration; authenticated setup retains real fields', async () => {
  const server = await createServer({
    server: { middlewareMode: true },
    appType: 'custom',
    optimizeDeps: { noDiscovery: true, include: [] },
    plugins: [{
      name: 'onboarding-auth-fixture',
      enforce: 'pre',
      resolveId(source) {
        if (source.endsWith('/context/AuthContext.jsx')) return '\0test-auth-context'
        if (source.endsWith('/context/WorkspaceContext.jsx')) return '\0test-workspace-context'
      },
      load(id) {
        if (id === '\0test-auth-context') return 'export function useAuth() { return globalThis.__onboardingAuthFixture }'
        if (id === '\0test-workspace-context') return 'export function useWorkspace() { return {} }'
      },
    }],
  })
  try {
    const user = await loadSessionUser(async path => {
      assert.equal(path, 'auth/me/')
      throw Object.assign(new Error('Unauthenticated'), { status: 401 })
    })
    assert.equal(user, null)
    globalThis.__onboardingAuthFixture = { user, loading: false, error: null }
    const { default: OnboardingPage } = await server.ssrLoadModule('/src/pages/public/OnboardingPage.jsx')
    const { PublicLocaleProvider } = await server.ssrLoadModule('/src/context/PublicLocaleContext.jsx')
    const html = renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: ['/setup'] },
      React.createElement(PublicLocaleProvider, null, React.createElement(OnboardingPage))))
    assert.match(html, /Institution Workspace Pilot/)
    assert.match(html, /contact\?interest=institution-pilot/)
    assert.doesNotMatch(html, /name="password_confirmation"|<form/)
    assert.doesNotMatch(html, /Something went wrong/)
    for (const account of [
      { id: 7, email: 'admin@example.com' },
      { id: 8, email: 'candidate@example.com', is_candidate: true },
    ]) {
      globalThis.__onboardingAuthFixture = { user: account, loading: false, error: null }
      const workspaceHtml = renderToStaticMarkup(React.createElement(MemoryRouter, null,
        React.createElement(PublicLocaleProvider, null, React.createElement(OnboardingPage))))
      assert.match(workspaceHtml, /name="institution_type"/)
      assert.match(workspaceHtml, /value="madrasah"/)
      assert.match(workspaceHtml, /name="name"/)
      assert.match(workspaceHtml, /name="email"/)
      assert.doesNotMatch(workspaceHtml, /backend|setup preview|TODO|mock/i)
      assert.doesNotMatch(workspaceHtml, /name="password_confirmation"/)
    }
    const previousStorage = globalThis.localStorage
    try {
      for (const locale of ['en', 'ar']) for (const theme of ['light', 'dark']) {
        globalThis.localStorage = { getItem: key => key === 'madaar.theme' ? theme : locale }
        globalThis.__onboardingAuthFixture = { user: { id: 7, email: 'Original@Example.com' }, loading: false, error: null }
        const localized = renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(PublicLocaleProvider, null, React.createElement(OnboardingPage))))
        assert.ok(localized.includes(locale === 'ar' ? 'إعداد مؤسستك' : 'Set up your institution'))
        assert.ok(localized.includes(locale === 'ar' ? 'dir="rtl"' : 'dir="ltr"'))
        assert.match(localized, /Original@Example.com/)
      }
    } finally { if (previousStorage === undefined) delete globalThis.localStorage; else globalThis.localStorage = previousStorage }
    globalThis.__onboardingAuthFixture = { user: null, loading: false, error: new Error('Network failure') }
    const failureHtml = renderToStaticMarkup(React.createElement(MemoryRouter, null,
      React.createElement(PublicLocaleProvider, null, React.createElement(OnboardingPage))))
    assert.match(failureHtml, /Account access could not be checked/)
    assert.match(failureHtml, /Try again/)
    assert.doesNotMatch(failureHtml, /name="password_confirmation"/)
  } finally {
    delete globalThis.__onboardingAuthFixture
    await server.close()
  }
})

test('auth initialization propagates genuine failures instead of treating them as anonymous', async () => {
  const account = { id: 7, email: 'admin@example.com' }
  assert.equal(await loadSessionUser(async () => account), account)
  for (const error of [Object.assign(new Error('Server failure'), { status: 500 }), new Error('Network failure'), Object.assign(new Error('Forbidden'), { status: 403 })]) {
    await assert.rejects(loadSessionUser(async () => { throw error }), caught => caught === error)
  }
  for (const malformed of [null, {}, { id: '7', email: 'admin@example.com' }, { authenticated: false }]) {
    await assert.rejects(loadSessionUser(async () => malformed), /unexpected account response/)
  }
})
