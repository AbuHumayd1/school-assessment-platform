import test from 'node:test'
import assert from 'node:assert/strict'
import { readFile } from 'node:fs/promises'
import { dismissDrawerBackdrop, dismissDrawerCancel, lockDrawerScroll } from '../src/utils/drawer.js'

test('backdrop click closes; inside controls and drawer padding do not', () => {
  let closes = 0
  const dialog = { close: () => closes++, getBoundingClientRect: () => ({ left: 20, right: 320, top: 0, bottom: 700 }) }
  dismissDrawerBackdrop({ target: dialog, currentTarget: dialog, clientX: 400, clientY: 100 })
  assert.equal(closes, 1)
  dismissDrawerBackdrop({ target: {}, currentTarget: dialog, clientX: 100, clientY: 100 })
  dismissDrawerBackdrop({ target: dialog, currentTarget: dialog, clientX: 100, clientY: 100 })
  assert.equal(closes, 1)
  // The same bounds-based behavior applies to right-positioned RTL drawers.
  dismissDrawerBackdrop({ target: dialog, currentTarget: dialog, clientX: 0, clientY: 100 })
  assert.equal(closes, 2)
})
test('Escape cancel closes once and prevents default native duplicate closing', () => {
  let closes = 0, prevented = false
  dismissDrawerCancel({ preventDefault: () => { prevented = true }, currentTarget: { close: () => closes++ } })
  assert.equal(closes, 1); assert.equal(prevented, true)
})
test('background scrolling is locked and original overflow restored', () => {
  const body = { style: { overflow: 'auto' } }
  const unlock = lockDrawerScroll(body)
  assert.equal(body.style.overflow, 'hidden')
  unlock(); assert.equal(body.style.overflow, 'auto')
})
test('shared drawer keeps explicit close and navigation selection dismissal wired', async () => {
  const drawer = await readFile(new URL('../src/components/common/Drawer.jsx', import.meta.url), 'utf8')
  assert.match(drawer, /onClose=\{onClose\}/)
  assert.match(drawer, /onClick=\{dismissDrawerBackdrop\}/)
  assert.match(drawer, /onCancel=\{dismissDrawerCancel\}/)
  assert.match(drawer, /onClick=\{\(\) => dialogRef.current\?\.close\(\)\}/)
  for (const layout of ['Public', 'Staff', 'Student']) {
    const source = await readFile(new URL(`../src/layouts/${layout}Layout.jsx`, import.meta.url), 'utf8')
    assert.match(source, /onNavigate=\{closeMenu\}/)
    assert.match(source, /onClose=\{closeMenu\}/)
  }
})
