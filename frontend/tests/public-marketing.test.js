import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import { createServer } from 'vite'
import { readFile } from 'node:fs/promises'
import postcss from 'postcss'
import { installPublicReveal } from '../src/utils/publicReveal.js'

// Small test DOM for actual server-rendered markup; no new runtime/test dependency.
function renderedDOM(html) {
  function element(tag, attrs, parent = null) {
    const names = new Set((attrs.class || '').split(/\s+/).filter(Boolean))
    const styles = new Map()
    const node = {
      tag, attrs, parent, children: [], names, styles,
      classList: { add: (...values) => values.forEach(value => names.add(value)), remove: (...values) => values.forEach(value => names.delete(value)) },
      style: { setProperty: (key, value) => styles.set(key, value), removeProperty: key => styles.delete(key) },
      getBoundingClientRect: () => ({ top: 1000, bottom: 1200 }),
      querySelectorAll(selector) {
        const attribute = selector.slice(1, -1)
        return this.children.flatMap(child => [child, ...child.querySelectorAll(selector)]).filter(child => Object.hasOwn(child.attrs, attribute))
      },
      closest(selector) { const attribute = selector.slice(1, -1); for (let current = this; current; current = current.parent) if (Object.hasOwn(current.attrs, attribute)) return current; return null },
    }
    return node
  }
  const root = element('root', {}); const stack = [root]
  for (const match of html.matchAll(/<(\/?)([a-z][\w-]*)([^>]*)>/g)) {
    if (match[1]) { while (stack.length > 1) { if (stack.pop().tag === match[2]) break } continue }
    const attrs = Object.fromEntries([...match[3].matchAll(/([\w-]+)="([^"]*)"/g)].map(match => [match[1], match[2]]))
    const node = element(match[2], attrs, stack.at(-1)); stack.at(-1).children.push(node)
    if (!['input', 'br', 'img', 'hr', 'meta', 'link'].includes(node.tag) && !match[3].endsWith('/')) stack.push(node)
  }
  return root
}

function observerEnvironment({ reduced = false, fail = false } = {}) {
  const observed = new Set(); const unobserved = []; const frames = []; let callback; let options; let preferenceChange
  return {
    observed, unobserved, frames,
    get options() { return options },
    intersect(target) { callback([{ target, isIntersecting: true }]) },
    changePreference() { preferenceChange() },
    flushFrames() { while (frames.length) frames.shift()() },
    environment: {
      innerHeight: 700,
      requestAnimationFrame(fn) { frames.push(fn); return frames.length }, cancelAnimationFrame() {},
      matchMedia: () => ({ matches: reduced, addEventListener: (_, fn) => { preferenceChange = fn }, removeEventListener() {} }),
      IntersectionObserver: class {
        constructor(fn, settings) { if (fail) throw new Error('Observer unavailable'); callback = fn; options = settings }
        observe(node) { observed.add(node) } unobserve(node) { observed.delete(node); unobserved.push(node) } disconnect() { observed.clear() }
      },
    },
  }
}

test('real Home, Features, How It Works, Pricing, About and Contact markup supplies observed section/card targets and stagger groups', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  try {
    const { default: Home } = await server.ssrLoadModule('/src/pages/public/LandingPage.jsx')
    const pages = await server.ssrLoadModule('/src/pages/public/PublicPages.jsx')
    const { PublicLocaleProvider } = await server.ssrLoadModule('/src/context/PublicLocaleContext.jsx')
    const cases = [
      [Home, ['landing-section__heading', 'landing-card', 'landing-step', 'landing-plan', 'landing-vision', 'landing-final-cta'], 'landing-grid'],
      [pages.FeaturesPage, ['features-section-heading', 'features-detail', 'feature-next-card', 'feature-roadmap-card', 'features-audience-card', 'features-cta'], 'feature-roadmap-grid'],
      [pages.HowItWorksPage, ['workflow-overview__heading', 'workflow-overview__step', 'workflow-detail', 'workflow-cta'], 'workflow-overview__grid'],
      [pages.PricingPage, ['pricing-card', 'pricing-capacity', 'pricing-cta'], 'pricing-grid'],
      [pages.AboutPage, ['about-vision', 'about-mission', 'about-contact-card', 'about-metric', 'about-trusted', 'about-closing'], 'about-future-grid'],
      [pages.ContactPage, ['contact-copy', 'public-form'], null],
    ]
    for (const [Page, expected, groupClass] of cases) {
      const html = renderToStaticMarkup(React.createElement(MemoryRouter, null, React.createElement(PublicLocaleProvider, null, React.createElement(Page))))
      assert.doesNotMatch(html, /public-reveal--pending/)
      const root = renderedDOM(html); const targets = root.querySelectorAll('[data-public-reveal]')
      for (const className of expected) assert.ok(targets.some(node => node.names.has(className)), `${Page.name}: ${className} is a real reveal target`)
      assert.ok(targets.every(node => ![...node.names].some(name => name.endsWith('-hero'))))
      const observer = observerEnvironment(); const cleanup = installPublicReveal(root, observer.environment)
      assert.equal(observer.observed.size, 0, 'entrance cannot run before pending styles have a frame')
      observer.flushFrames(); assert.equal(observer.observed.size, targets.length)
      assert.deepEqual(observer.options, { threshold: .15, rootMargin: '0px 0px -40px 0px' })
      if (groupClass) {
        const group = root.querySelectorAll('[data-public-reveal-group]').find(node => node.names.has(groupClass))
        assert.ok(group); const cards = group.querySelectorAll('[data-public-reveal]')
        assert.ok(cards.length > 1); assert.equal(cards[0].styles.get('--reveal-delay'), '0ms'); assert.equal(cards[1].styles.get('--reveal-delay'), '80ms')
      }
      const target = targets[0]; observer.intersect(target); observer.intersect(target)
      assert.equal(target.names.has('public-reveal--pending'), false); assert.equal(target.names.has('public-reveal--shown'), true)
      assert.equal(observer.unobserved.filter(node => node === target).length, 1)
      cleanup(); assert.ok(targets.every(node => !node.names.has('public-reveal--pending')))
    }
  } finally { await server.close() }
})

test('actual content stays visible with reduced motion, unsupported/failed observers and an in-session preference change', () => {
  const html = '<section data-public-reveal="" class="about-mission"></section>'
  for (const options of [{ reduced: true }, { fail: true }]) {
    const root = renderedDOM(html); const state = observerEnvironment(options); installPublicReveal(root, state.environment)
    state.flushFrames(); assert.equal(root.querySelectorAll('[data-public-reveal]')[0].names.has('public-reveal--pending'), false)
    assert.equal(root.querySelectorAll('[data-public-reveal]')[0].names.has('public-reveal--shown'), false)
  }
  const unsupported = renderedDOM(html); installPublicReveal(unsupported, {})
  assert.equal(unsupported.querySelectorAll('[data-public-reveal]')[0].names.has('public-reveal--pending'), false)
  const root = renderedDOM(html); const state = observerEnvironment(); const cleanup = installPublicReveal(root, state.environment)
  state.changePreference(); state.flushFrames()
  assert.equal(state.observed.size, 0); const target = root.querySelectorAll('[data-public-reveal]')[0]
  assert.equal(target.names.has('public-reveal--pending'), false); assert.equal(target.styles.has('--reveal-delay'), false); cleanup()
})

test('the actual public layout mounts motion only on marketing routes; live exam and Quick access markup have no reveal targets', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  try {
    const { default: PublicLayout } = await server.ssrLoadModule('/src/layouts/PublicLayout.jsx')
    const { default: StudentExamPage } = await server.ssrLoadModule('/src/pages/student/StudentExamPage.jsx')
    const { QuickCredentialForm } = await server.ssrLoadModule('/src/pages/public/QuickExamPages.jsx')
    for (const path of ['/', '/features', '/how-it-works', '/pricing', '/about', '/contact', '/take-exam/attempt/31', '/take-exam', '/signin', '/setup']) {
      const content = path.includes('/attempt/') ? React.createElement(StudentExamPage) : React.createElement(QuickCredentialForm)
      const route = React.createElement(Route, { element: React.createElement(PublicLayout) }, React.createElement(Route, { path: '*', element: content }))
      const html = renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: [path] }, React.createElement(Routes, null, route)))
      const marketing = ['/', '/features', '/how-it-works', '/pricing', '/about', '/contact'].includes(path)
      assert.equal(html.includes('public-layout--marketing'), marketing)
      assert.equal(html.includes('data-public-motion=""'), marketing, `${path}: the real mounted motion wrapper receives its enabled state`)
      assert.doesNotMatch(html, /data-public-reveal|public-reveal--pending/)
      if (path.includes('/attempt/')) assert.match(html, /public-layout--exam/)
    }
    const portal = renderToStaticMarkup(React.createElement(MemoryRouter, { initialEntries: ['/student/exam/31'] }, React.createElement(Routes, null, React.createElement(Route, { path: '/student/exam/:attemptId', element: React.createElement(StudentExamPage) }))))
    assert.doesNotMatch(portal, /public-marketing-motion|data-public-reveal|public-reveal/)
  } finally { await server.close() }
})

test('public typography tokens replace existing desktop/mobile declarations and polish CSS is the final app stylesheet import', async () => {
  const main = await readFile(new URL('../src/main.jsx', import.meta.url), 'utf8')
  const imports = [...main.matchAll(/import '([^']+\.css)'/g)].map(match => match[1])
  assert.equal(imports.at(-1), './styles/public-polish.css')
  const layout = postcss.parse(await readFile(new URL('../src/styles/layouts.css', import.meta.url), 'utf8'))
  const landing = postcss.parse(await readFile(new URL('../src/pages/public/landing.css', import.meta.url), 'utf8'))
  const publicPages = postcss.parse(await readFile(new URL('../src/pages/public/public-pages.css', import.meta.url), 'utf8'))
  function values(sheet, selector, property) {
    const found = []; sheet.walkRules(rule => { if (rule.selectors.includes(selector)) rule.walkDecls(property, declaration => found.push(declaration.value)) }); return found
  }
  assert.deepEqual(values(layout, '.public-layout', '--public-copy-size'), ['clamp(1.0625rem, calc(1rem + .15vw), 1.125rem)'])
  assert.deepEqual(values(layout, '.public-layout', '--public-card-copy-size'), ['1rem'])
  assert.deepEqual(values(layout, '.public-nav a', 'font-size'), ['1rem'])
  assert.deepEqual(values(layout, '.public-footer__column a', 'font-size'), ['var(--public-support-size)'])
  for (const [sheet, selectors, token] of [
    [landing, ['.landing-hero__description', '.landing-section__heading > p:last-child'], '--public-copy-size'],
    [landing, ['.landing-card p', '.landing-step p', '.landing-plan li'], '--public-card-copy-size'],
    [publicPages, ['.features-detail__subtitle', '.features-hero__inner > p', '.workflow-hero__copy > p', '.auth-form-wrap .public-page-intro p', '.setup-form-heading p'], '--public-copy-size'],
    [publicPages, ['.features-audience-card p', '.pricing-card li', '.about-metric p', '.about-future-grid p'], '--public-card-copy-size'],
  ]) for (const selector of selectors) { const declarations = values(sheet, selector, 'font-size'); assert.ok(declarations.length); assert.ok(declarations.every(value => value === `var(${token})`), `${selector}: no later mobile rule shrinks it`) }
  const polish = postcss.parse(await readFile(new URL('../src/styles/public-polish.css', import.meta.url), 'utf8'))
  assert.equal(values(polish, '.public-reveal--pending', 'transform')[0], 'translateY(20px)')
  assert.match(values(polish, '.public-reveal--shown', 'transition')[0], /600ms/)
  assert.ok(polish.nodes.some(node => node.type === 'atrule' && node.params === '(prefers-reduced-motion: reduce)'))
})
