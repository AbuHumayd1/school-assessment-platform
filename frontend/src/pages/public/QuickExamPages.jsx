import ThemeSwitch from '../../components/common/ThemeSwitch.jsx'
import MadaarMark from '../../components/common/MadaarMark.jsx'
import { createContext, useCallback, useContext, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react'
import { Link, Navigate, Outlet, useLocation, useNavigate } from 'react-router-dom'
import Button from '../../components/common/Button.jsx'
import StudentExamPage from '../student/StudentExamPage.jsx'
import { PublicLanguageSwitcher, PublicLocaleProvider, PublicLocaleTree, usePublicLocale } from '../../context/PublicLocaleContext.jsx'
import { apiFetch } from '../../services/api.js'
import { clearQuickAttempt, createExamAdapter, endQuickAccess, endQuickAccessBeforeStart, getQuickAttemptPath, loadQuickAccess, rememberQuickAttempt, startQuickAccess, verifyQuickAccess } from '../../services/examAdapters.js'
import { quickExamTranslate } from '../../utils/quickExamLocale.js'
import { createQuickTabOwner } from '../../utils/quickTabOwnership.js'
import '../../styles/quick-exam.css'
import ImmediateScore from '../../components/student/ImmediateScore.jsx'

const AccessContext = createContext(null)
const failure = 'We could not complete this request. Check your connection and try again.'
const expired = 'Your access has expired. Verify your details again to continue.'
export function quickVerificationError(error) {
  return error.status === 401 && error.data?.detail === 'The exam details or access credentials are incorrect.'
    ? 'We could not verify these details. Check them and try again.' : failure
}
function useCopy() { const { locale } = usePublicLocale(); return useCallback(text => quickExamTranslate(locale, text), [locale]) }

function AccessProvider({ children }) {
  const [session, setSession] = useState(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(false)
  const refresh = useCallback(async () => {
    setLoading(true); setError(false)
    try { const context = await loadQuickAccess(apiFetch); setSession(context); return context }
    catch { setError(true); return null }
    finally { setLoading(false) }
  }, [])
  useEffect(() => { refresh() }, [refresh])
  return <AccessContext.Provider value={{ session, loading, error, refresh }}>{children}</AccessContext.Provider>
}

let quickClient = null

function useQuickClient() {
  const [owner, setOwner] = useState(null)
  const [phase, setPhase] = useState('checking')
  useEffect(() => {
    const client = createQuickTabOwner(window, () => { clearQuickAttempt(); setPhase('inactive') })
    quickClient = client; setOwner(client)
    return () => { client.dispose(); if (quickClient === client) quickClient = null }
  }, [])
  return { owner, phase, setPhase }
}

export function QuickClientNotice({ t = text => text, expiredAccess = false, inactive = false, onTakeover, busy = false }) {
  return <section className="quick-client-notice" role="alert">
    <h1>{t(expiredAccess ? 'Examination access unavailable' : inactive ? 'This page is no longer the active examination tab.' : 'This examination is already open in another tab.')}</h1>
    <p>{t(expiredAccess ? 'Your examination access is no longer available. It may have been opened elsewhere. Verify your details again to continue.' : inactive ? 'This page cannot make changes. Continue here to recover the same attempt with its original deadline.' : 'This page cannot make changes while another tab is active. You can take over and continue the same attempt with its existing deadline.')}</p>
    <div className="quick-client-notice__actions"><Button as={Link} to="/take-exam" variant="outline">{t('Return to exam access')}</Button>{!expiredAccess && onTakeover && <Button onClick={onTakeover} loading={busy}>{t('Take over this exam')}</Button>}</div>
  </section>
}

export function QuickExamFrame({ session, live = false, complete = false, t = text => text, endBusy, endError, onEnd, children }) {
  const candidate = session?.candidate
  return <div className={`quick-exam-layout${live ? ' quick-exam-layout--live public-layout--exam' : ''}`}>
    {!live && <header className="quick-exam-header">
      <div className="quick-exam-header__brand"><span className="wordmark__mark" aria-hidden="true"><MadaarMark /></span><span>{t('Powered by Madaar')}</span></div>
      {session && <div className="quick-exam-header__context"><strong dir="auto">{session.assessment.title}</strong><span dir="auto">{[candidate.first_name, candidate.last_name].filter(Boolean).join(' ')} <bdi>{candidate.candidate_id}</bdi></span></div>}
      <div className="quick-exam-header__actions"><ThemeSwitch locale={t('Take an Exam') === 'Take an Exam' ? 'en' : 'ar'} /><PublicLanguageSwitcher />{session && !complete && session.availability.state !== 'in_progress' && <Button variant="outline" loading={endBusy} onClick={onEnd}>{t('End Session')}</Button>}</div>
    </header>}
    <main className={live ? 'public-main' : 'quick-exam-main'}>{endError && <p role="alert">{endError}</p>}{children}</main>
  </div>
}

function VerifiedEnvironment() {
  const { pathname } = useLocation(); const navigate = useNavigate(); const t = useCopy()
  const { session, refresh } = useContext(AccessContext)
  const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  async function end() {
    if (busy) return
    setBusy(true); setError('')
    try {
      // Recheck a stale pre-start briefing before ending shared browser access.
      if (!await endQuickAccessBeforeStart(apiFetch)) { await refresh(); return }
      clearQuickAttempt(); navigate('/take-exam', { replace: true })
    } catch { setError(t(failure)) } finally { setBusy(false) }
  }
  return <QuickExamFrame session={session} live={pathname.includes('/attempt/')} complete={pathname.endsWith('/complete')} t={t} endBusy={busy} endError={error} onEnd={end}><Outlet /></QuickExamFrame>
}

export function QuickExamLayout() {
  const { pathname } = useLocation()
  return <PublicLocaleProvider><PublicLocaleTree><AccessProvider key={pathname}><VerifiedEnvironment /></AccessProvider></PublicLocaleTree></PublicLocaleProvider>
}

function AccessGate({ children }) {
  const { session, loading, error, refresh } = useContext(AccessContext)
  const t = useCopy()
  if (loading) return <p className="quick-exam-status" role="status">{t('Loading examination information...')}</p>
  if (error) return <section className="quick-exam-panel"><p role="alert">{t(failure)}</p><Button onClick={refresh}>{t('Retry')}</Button></section>
  if (!session) { clearQuickAttempt(); return <Navigate to="/take-exam" replace state={{ reverify: true, accessLost: true }} /> }
  return children
}

export function QuickCredentialForm({ t = text => text, busy = false, error = '', onSubmit }) {
  const [showPin, setShowPin] = useState(false)
  return <form className="quick-exam-form" onSubmit={onSubmit}>
    <label htmlFor="quick-code">{t('Exam Code')}</label><input id="quick-code" name="exam_code" placeholder={t("Exam Code")} aria-describedby={error ? "quick-access-error" : undefined} aria-invalid={Boolean(error)} required autoComplete="off" autoCapitalize="characters" dir="ltr" disabled={busy} />
    <label htmlFor="quick-candidate">{t('Candidate ID')}</label><input id="quick-candidate" name="candidate_id" placeholder={t("Candidate ID")} aria-describedby={error ? "quick-access-error" : undefined} aria-invalid={Boolean(error)} required autoComplete="off" dir="auto" disabled={busy} />
    <label htmlFor="quick-pin">{t('Access PIN')}</label><div className="quick-exam-pin"><input id="quick-pin" name="pin" type={showPin ? 'text' : 'password'} placeholder={t("Access PIN")} aria-describedby={error ? "quick-access-error" : undefined} aria-invalid={Boolean(error)} required autoComplete="off" dir="ltr" disabled={busy} /><button type="button" aria-controls="quick-pin" aria-pressed={showPin} onClick={() => setShowPin(value => !value)}>{t(showPin ? 'Hide PIN' : 'Show PIN')}</button></div>
    {error && <p id="quick-access-error" role="alert">{error}</p>}<Button type="submit" loading={busy}>{t('Continue')}</Button>
  </form>
}

export function QuickEntryPage() {
  const t = useCopy(); const navigate = useNavigate(); const { state } = useLocation()
  const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  async function verify(event) {
    event.preventDefault(); if (busy) return; const form = event.currentTarget; const data = new FormData(form)
    setBusy(true); setError('')
    try {
      await verifyQuickAccess(apiFetch, { exam_code: String(data.get('exam_code')), candidate_id: String(data.get('candidate_id')), pin: String(data.get('pin')) })
      form.reset(); navigate('/take-exam/instructions')
    } catch (requestError) { setError(t(quickVerificationError(requestError))) }
    finally { setBusy(false) }
  }
  return <section className="quick-exam-entry" aria-labelledby="quick-entry-title">
    <div className="quick-exam-entry__copy">
      <h1 id="quick-entry-title">{t('Take an Exam')}</h1>
      <p className="quick-exam-entry__description">{t('Enter the examination details provided by your institution or examination organiser.')}</p>
      <p className="quick-exam-entry__reassurance">{t('You will review the examination details and instructions before your timer begins.')}</p>
      <Link to="/">{t('Back to website')}</Link>
    </div>
    <div className="quick-exam-entry__card">
      <h2>{t('Ready to begin?')}</h2>
      {state?.reverify && <p role="status">{t(state.accessLost ? 'Your examination access is no longer available. It may have been opened elsewhere. Verify your details again to continue.' : expired)}</p>}
      <QuickCredentialForm t={t} busy={busy} error={error} onSubmit={verify} />
    </div>
  </section>
}

const availabilityLabels = { available: 'Ready to start', in_progress: 'Resume available', upcoming: 'Not yet available', ended: 'Examination window ended', attempt_limit_reached: 'No attempts remaining', unavailable: 'Examination unavailable' }
const availabilityReasons = {
  upcoming: 'Exam has not started yet.', ended: 'Exam has ended.',
  not_open: 'Exam is not open for candidates.', not_eligible: 'Candidate is not eligible.',
  not_ready: 'Exam is not ready for candidates.', attempt_limit_reached: 'No attempts remaining.',
  resume_disabled: 'This exam cannot be resumed.',
}
export function QuickInstructionsView({ session, t = text => text, locale = 'en', busy, error, onStart }) {
  const { candidate, assessment, availability } = session
  const date = value => value ? new Intl.DateTimeFormat(locale, { dateStyle: 'medium', timeStyle: 'short', timeZone: assessment.timezone || undefined }).format(new Date(value)) : null
  const facts = [['Candidate', [candidate.first_name, candidate.last_name].filter(Boolean).join(' ') || candidate.candidate_id], ['Candidate ID', candidate.candidate_id], ['Duration', t(`${assessment.duration_minutes} min`)], ['Questions', assessment.question_count], ['Attempts remaining', availability.attempts_remaining], ['Starts', date(assessment.start_at)], ['Ends', date(assessment.end_at)]]
  const resumable = availability.state === 'in_progress'
  return <section className="quick-exam-briefing" aria-labelledby="quick-briefing-title">
    <div className="quick-exam-briefing__heading"><p className="quick-exam-briefing__eyebrow">{t('Examination briefing')}</p><h1 id="quick-briefing-title" dir="auto">{assessment.title}</h1><p className="quick-exam-briefing__status" role="status">{t(availabilityReasons[availability.reason] || (resumable && !availability.can_resume ? 'This exam cannot be resumed.' : availabilityLabels[availability.state] || 'Examination unavailable'))}</p></div>
    <div className="quick-exam-briefing__grid">
      <article className="quick-exam-briefing__guidance"><h2>{t('Examination instructions')}</h2>{assessment.description && <p className="quick-exam-briefing__description" dir="auto">{assessment.description}</p>}
        <ul><li>{t('Read each question carefully. Answers save automatically.')}</li><li>{t('Stay on the examination page. Leaving is recorded and repeated interruptions may submit your attempt.')}</li></ul>
        <p className="quick-exam-briefing__timer">{t(resumable ? 'An existing attempt keeps its original deadline when resumed.' : 'Your examination timer will begin when you select Start Exam.')}</p>
      </article>
      <aside className="quick-exam-briefing__summary"><h2>{t('Examination summary')}</h2><dl>{facts.filter(([, value]) => value !== null && value !== undefined).map(([label, value]) => <div key={label}><dt>{t(label)}</dt><dd dir="auto">{value}</dd></div>)}</dl></aside>
    </div>
    <div className="quick-exam-briefing__actions">{error && <p role="alert">{error}</p>}{(availability.can_start || availability.can_resume) && <Button loading={busy} onClick={onStart}>{t(availability.can_resume ? 'Resume examination' : 'Start examination')}</Button>}</div>
  </section>
}

function Instructions() {
  const { session, refresh } = useContext(AccessContext); const t = useCopy(); const { locale } = usePublicLocale(); const navigate = useNavigate()
  const { owner, phase, setPhase } = useQuickClient()
  const [busy, setBusy] = useState(false); const [error, setError] = useState('')
  async function start(takeover = false) {
    if (busy || !owner) return
    setBusy(true); setError('')
    try {
      if (!await owner.claim({ takeover })) { setPhase('blocked'); return }
      const attempt = await startQuickAccess((path, options) => owner.request(apiFetch, path, options))
      if (owner.isOwner()) navigate(`/take-exam/attempt/${attempt.id}`)
    } catch (requestError) {
      owner.release()
      if (requestError.status === 401) { clearQuickAttempt(); setPhase('expired') }
      else if (requestError.code !== 'quick_client_inactive') {
        setError(t(availabilityReasons[requestError.data?.reason] || failure))
        if ([400, 403].includes(requestError.status)) await refresh()
      }
    } finally { setBusy(false) }
  }
  if (['blocked', 'inactive', 'expired'].includes(phase)) return <QuickClientNotice t={t} expiredAccess={phase === 'expired'} inactive={phase === 'inactive'} onTakeover={() => start(true)} busy={busy} />
  return <QuickInstructionsView session={session} t={t} locale={locale} busy={busy || !owner} error={error} onStart={() => start()} />
}
export function QuickInstructionsPage() { return <AccessGate><Instructions /></AccessGate> }

function RunnerClient({ owner, onExpired }) {
  const navigate = useNavigate(); const t = useCopy()
  const copyRef = useRef(t); copyRef.current = t
  const request = useCallback((path, options) => owner.request(apiFetch, path, options), [owner])
  const api = useMemo(() => ({ ...createExamAdapter(request, { mode: 'quick', onAccessExpired: onExpired, errorMessage: () => copyRef.current(failure) }), backPath: '/take-exam/instructions', backLabel: 'Back to instructions', rememberPath: id => rememberQuickAttempt(`/take-exam/attempt/${id}`), clearPath: clearQuickAttempt }), [request, onExpired])
  const terminal = useCallback(() => { clearQuickAttempt(); owner.release(); navigate('/take-exam/complete', { replace: true }) }, [navigate, owner])
  return <StudentExamPage api={api} translate={t} onTerminal={terminal} headerControl={<PublicLanguageSwitcher />} />
}
function Runner() {
  const t = useCopy(); const { owner, phase, setPhase } = useQuickClient()
  const expire = useCallback(() => { clearQuickAttempt(); owner?.release(); setPhase('expired') }, [owner, setPhase])
  const acquire = useCallback(async (takeover = false) => {
    if (!owner) return
    setPhase('checking')
    try {
      const acquired = await owner.claim({ takeover })
      if (!acquired) { setPhase('blocked'); return }
      const context = await loadQuickAccess((path, options) => owner.request(apiFetch, path, options))
      if (!context) expire()
      else if (owner.isOwner()) setPhase('active')
    } catch { const lost = !owner.isOwner(); owner.release(); setPhase(lost ? 'inactive' : 'retry') }
  }, [owner, setPhase, expire])
  useEffect(() => { if (owner) acquire() }, [owner, acquire])
  useEffect(() => {
    const recover = event => { if (event.persisted) acquire() }
    window.addEventListener('pageshow', recover)
    return () => window.removeEventListener('pageshow', recover)
  }, [acquire])
  if (phase === 'active') return <RunnerClient owner={owner} onExpired={expire} />
  if (phase === 'checking') return <p className="quick-exam-status" role="status">{t('Loading examination information...')}</p>
  if (phase === 'retry') return <section className="quick-client-notice"><p role="alert">{t(failure)}</p><Button onClick={() => acquire()}>{t('Retry')}</Button></section>
  return <QuickClientNotice t={t} expiredAccess={phase === 'expired'} inactive={phase === 'inactive'} onTakeover={() => acquire(true)} />
}
export function QuickAttemptPage() { return <AccessGate><Runner /></AccessGate> }

export function QuickCompletionView({ status, score, t = text => text, busy, error, onDone }) {
  return <section className="quick-exam-completion"><p>{t('Submission received')}</p><h1>{t(status === 'expired' ? 'Time’s Up' : score ? 'Exam submitted successfully' : 'Exam Submitted')}</h1><p>{t('Your saved answers have been received. Your institution will provide result information.')}</p><ImmediateScore score={['submitted', 'expired'].includes(status) ? score : null} t={t} />{error && <p role="alert">{error}</p>}<Button onClick={onDone} loading={busy}>{t('Done')}</Button></section>
}
function Completion() {
  const t = useCopy(); const navigate = useNavigate(); const [status, setStatus] = useState(null); const [score, setScore] = useState(null); const [error, setError] = useState(''); const [busy, setBusy] = useState(false)
  const check = useCallback(async () => {
    setError('')
    try { const attempt = await apiFetch('quick-exam/attempt/'); if (['submitted', 'expired'].includes(attempt.status)) { setStatus(attempt.status); setScore(attempt.immediate_score) } else navigate('/take-exam/instructions', { replace: true }) }
    catch (requestError) { if (requestError.status === 401) navigate('/take-exam', { replace: true, state: { reverify: true } }); else if (requestError.status === 404) navigate('/take-exam/instructions', { replace: true }); else setError(t(failure)) }
  }, [navigate, t])
  useEffect(() => { check() }, [check])
  async function done() { setBusy(true); setError(''); try { await endQuickAccess(apiFetch); clearQuickAttempt(); navigate('/take-exam', { replace: true }) } catch { setError(t(failure)) } finally { setBusy(false) } }
  if (!status) return <section className="quick-exam-panel"><p role={error ? 'alert' : 'status'}>{error || t('Loading examination information...')}</p>{error && <Button onClick={check}>{t('Retry')}</Button>}</section>
  return <QuickCompletionView status={status} score={score} t={t} busy={busy} error={error} onDone={done} />
}
export function QuickCompletePage() { return <AccessGate><Completion /></AccessGate> }

export function QuickAttemptNavigationGuard() {
  const { pathname } = useLocation(); const navigate = useNavigate()
  useLayoutEffect(() => {
    const path = getQuickAttemptPath(); const match = path?.match(/^\/take-exam\/attempt\/(\d+)$/)
    if (!match || pathname === path) return
    if (!quickClient?.isOwner()) { clearQuickAttempt(); return }
    const owner = quickClient
    const api = createExamAdapter((route, options) => owner.request(apiFetch, route, options), { mode: 'quick', onAccessExpired: () => { clearQuickAttempt(); navigate('/take-exam', { replace: true, state: { reverify: true, accessLost: true } }) } })
    api.recordAttemptIntegrity(match[1], 'navigation_attempt').then(state => {
      if (state.attempt_status && state.attempt_status !== 'in_progress') { clearQuickAttempt(); navigate('/take-exam/complete', { replace: true }); return }
      window.dispatchEvent(new CustomEvent('attempt-integrity-updated', { detail: { attemptId: match[1], accessMode: 'quick', state } }))
    }).catch(() => {})
    navigate(path, { replace: true })
  }, [pathname, navigate])
  return null
}
