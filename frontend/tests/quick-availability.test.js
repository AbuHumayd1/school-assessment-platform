import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter } from 'react-router-dom'
import { createServer } from 'vite'
import { quickExamTranslate } from '../src/utils/quickExamLocale.js'

test('Quick instructions show safe server reasons and Lagos times independently of browser timezone', async () => {
  const originalTimezone = process.env.TZ
  process.env.TZ = 'UTC'
  const server = await createServer({ server: { middlewareMode: true, hmr: false }, appType: 'custom', optimizeDeps: { noDiscovery: true, include: [] } })
  try {
    const { QuickInstructionsView } = await server.ssrLoadModule('/src/pages/public/QuickExamPages.jsx')
    const render = (availability, locale = 'en') => renderToStaticMarkup(React.createElement(MemoryRouter, null,
      React.createElement(QuickInstructionsView, { locale, t: text => quickExamTranslate(locale, text), session: {
        candidate: { candidate_id: 'SYNTHETIC-001', first_name: 'Test' },
        assessment: { title: 'Synthetic exam', timezone: 'Africa/Lagos', duration_minutes: 5, question_count: 10,
          start_at: '2026-10-07T10:00:00Z', end_at: '2026-10-07T11:00:00Z' },
        availability: { state: 'unavailable', can_start: false, can_resume: false, attempts_remaining: 2, ...availability },
      } })))
    const reasons = { upcoming: 'Exam has not started yet.', ended: 'Exam has ended.', not_open: 'Exam is not open for candidates.',
      not_eligible: 'Candidate is not eligible.', not_ready: 'Exam is not ready for candidates.',
      attempt_limit_reached: 'No attempts remaining.', resume_disabled: 'This exam cannot be resumed.' }
    for (const [reason, message] of Object.entries(reasons)) {
      for (const locale of ['en', 'ar']) {
        const html = render({ reason, message: 'Private database detail' }, locale)
        assert.ok(html.includes(quickExamTranslate(locale, message)))
        assert.ok(!html.includes('Private database detail'))
        assert.doesNotMatch(html, /<button/)
      }
    }
    const draft = render({ reason: 'not_open' })
    assert.match(draft, /11:00 AM/)
    assert.match(draft, /12:00 PM/)
    const available = render({ state: 'available', reason: null, can_start: true })
    assert.match(available, /Ready to start/)
    assert.match(available, /Start examination/)
    const unknown = render({ reason: 'private_internal_code', message: 'Private database detail' })
    assert.match(unknown, /Examination unavailable/)
    assert.doesNotMatch(unknown, /Private database detail|private_internal_code/)
    const resume = render({ state: 'in_progress', can_resume: true, reason: null })
    assert.match(resume, /Resume examination/)
  } finally {
    await server.close()
    if (originalTimezone === undefined) delete process.env.TZ
    else process.env.TZ = originalTimezone
  }
})
