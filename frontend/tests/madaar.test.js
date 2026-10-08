import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import { readFile } from 'node:fs/promises'
import { madaarAr } from '../src/context/madaarTranslations.js'
import { initialTheme } from '../src/utils/theme.js'

const server = await createServer({
  server: { middlewareMode: true, hmr: false }, appType: 'custom',
  optimizeDeps: { noDiscovery: true, include: [] },
  plugins: [{ name: 'madaar-session-fixtures', enforce: 'pre',
    resolveId(source) {
      if (source.endsWith('/context/AuthContext.jsx')) return '\0madaar-auth'
      if (source.endsWith('/context/WorkspaceContext.jsx')) return '\0madaar-workspace'
    },
    load(id) {
      if (id === '\0madaar-auth') return 'export function useAuth() { return globalThis.__madaar.auth }'
      if (id === '\0madaar-workspace') return 'export function useWorkspace() { return globalThis.__madaar.workspace }'
    },
    transform(source, id) {
      if (id.endsWith('/ManagedExamCTA.jsx')) return source.replace('import.meta.env.VITE_PUBLIC_WHATSAPP_NUMBER', 'globalThis.__madaarWhatsApp').replace('import.meta.env.VITE_PUBLIC_CONTACT_EMAIL', 'globalThis.__madaarEmail')
    },
  }],
})
const { default: App } = await server.ssrLoadModule('/src/App.jsx')
const { LanguageModeProvider } = await server.ssrLoadModule('/src/context/LanguageModeContext.jsx')
const { PublicLocaleProvider } = await server.ssrLoadModule('/src/context/PublicLocaleContext.jsx')
const { PublicNavigation } = await server.ssrLoadModule('/src/layouts/PublicLayout.jsx')
const { enquiryTypes } = await server.ssrLoadModule('/src/pages/public/CommercialPages.jsx')
const { default: Request, publicContactEmail } = await server.ssrLoadModule('/src/components/common/ManagedExamRequest.jsx')
const { publicWhatsAppNumber, managedExamDestination, managedExamMessage } = await server.ssrLoadModule('/src/components/common/ManagedExamCTA.jsx')
const { QuickExamFrame } = await server.ssrLoadModule('/src/pages/public/QuickExamPages.jsx')
const { QuestionRenderer } = await server.ssrLoadModule('/src/components/student/StudentComponents.jsx')
const { quickExamTranslate } = await server.ssrLoadModule('/src/utils/quickExamLocale.js')
await server.close()
globalThis.__madaar = {
  auth: { user: null, loading: false },
  workspace: { loading: false, isPlatformAdmin: true, accessState: 'ready', currentRole: 'platform_admin', workspaces: [], clearSelection() {} },
}
function render(path) {
  return renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: [path] }, React.createElement(LanguageModeProvider, null, React.createElement(App))))
}
test('actual public root presents current Madaar offerings and working access links', () => {
  const html = render('/')
  for (const copy of ['Madaar', 'Create. Assess. Mark. Analyse. Improve.', 'Available Now', 'Currently in Pilot', 'Request a Managed Examination']) assert.ok(html.includes(copy))
  assert.match(html, /id="managed-examinations"/)
  assert.match(html, /id="institution-workspace"/)
  assert.match(html, /href="\/signin"/)
  assert.match(html, /href="\/take-exam"/)
  assert.match(html, /href="\/contact"/)
  assert.doesNotMatch(html, /School Assessment Platform|Free Trial|Most popular|Starter|₦|AI invigilation/)
})
test('all public section navigation points to a rendered homepage target', () => {
  const html = render('/')
  for (const [, id] of html.matchAll(/href="\/#([\w-]+)"/g)) assert.ok(html.includes(`id="${id}"`), id)
})

test('education vision distinguishes the current foundation from future capabilities in both languages and themes', () => {
  const previous = globalThis.localStorage
  try {
    for (const locale of ['en', 'ar']) for (const theme of ['light', 'dark']) {
      globalThis.localStorage = { getItem: key => key === 'madaar.theme' ? theme : locale }
      assert.equal(initialTheme({ localStorage: globalThis.localStorage }), theme)
      const html = render('/')
      const vision = html.match(/<section id="madaar-vision"[\s\S]*?<\/section>/)[0]
      const translated = text => locale === 'ar' ? madaarAr[text] : text.replaceAll("'", '&#x27;')
      for (const text of ["Assessment is where we're starting.", "Better education is where we're going.", 'Starting with Assessment', 'Future Direction', 'Basic assessment reporting is available today. Broader learning analytics are part of our future direction.']) assert.ok(vision.includes(translated(text)), text)
      const areas = [...vision.matchAll(/<li class="madaar-vision__area[^>]*>([\s\S]*?)<\/li>/g)].map(match => match[1])
      assert.equal(areas.length, 5)
      for (const [index, title] of ['Teach', 'Learn', 'Assess', 'Analyse', 'Improve'].entries()) assert.ok(areas[index].includes(`<h4>${translated(title)}</h4>`))
      for (const area of areas.slice(0, 2)) {
        assert.ok(area.includes(translated('Future Direction')))
        assert.doesNotMatch(area, /madaar-status|Available Now|متاحة الآن/)
      }
      for (const text of ['Available Now', 'Currently in Pilot', 'Madrasahs & Islamic Educational Institutes', 'Create. Assess. Mark. Analyse. Improve.']) assert.ok(html.includes(locale === 'ar' ? madaarAr[text] : text.replaceAll('&', '&amp;')))
      assert.match(vision, /madaar-vision__area--current/)
    }
  } finally { if (previous === undefined) delete globalThis.localStorage; else globalThis.localStorage = previous }
})

test('vision styling uses existing theme tokens and logical RTL/mobile progression', async () => {
  const css = await readFile(new URL('../src/pages/public/madaar.css', import.meta.url), 'utf8')
  assert.match(css, /\.madaar-vision__loop[^}]*repeat\(5, minmax\(0, 1fr\)\)/)
  assert.match(css, /\.madaar-vision__area--current[^}]*var\(--brand-soft\)/)
  assert.match(css, /\.madaar-vision__area[^}]*border-inline-start: 2px solid var\(--border\)/)
  assert.match(css, /\.madaar-vision__loop \{ grid-template-columns: 1fr; \}/)
})

test('Madrasahs are an explicit audience in English and Arabic', () => {
  assert.match(render('/'), /Madrasahs &amp; Islamic Educational Institutes/)
  assert.equal(madaarAr['Madrasahs & Islamic Educational Institutes'], 'المدارس والمعاهد الإسلامية')
  assert.equal(madaarAr['Built for Madrasahs'], 'مصمّمة للمدارس والمعاهد الإسلامية')
  const previous = globalThis.localStorage
  globalThis.localStorage = { getItem: () => 'ar' }
  try { assert.match(render('/'), /المدارس والمعاهد الإسلامية/) }
  finally { if (previous === undefined) delete globalThis.localStorage; else globalThis.localStorage = previous }
})

test('section links stay neutral and Pricing/Contact stay route-aware in both languages and themes', () => {
  const previous = globalThis.localStorage
  try {
    for (const locale of ['en', 'ar']) for (const theme of ['light', 'dark']) {
      globalThis.localStorage = { getItem: key => key === 'madaar.theme' ? theme : locale }
      assert.equal(initialTheme({ localStorage: globalThis.localStorage }), theme)
      for (const path of ['/', '/#managed-examinations', '/#institution-workspace', '/pricing', '/contact']) {
        // Desktop and mobile share this exact navigation component.
        const html = renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: [path] }, React.createElement(PublicLocaleProvider, null, React.createElement(PublicNavigation))))
        const anchors = [...html.matchAll(/<a\b([^>]+)>/g)].map(match => match[1])
        assert.equal(anchors.length, 4)
        for (const attrs of anchors.slice(0, 2)) assert.doesNotMatch(attrs, /class="active"|aria-current/)
        for (const [index, route] of [[2, '/pricing'], [3, '/contact']]) {
          assert.equal(anchors[index].includes('aria-current="page"'), path === route)
          assert.equal(/class="active"/.test(anchors[index]), path === route)
        }
      }
    }
  } finally { if (previous === undefined) delete globalThis.localStorage; else globalThis.localStorage = previous }
})

test('desktop nav uses theme-neutral text and brand hover/active with an RTL-safe indicator', async () => {
  const css = await readFile(new URL('../src/styles/theme.css', import.meta.url), 'utf8')
  assert.match(css, /\.public-header > \.public-nav a \{ color: var\(--text\); border-block-end: 2px solid transparent; \}/)
  assert.match(css, /\.public-header > \.public-nav a:hover \{ color: var\(--brand\); \}/)
  assert.match(css, /\.public-header > \.public-nav a.active \{ color: var\(--brand\); border-block-end-color: var\(--brand\); \}/)
})
test('contact CTA handles missing or invalid configuration honestly, and valid public email opens mail', () => {
  for (const value of ['', 'https://example.com', 'a@example.com\nBcc:other@example.com']) assert.equal(publicContactEmail(value), null)
  assert.equal(publicContactEmail(' public@example.com '), 'public@example.com')
  const missing = renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(Request, { number: null, email: null })))
  assert.match(missing, /No request has been submitted/)
  assert.doesNotMatch(missing, /<form|mailto:|successfully/)
  const configured = renderToStaticMarkup(React.createElement(Request, { email: 'public@example.com' }))
  assert.match(configured, /href="mailto:public@example.com\?subject=Request%20a%20Managed%20Examination&amp;body=/)
  assert.match(configured, /only when you send the email/)
})
test('WhatsApp configuration accepts only international digits and encodes the exact sales message', () => {
  for (const value of ['', '+12345678901', '123 45678901', '234XXXXXXXXXX', '0123456789', '123456', '1234567890123456', 'https://wa.me/12345678901']) assert.equal(publicWhatsAppNumber(value), null)
  const destination = managedExamDestination({ number: '12345678901', email: 'public@example.com' })
  const url = new URL(destination.href)
  assert.equal(url.origin, 'https://wa.me')
  assert.equal(url.pathname, '/12345678901')
  assert.equal(url.searchParams.get('text'), managedExamMessage)
  assert.equal(destination.kind, 'whatsapp')
  assert.equal(managedExamDestination({ number: '+12345678901', email: null }).href, '/contact')
})
test('configured commercial CTAs consistently open safe WhatsApp links; Contact uses a broader enquiry', () => {
  globalThis.__madaarWhatsApp = '12345678901'
  try {
    const destination = managedExamDestination().href
    for (const path of ['/', '/pricing']) {
      const html = render(path)
      const anchors = [...html.matchAll(/<a\b([^>]+)>(.*?)<\/a>/g)].filter(([, , label]) => /Request (an|a Managed) Examination/.test(label))
      assert.ok(anchors.length >= (path === '/' ? 6 : 4))
      for (const [, attrs] of anchors) {
        assert.ok(attrs.replaceAll('&#x27;', "'").includes(`href="${destination}"`))
        assert.match(attrs, /target="_blank"/)
        assert.match(attrs, /rel="noopener noreferrer"/)
      }
    }
    const contact = render('/contact')
    assert.match(contact, /General Enquiry/)
    assert.ok(contact.replaceAll('&#x27;', "'").includes('https://wa.me/12345678901?text=' + encodeURIComponent("Hello, I'd like to enquire about General Enquiry with Madaar.")))
  } finally { delete globalThis.__madaarWhatsApp }
})
test('real signin, contact and legacy pricing routes show Madaar without placeholder claims', () => {
  for (const path of ['/signin', '/contact', '/pricing']) {
    const html = render(path)
    assert.match(html, /Madaar/)
    assert.doesNotMatch(html, /School Assessment Platform|Preview noted|Most popular|Free Trial/)
    if (path === '/signin') assert.match(html, /name="password"/)
  }
})
test('pricing shows custom service pricing and planned workspace tiers without invented prices or limits', () => {
  const html = render('/pricing')
  for (const text of ['Custom pricing', 'Starter', 'Growth', 'Professional', 'Enterprise', 'Final plan pricing and limits will be announced before general availability.']) assert.ok(html.includes(text))
  assert.match(html, /href="\/contact\?interest=institution-pilot"/)
  assert.doesNotMatch(html, /Free Trial|₦|\$\d|AI credits|\d+ candidates|GB storage/)
})
test('contact enquiry query selects each supported intent and invalid values fall back to general', () => {
  for (const interest of ['managed-exam', 'institution-pilot', 'partnership', 'general']) assert.ok(render('/contact?interest=' + interest).includes(`value="${interest}" selected=""`))
  const html = render('/contact?interest=unknown')
  assert.match(html, /value="general" selected=""/)
  assert.doesNotMatch(html, /<form|successfully submitted/)
})

test('Contact shows enquiry-specific copy and primary labels in English/Arabic and light/dark with existing destinations', () => {
  const previous = globalThis.localStorage
  const escaped = text => text.replaceAll('&', '&amp;').replaceAll("'", '&#x27;')
  try {
    for (const locale of ['en', 'ar']) for (const theme of ['light', 'dark']) {
      globalThis.localStorage = { getItem: key => key === 'madaar.theme' ? theme : locale }
      assert.equal(initialTheme({ localStorage: globalThis.localStorage }), theme)
      for (const [intent, enquiry] of Object.entries(enquiryTypes)) {
        for (const channel of ['whatsapp', 'email', 'missing']) {
          globalThis.__madaarWhatsApp = channel === 'whatsapp' ? '12345678901' : undefined
          globalThis.__madaarEmail = channel === 'email' ? 'public@example.com' : undefined
          const html = render('/contact?interest=' + intent)
          const section = html.match(/<section class="madaar-request"[\s\S]*?<\/section>/)[0]
          assert.ok(section.includes(escaped(locale === 'ar' ? madaarAr[enquiry.description] : enquiry.description)))
          assert.doesNotMatch(section, /This opens your chosen contact app|Nothing is submitted by this page|<form|successfully submitted/)
          if (channel === 'missing') assert.match(section, /role="status"/)
          else {
            const primary = section.match(/<a class="madaar-button"([^>]*)>(.*?)<\/a>/)
            assert.ok(primary, `${intent}/${channel}/${locale}/${theme}`)
            assert.equal(primary[2], escaped(locale === 'ar' ? madaarAr[enquiry.cta] : enquiry.cta))
            assert.ok(primary[1].includes(channel === 'whatsapp' ? 'https://wa.me/12345678901?text=' : 'mailto:public@example.com?subject='))
            if (channel === 'whatsapp') {
              assert.match(primary[1], /target="_blank"/)
              assert.match(primary[1], /rel="noopener noreferrer"/)
            }
          }
        }
      }
    }
  } finally {
    delete globalThis.__madaarWhatsApp; delete globalThis.__madaarEmail
    if (previous === undefined) delete globalThis.localStorage; else globalThis.localStorage = previous
  }
})
test('new public marketing, nested CTAs, Pricing and Contact translate through the existing Arabic context', () => {
  const oldStorage = globalThis.localStorage
  globalThis.localStorage = { getItem: key => key.endsWith('public-locale') ? 'ar' : 'arabic' }
  try {
    const home = render('/')
    assert.match(home, /lang="ar" dir="rtl"/)
    for (const phrase of ['كل تقييم.', 'خدمة إدارة الاختبارات', 'متاحة الآن', 'مصمّمة للمدارس', 'اطلب خدمة إدارة اختبار', 'النتائج والتقارير']) assert.ok(home.includes(phrase), phrase)
    assert.doesNotMatch(home, /Every assessment|Available Now|Request a Managed Examination|Planning an examination/)
    const pricing = render('/pricing')
    assert.match(pricing, /تسعير مخصّص/)
    assert.match(pricing, /المؤسسات الكبرى/)
    const contact = render('/contact?interest=institution-pilot')
    assert.match(contact, /المرحلة التجريبية لمساحة عمل المؤسسة/)
    assert.match(contact, /value="institution-pilot" selected=""/)
  } finally { if (oldStorage === undefined) delete globalThis.localStorage; else globalThis.localStorage = oldStorage }
})
test('interface translation leaves exact-match English and Arabic authored question/options unchanged', () => {
  const question = { id: 1, type: 'multiple_choice', prompt: 'Next', options: [{ id: 1, label: 'Submit Exam' }, { id: 2, label: 'السؤال الأصلي' }] }
  const snapshot = JSON.stringify(question)
  for (const locale of ['ar', 'en']) {
    const html = renderToStaticMarkup(React.createElement(QuestionRenderer, { question, value: [2], onChange() {}, translate: text => quickExamTranslate(locale, text) }))
    assert.match(html, />Next<\/legend>/)
    assert.match(html, /Submit Exam/)
    assert.match(html, /السؤال الأصلي/)
    assert.equal(JSON.stringify(question), snapshot)
  }
})
test('platform, managed workspace and candidate routes keep their shells and identities', () => {
  globalThis.__madaar.auth.user = { id: 1, email: 'fixture@example.com', is_candidate: true }
  const selected = { role: 'platform_admin', institution: { id: 3, name: 'ACTIVUS HEALTHCARE', workspace_mode: 'managed_exam' } }
  Object.assign(globalThis.__madaar.workspace, { currentWorkspace: selected, workspaces: [selected], resolvedUserId: 1 })
  for (const path of ['/platform/institution-banks', '/app/subjects', '/student/exams']) {
    const html = render(path)
    assert.match(html, /Madaar/)
    assert.doesNotMatch(html, /School Assessment Platform|Something went wrong/)
    if (path.startsWith('/app')) assert.match(html, /ACTIVUS HEALTHCARE/)
  }
  const html = renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(PublicLocaleProvider, null, React.createElement(QuickExamFrame, {
    session: { assessment: { title: 'ACTIVUS EEG Comprehensive Examination' }, candidate: { first_name: 'Fixture', last_name: 'Candidate', candidate_id: 'TEST' }, availability: { state: 'available' } },
  }))))
  assert.match(html, /ACTIVUS EEG Comprehensive Examination/)
  assert.match(html, /Powered by Madaar/)
})
test('document title and live examination copy retain Madaar and the assessment title', async () => {
  assert.match(await readFile(new URL('../index.html', import.meta.url), 'utf8'), /<title>Madaar<\/title>/)
  const source = await readFile(new URL('../src/pages/student/StudentExamPage.jsx', import.meta.url), 'utf8')
  assert.match(source, /attempt\.assessment_title/)
  assert.match(source, /Powered by Madaar/)
  assert.doesNotMatch(source, /School Assessment/)
})
