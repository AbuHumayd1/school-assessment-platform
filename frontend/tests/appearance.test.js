import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import vm from 'node:vm'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { initialTheme, applyTheme, THEME_KEY } from '../src/utils/theme.js'
import { readPublicLocale, persistInterfaceLanguage, PUBLIC_LANGUAGE_KEY, WORKSPACE_LANGUAGE_KEY } from '../src/utils/interfaceLanguage.js'
import { installHeroRotation, heroAudiences, HERO_INTERVAL } from '../src/utils/heroRotation.js'

function environment(preference = null, systemDark = false) {
  const values = new Map(preference ? [[THEME_KEY, preference]] : [])
  return { localStorage: { getItem: key => values.get(key), setItem: (key, value) => values.set(key, value) }, matchMedia: () => ({ matches: systemDark }), document: { documentElement: { dataset: {}, style: {} } }, values }
}
test('theme defaults to light regardless of system, preserving explicit light/dark choices', () => {
  assert.equal(initialTheme(environment(null, true)), 'light')
  assert.equal(initialTheme(environment(null, false)), 'light')
  assert.equal(initialTheme(environment('light', true)), 'light')
  assert.equal(initialTheme(environment('dark', false)), 'dark')
  const env = environment(); applyTheme('dark', env, true)
  assert.equal(env.document.documentElement.dataset.theme, 'dark')
  assert.equal(env.document.documentElement.style.colorScheme, 'dark')
  assert.equal(env.localStorage.getItem(THEME_KEY), 'dark')
  assert.equal(initialTheme(env), 'dark')
  applyTheme('light', env, true); assert.equal(initialTheme(env), 'light')
  const blocked = { matchMedia: () => ({ matches: true }), get localStorage() { throw new Error('Storage unavailable') } }
  assert.equal(initialTheme(blocked), 'light')
})
test('pre-React initializer matches persisted and system theme before mounting React', async () => {
  const source = await readFile(new URL('../public/theme-init.js', import.meta.url), 'utf8')
  for (const [preference, system, expected] of [['dark', false, 'dark'], ['light', true, 'light'], [null, true, 'light'], [null, false, 'light']]) {
    const env = environment(preference, system); vm.runInNewContext(source, { ...env, window: env })
    assert.equal(env.document.documentElement.dataset.theme, expected)
  }
})
test('language retains existing storage keys and persists document lang/dir independently of authored data', () => {
  const env = environment()
  persistInterfaceLanguage('ar', 'arabic', env)
  assert.equal(readPublicLocale(env.localStorage), 'ar')
  assert.equal(env.values.get(PUBLIC_LANGUAGE_KEY), 'ar')
  assert.equal(env.values.get(WORKSPACE_LANGUAGE_KEY), 'arabic')
  assert.equal(env.document.documentElement.lang, 'ar')
  assert.equal(env.document.documentElement.dir, 'rtl')
  persistInterfaceLanguage('en', 'english', env)
  assert.equal(env.document.documentElement.lang, 'en')
  assert.equal(env.document.documentElement.dir, 'ltr')
})
test('hero advances every 4500ms and cancels its timer for reduced motion and unmount', () => {
  let callback, duration, change, advances = 0, clears = 0
  const media = { matches: false, addEventListener: (_, fn) => { change = fn }, removeEventListener() {} }
  const env = { matchMedia: () => media, setInterval: (fn, ms) => { callback = fn; duration = ms; return 1 }, clearInterval: () => clears++ }
  const cleanup = installHeroRotation(env, () => advances++)
  assert.equal(duration, 4500); assert.equal(HERO_INTERVAL, 4500)
  assert.deepEqual(heroAudiences, ['Built for Schools', 'Built for Madrasahs', 'Built for Training Programmes', 'Built for Professional Examinations', 'Built for Competitions', 'Built for Educational Institutes', 'Built for Organisations'])
  callback(); callback(); assert.equal(advances, 2)
  media.matches = true; change(); assert.equal(clears, 1)
  let scheduled = false
  installHeroRotation({ ...env, setInterval: () => { scheduled = true } }, () => {})()
  assert.equal(scheduled, false)
  cleanup()
})
test('theme switch labels work in Arabic and English, logo supports monochrome, favicon uses the mark', async () => {
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  try {
    const { default: Switch } = await server.ssrLoadModule('/src/components/common/ThemeSwitch.jsx')
    const { ThemeProvider } = await server.ssrLoadModule('/src/context/ThemeContext.jsx')
    const { default: Mark } = await server.ssrLoadModule('/src/components/common/MadaarMark.jsx')
    const { LanguageModeProvider } = await server.ssrLoadModule('/src/context/LanguageModeContext.jsx')
    for (const locale of ['ar', 'en']) {
      const html = renderToStaticMarkup(React.createElement(LanguageModeProvider, null, React.createElement(ThemeProvider, null, React.createElement(Switch, { locale }))))
      assert.match(html, /type="button"/)
      assert.ok(html.includes(locale === 'ar' ? 'تفعيل المظهر الداكن' : 'Switch to dark mode'))
    }
    const normal = renderToStaticMarkup(React.createElement(Mark))
    assert.match(normal, /C8A85B/); assert.match(normal, /aria-hidden="true"/)
    assert.doesNotMatch(renderToStaticMarkup(React.createElement(Mark, { monochrome: true })), /C8A85B/)
    const index = await readFile(new URL('../index.html', import.meta.url), 'utf8')
    assert.match(index, /madaar-mark\.svg/)
    assert.ok(index.indexOf('theme-init.js') < index.indexOf('/src/main.jsx'))
  } finally { await server.close() }
})
