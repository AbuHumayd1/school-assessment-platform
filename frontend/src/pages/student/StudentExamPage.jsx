import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import Button from '../../components/common/Button.jsx'
import Card from '../../components/common/Card.jsx'
import Icon from '../../components/common/Icon.jsx'
import LoadingState from '../../components/common/LoadingState.jsx'
import Modal from '../../components/common/Modal.jsx'
import { ExamTimer, QuestionNavigator, QuestionRenderer, StudentEmptyState } from '../../components/student/StudentComponents.jsx'
import * as portalApi from '../../services/attempts.js'

const identity = text => text
const portalRunner = { ...portalApi, mode: 'portal', backPath: '/student/exams', backLabel: 'Back to My Exams', rememberPath: id => portalApi.rememberActiveAttempt(`/student/exam/${id}`), clearPath: portalApi.clearRememberedAttempt }

export default function StudentExamPage({ api = portalRunner, translate = identity, onTerminal, headerControl }) {
  const t = translate
  const { getAttempt, getAttemptIntegrity, getAttemptQuestion, getAttemptQuestions, recordAttemptIntegrity, saveAttemptAnswer, setAttemptReview, submitAttempt } = api
  const clearRememberedAttempt = api.clearPath
  const { attemptId } = useParams()
  const [attempt, setAttempt] = useState(null)
  const [questions, setQuestions] = useState([])
  const [current, setCurrent] = useState(0)
  const [question, setQuestion] = useState(null)
  const [answers, setAnswers] = useState({})
  const [marked, setMarked] = useState(() => new Set())
  const [seconds, setSeconds] = useState(0)
  const [expiryFinalizing, setExpiryFinalizing] = useState(false)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [loading, setLoading] = useState(true)
  const [questionLoading, setQuestionLoading] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState('')
  const [saveError, setSaveError] = useState('')
  const [saveState, setSaveState] = useState({})
  const [integrity, setIntegrity] = useState(null)
  const [integrityError, setIntegrityError] = useState('')
  const [leaveWarning, setLeaveWarning] = useState(false)
  const [clock, setClock] = useState(null)
  const answerValuesRef = useRef({})
  const answerRevisionRef = useRef({})
  const dirtyQuestionsRef = useRef(new Set())
  const saveQueuesRef = useRef(new Map())
  const questionRequestRef = useRef(0)
  const expirySyncRef = useRef(false)
  const hiddenTimerRef = useRef(null)
  const hiddenRef = useRef(false)
  const blurredRef = useRef(false)
  const unloadingRef = useRef(false)
  const signalTimesRef = useRef(new Map())

  const answeredCount = useMemo(() => questions.filter((item, index) => item.answered || (answers[index]?.length > 0)).length, [questions, answers])
  const markedCount = questions.filter((item, index) => marked.has(index) || item.marked_for_review).length
  const attemptStatus = attempt?.status

  const applyServerClock = useCallback(payload => {
    const serverEpoch = new Date(payload.server_time).getTime()
    if (!Number.isFinite(serverEpoch)) return
    const offsetMs = serverEpoch - Date.now()
    const expiresServerEpoch = serverEpoch + Math.max(0, payload.remaining_seconds) * 1000
    setClock({ offsetMs, expiresServerEpoch })
    setSeconds(Math.max(0, Math.floor((expiresServerEpoch - (Date.now() + offsetMs)) / 1000)))
  }, [])

  const refreshAttempt = useCallback(async () => {
    const payload = await getAttempt(attemptId)
    setAttempt(payload)
    if (payload.status === 'in_progress') {
      applyServerClock(payload)
      if (payload.remaining_seconds > 0) {
        expirySyncRef.current = false
        setExpiryFinalizing(false)
      } else setExpiryFinalizing(true)
    }
    else {
      setSeconds(0)
      setExpiryFinalizing(false)
      clearRememberedAttempt(attemptId)
    }
    return payload
  }, [attemptId, applyServerClock, api])

  const applyIntegrityState = useCallback(payload => {
    setIntegrity(payload)
    setIntegrityError('')
    if (payload.attempt_status && payload.attempt_status !== 'in_progress') {
      setAttempt(previous => previous ? { ...previous, status: payload.attempt_status } : previous)
      setSeconds(0)
      clearRememberedAttempt(attemptId)
    }
  }, [attemptId, api])

  const reportIntegritySignal = useCallback(async (signal, { quiet = false } = {}) => {
    const now = Date.now()
    const previous = signalTimesRef.current.get(signal) || 0
    if (now - previous < 1500) return null
    signalTimesRef.current.set(signal, now)
    try {
      const payload = await recordAttemptIntegrity(attemptId, signal)
      applyIntegrityState(payload)
      return payload
    } catch (requestError) {
      if (requestError.status === 409) {
        try { applyIntegrityState(await getAttemptIntegrity(attemptId)) } catch { /* The attempt summary refresh below remains authoritative. */ }
      } else if (!quiet) {
        setIntegrityError(requestError.message || 'This examination signal could not be recorded.')
      }
      return null
    }
  }, [attemptId, applyIntegrityState, api])

  useEffect(() => {
    let cancelled = false
    async function load() {
      setLoading(true)
      setError('')
      try {
        const [summary, navigation] = await Promise.all([getAttempt(attemptId), getAttemptQuestions(attemptId)])
        if (cancelled) return
        setAttempt(summary)
        if (summary.status === 'in_progress') applyServerClock(summary)
        const ordered = [...navigation].sort((a, b) => a.order - b.order)
        setQuestions(ordered)
        setMarked(new Set(ordered.flatMap((item, index) => item.marked_for_review ? [index] : [])))
        const firstUnanswered = ordered.findIndex(item => !item.answered)
        setCurrent(firstUnanswered < 0 ? 0 : firstUnanswered)
      } catch (requestError) {
        if (!cancelled) {
          clearRememberedAttempt(attemptId)
          setError(requestError.message || 'This examination could not be loaded. Check your connection and try again.')
        }
      } finally {
        if (!cancelled) setLoading(false)
      }
    }
    if (!attemptId || !/^\d+$/.test(attemptId)) {
      clearRememberedAttempt(attemptId)
      setError('This examination link is not valid.')
      setLoading(false)
    } else load()
    return () => { cancelled = true }
  }, [attemptId, applyServerClock, api])

  useEffect(() => {
    if (attemptStatus !== 'in_progress') return undefined
    const interval = window.setInterval(() => {
      if (!clock) return
      const remaining = Math.max(0, Math.floor((clock.expiresServerEpoch - (Date.now() + clock.offsetMs)) / 1000))
      setSeconds(remaining)
      if (remaining === 0 && !expirySyncRef.current) {
        expirySyncRef.current = true
        setExpiryFinalizing(true)
        refreshAttempt().catch(() => {})
      }
    }, 1000)
    return () => window.clearInterval(interval)
  }, [attemptStatus, clock, refreshAttempt])

  useEffect(() => {
    if (attemptStatus !== 'in_progress') return undefined
    const sync = window.setInterval(() => {
      refreshAttempt().catch(() => {})
    }, 20000)
    return () => window.clearInterval(sync)
  }, [attemptStatus, refreshAttempt])

  useEffect(() => {
    if (attemptStatus !== 'in_progress') {
      clearRememberedAttempt(attemptId)
      return undefined
    }
    api.rememberPath(attemptId)
    let cancelled = false
    getAttemptIntegrity(attemptId).then(payload => {
      if (!cancelled) applyIntegrityState(payload)
    }).catch(requestError => {
      if (!cancelled) setIntegrityError(requestError.message || 'Integrity status could not be loaded.')
    })

    function onVisibilityChange() {
      if (document.visibilityState === 'hidden') {
        hiddenRef.current = true
        if (unloadingRef.current) return
        window.clearTimeout(hiddenTimerRef.current)
        hiddenTimerRef.current = window.setTimeout(() => {
          if (document.visibilityState === 'hidden' && !unloadingRef.current) reportIntegritySignal('page_hidden', { quiet: true })
        }, 700)
      } else {
        window.clearTimeout(hiddenTimerRef.current)
        hiddenTimerRef.current = null
        if (hiddenRef.current) {
          hiddenRef.current = false
          if (!unloadingRef.current) reportIntegritySignal('page_visible', { quiet: true })
        }
        unloadingRef.current = false
      }
    }

    function onPageHide() {
      window.clearTimeout(hiddenTimerRef.current)
      hiddenTimerRef.current = null
      // Pagehide is recorded but not counted: refresh and tab close share this browser signal.
      reportIntegritySignal('page_hide', { quiet: true })
    }

    function onWindowBlur() {
      if (document.visibilityState === 'hidden' || blurredRef.current) return
      window.setTimeout(() => {
        if (document.visibilityState === 'visible' && !document.hasFocus() && !blurredRef.current) {
          blurredRef.current = true
          reportIntegritySignal('window_blur', { quiet: true })
        }
      }, 900)
    }

    function onWindowFocus() {
      unloadingRef.current = false
      if (hiddenRef.current && document.visibilityState === 'visible') {
        hiddenRef.current = false
        window.clearTimeout(hiddenTimerRef.current)
        if (!unloadingRef.current) reportIntegritySignal('page_visible', { quiet: true })
      }
      if (blurredRef.current) {
        blurredRef.current = false
        reportIntegritySignal('window_focus', { quiet: true })
      }
    }

    function onBeforeUnload(event) {
      unloadingRef.current = true
      event.preventDefault()
      event.returnValue = ''
    }

    function onDocumentKeyDown(event) {
      onExamKeyDown(event)
    }

    function onIntegrityUpdate(event) {
      if ((event.detail?.accessMode || 'portal') === api.mode && String(event.detail?.attemptId) === String(attemptId) && event.detail?.state) {
        applyIntegrityState(event.detail.state)
      }
    }

    document.addEventListener('visibilitychange', onVisibilityChange)
    window.addEventListener('pagehide', onPageHide)
    window.addEventListener('pageshow', onWindowFocus)
    window.addEventListener('blur', onWindowBlur)
    window.addEventListener('focus', onWindowFocus)
    window.addEventListener('beforeunload', onBeforeUnload)
    window.addEventListener('attempt-integrity-updated', onIntegrityUpdate)
    document.addEventListener('keydown', onDocumentKeyDown, true)
    return () => {
      cancelled = true
      window.clearTimeout(hiddenTimerRef.current)
      document.removeEventListener('visibilitychange', onVisibilityChange)
      window.removeEventListener('pagehide', onPageHide)
      window.removeEventListener('pageshow', onWindowFocus)
      window.removeEventListener('blur', onWindowBlur)
      window.removeEventListener('focus', onWindowFocus)
      window.removeEventListener('beforeunload', onBeforeUnload)
      window.removeEventListener('attempt-integrity-updated', onIntegrityUpdate)
      document.removeEventListener('keydown', onDocumentKeyDown, true)
    }
  }, [attemptId, attemptStatus, applyIntegrityState, reportIntegritySignal, api])

  useEffect(() => {
    if (!attemptStatus || !questions.length || attemptStatus !== 'in_progress' || seconds <= 0) return undefined
    const item = questions[current]
    if (!item) return undefined
    let cancelled = false
    const requestId = ++questionRequestRef.current
    setQuestionLoading(true)
    setQuestion(null)
    getAttemptQuestion(attemptId, item.id).then(payload => {
      if (cancelled || requestId !== questionRequestRef.current) return
      setQuestion(payload)
      setError('')
      const restored = payload.selected_options || []
      answerValuesRef.current = { ...answerValuesRef.current, [current]: restored }
      setAnswers(previous => ({ ...previous, [current]: restored }))
      setQuestions(previous => previous.map((entry, index) => index === current ? { ...entry, answered: restored.length > 0, marked_for_review: payload.marked_for_review } : entry))
      setMarked(previous => {
        const next = new Set(previous)
        payload.marked_for_review ? next.add(current) : next.delete(current)
        return next
      })
      setSaveState(previous => ({ ...previous, [current]: 'saved' }))
    }).catch(requestError => {
      if (!cancelled && requestId === questionRequestRef.current) setError(requestError.message || 'The question could not be loaded.')
    }).finally(() => {
      if (!cancelled && requestId === questionRequestRef.current) setQuestionLoading(false)
    })
    return () => { cancelled = true }
  }, [attemptId, attemptStatus, current, questions.length, api])

  const persistAnswer = useCallback(index => {
    const item = questions[index]
    if (!item || !dirtyQuestionsRef.current.has(item.id)) return Promise.resolve()
    const previous = saveQueuesRef.current.get(item.id) || Promise.resolve()
    const task = previous.catch(() => {}).then(async () => {
      while (dirtyQuestionsRef.current.has(item.id)) {
        const revision = answerRevisionRef.current[index]
        const selected = [...(answerValuesRef.current[index] || [])]
        await saveAttemptAnswer(attemptId, item.id, selected)
        if (answerRevisionRef.current[index] === revision) {
          dirtyQuestionsRef.current.delete(item.id)
          setSaveState(state => ({ ...state, [index]: 'saved' }))
          setQuestions(list => list.map((row, rowIndex) => rowIndex === index ? { ...row, answered: selected.length > 0 } : row))
        }
      }
      setSaveError('')
    }).catch(requestError => {
      setSaveState(state => ({ ...state, [index]: 'error' }))
      setSaveError(requestError.message || 'Your answer could not be saved. Retry before continuing.')
      throw requestError
    })
    saveQueuesRef.current.set(item.id, task)
    return task
  }, [attemptId, questions, api])

  const flushAnswer = useCallback(index => {
    const item = questions[index]
    if (!item) return Promise.resolve()
    if (dirtyQuestionsRef.current.has(item.id)) return persistAnswer(index)
    return saveQueuesRef.current.get(item.id) || Promise.resolve()
  }, [persistAnswer, questions])

  function changeAnswer(value) {
    const selected = Array.isArray(value) ? value : value ? [value] : []
    const item = questions[current]
    answerValuesRef.current = { ...answerValuesRef.current, [current]: selected }
    answerRevisionRef.current[current] = (answerRevisionRef.current[current] || 0) + 1
    dirtyQuestionsRef.current.add(item.id)
    setAnswers(previous => ({ ...previous, [current]: selected }))
    setQuestions(previous => previous.map((entry, index) => index === current ? { ...entry, answered: selected.length > 0 } : entry))
    setSaveState(previous => ({ ...previous, [current]: 'saving' }))
    persistAnswer(current).catch(() => {})
  }

  async function selectQuestion(index) {
    if (index === current) return
    try {
      await flushAnswer(current)
      setCurrent(index)
      setSaveError('')
    } catch { /* Keep the candidate on this question until its answer saves. */ }
  }

  async function changeReview() {
    const item = questions[current]
    const wasMarked = marked.has(current)
    const nextValue = !wasMarked
    setMarked(previous => { const next = new Set(previous); nextValue ? next.add(current) : next.delete(current); return next })
    setQuestions(previous => previous.map((entry, index) => index === current ? { ...entry, marked_for_review: nextValue } : entry))
    try {
      await setAttemptReview(attemptId, item.id, nextValue)
    } catch (requestError) {
      setMarked(previous => { const next = new Set(previous); wasMarked ? next.add(current) : next.delete(current); return next })
      setQuestions(previous => previous.map((entry, index) => index === current ? { ...entry, marked_for_review: wasMarked } : entry))
      setError(requestError.message || 'The review flag could not be saved. Try again.')
    }
  }

  async function handleAttemptNavigation() {
    setLeaveWarning(true)
    await reportIntegritySignal('navigation_attempt')
  }

  function blockContentExtraction(event, signal) {
    event.preventDefault()
    reportIntegritySignal(signal, { quiet: true })
  }

  function onExamKeyDown(event) {
    const key = event.key.toLowerCase()
    // Browser controls are deterrence/signals only. Server-side authorization, timing, persistence and policy remain authoritative; OS screenshots cannot be blocked here.
    if ((event.ctrlKey || event.metaKey) && ['c', 'x', 'a'].includes(key)) {
      event.preventDefault()
      reportIntegritySignal(key === 'c' ? 'copy_attempt' : key === 'x' ? 'cut_attempt' : 'select_all_attempt', { quiet: true })
    } else if (event.key === 'PrintScreen') {
      // Browser key events are only a signal; OS screenshots cannot be reliably prevented here.
      reportIntegritySignal('screenshot_key_attempt', { quiet: true })
    }
  }

  async function moveTo(index) {
    try {
      await flushAnswer(current)
      if (index >= questions.length) setConfirmOpen(true)
      else setCurrent(index)
      setSaveError('')
    } catch { /* A save failure must not discard the current answer. */ }
  }

  async function confirmSubmit() {
    setSubmitting(true)
    setSaveError('')
    try {
      await Promise.all(questions.map((_, index) => flushAnswer(index)))
      const result = await submitAttempt(attemptId)
      setAttempt(previous => ({ ...previous, status: result.status, submitted_at: result.submitted_at }))
      clearRememberedAttempt(attemptId)
      setConfirmOpen(false)
      setSeconds(0)
    } catch (requestError) {
      try {
        const current = await refreshAttempt()
        if (current.status !== 'in_progress') {
          setConfirmOpen(false)
          setSaveError('')
          return
        }
      } catch { /* Keep the original submission error when the status cannot be confirmed. */ }
      setSaveError(requestError.message || 'The attempt could not be submitted. Your saved answers remain available.')
    } finally {
      setSubmitting(false)
    }
  }

  useEffect(() => {
    if (onTerminal && attemptStatus && ['submitted', 'expired'].includes(attemptStatus)) onTerminal()
  }, [attemptStatus, onTerminal])

  if (loading) return <LoadingState label={t('Loading your examination…')} />
  if (error && !attempt) return <div className="student-page"><StudentEmptyState title={t('Examination unavailable')} description={t(error)} /><p className="exam-terminal-state__actions"><Button as={Link} to={api.backPath} variant="outline">{t(api.backLabel)}</Button></p></div>
  if (onTerminal && attemptStatus && attemptStatus !== 'in_progress') return <LoadingState label={t('Opening your examination summary...')} />
  if (attempt?.status === 'submitted') return <section className="exam-terminal-state"><span className="exam-terminal-state__icon"><Icon name="clipboard" size={31} /></span><p className="student-eyebrow">{t('Submission received')}</p><h1>{t('Exam Submitted')}</h1><p>{t('Your examination has been submitted. Check My Results for updates from your institution.')}</p><div className="exam-terminal-state__actions"><Button as={Link} to={api.backPath} variant="outline">{t(api.backLabel)}</Button></div></section>
  if (attempt?.status !== 'in_progress') return <section className="exam-terminal-state exam-terminal-state--expired"><span className="exam-terminal-state__icon"><Icon name="bell" size={31} /></span><p className="student-eyebrow">{t('Examination window')}</p><h1>{t("Time's Up")}</h1><p>{t('Your saved answers have been marked. Check My Results when your institution releases the result.')}</p><div className="exam-terminal-state__actions"><Button as={Link} to={api.backPath} variant="outline">{t(api.backLabel)}</Button></div></section>
  if (expiryFinalizing || seconds <= 0) return <section className="exam-terminal-state exam-terminal-state--expired" role="status"><span className="exam-terminal-state__icon"><Icon name="bell" size={31} /></span><p className="student-eyebrow">{t('Examination window')}</p><h1>{t('Finalising your examination')}</h1><p>{t('Time is up. We are confirming your examination status with the server. This page will update when the connection is restored.')}</p></section>

  const optionQuestion = question ? {
    id: question.id,
    type: question.question.question_type,
    prompt: question.question.text,
    media: question.question.media,
    mediaMode: api.mode,
    options: question.options.map(option => ({ id: option.id, label: option.text })),
  } : null
  const statusLabel = saveState[current] === 'saving' ? 'Saving answer…' : saveState[current] === 'error' ? 'Answer not saved' : 'All changes saved'

  return <div className="student-exam-runner" onCopy={event => blockContentExtraction(event, 'copy_attempt')} onCut={event => blockContentExtraction(event, 'cut_attempt')} onContextMenu={event => blockContentExtraction(event, 'context_menu_attempt')}>
    <header className="exam-runner-header"><div className="exam-runner-brand"><span className="wordmark__mark" aria-hidden="true">{t('SA')}</span><span>{t('School Assessment')}<br /><small>{t(api.mode === 'quick' ? 'Take an Exam' : 'Student portal')}</small></span></div><div className="exam-runner-title"><h1>{attempt.assessment_title}</h1><p>{attempt.assessment_type} · {t(`Attempt ${attempt.attempt_number}`)}</p></div><div className="exam-runner-header__status"><span className="preview-save-state" role="status"><Icon name="file" size={16} />{t(statusLabel)}</span><ExamTimer seconds={seconds} translate={t} />{headerControl}</div></header>
    <div className="exam-runner-context"><span><Icon name="clipboard" size={16} />{t('Live examination')}</span><span className="exam-runner-context__candidate">{t(`${questions.length} questions`)}</span><span>{t('Answers save automatically')}</span></div>
    {(integrity?.warning || leaveWarning) && integrity?.interruption_count > 0 && <aside className="exam-integrity-warning" role="alert"><Icon name="bell" size={19} /><div><strong>{t('Examination interruption detected.')}</strong><p>{t('Leaving the examination is recorded. Repeated interruptions may cause your examination to be submitted automatically.')}</p><span>{t(`Warning ${integrity.interruption_count} of ${integrity.interruption_limit}`)}</span></div></aside>}
    {integrityError && <p className="exam-integrity-sync-error" role="status">{t('Integrity status could not sync. Keep this page open and check your connection.')}</p>}
    <div className="exam-runner-progress"><div><strong>{t(`Question ${current + 1} of ${questions.length}`)}</strong><span>{t(`Question ${questions[current]?.order ?? current + 1}`)}</span></div><div className="exam-progress-track" role="progressbar" aria-label={t('Answered questions')} aria-valuemin="0" aria-valuemax={questions.length} aria-valuenow={answeredCount}><span style={{ width: `${questions.length ? (answeredCount / questions.length) * 100 : 0}%` }} /></div><div className="exam-progress-counts"><span>{t(`${answeredCount} answered`)}</span><span>{t(`${questions.length - answeredCount} unanswered`)}</span><span>{t(`${markedCount} marked`)}</span></div></div>
    <main className="exam-runner-content"><section className="exam-question-column"><Card as="article" className="exam-question-card"><div className="exam-question-card__heading"><span className="exam-question-index">Q{String(current + 1).padStart(2, '0')}</span><div><strong>{question?.question?.question_type === 'multiple_choice' ? t('Multiple choice') : question?.question?.question_type === 'multiple_select' ? t('Multiple select') : question?.question?.question_type === 'true_false' ? t('True or false') : t('Question')}</strong><span>{t(`Question ${current + 1}`)}</span></div><Button variant={marked.has(current) ? 'secondary' : 'outline'} size="small" aria-pressed={marked.has(current)} onClick={changeReview} disabled={questionLoading || !question}><Icon name="file" size={16} />{marked.has(current) ? t('Marked for Review') : t('Mark for Review')}</Button></div><div className="exam-question-card__body">{questionLoading || !optionQuestion ? <LoadingState label={t('Loading question…')} /> : <QuestionRenderer translate={t} question={optionQuestion} value={answers[current] || []} onChange={changeAnswer} />}<p className="preview-answer-note" role="status"><Icon name="file" size={15} />{t(statusLabel)}</p>{(saveError || error) && <p className="auth-error" role="alert">{saveError || error}</p>}{saveError && <Button variant="outline" size="small" onClick={() => flushAnswer(current).catch(() => {})}>{t('Retry save')}</Button>}</div><div className="exam-question-card__footer"><Button variant="outline" disabled={current === 0 || questionLoading} onClick={() => moveTo(current - 1)}><Icon name="arrow" size={16} className="icon-flip-horizontal" />{t('Previous')}</Button><div><Button variant="ghost" disabled={questionLoading || !question} onClick={changeReview}>{marked.has(current) ? t('Remove review mark') : t('Mark for review')}</Button><Button disabled={questionLoading || !question} onClick={() => moveTo(current + 1)}>{current === questions.length - 1 ? t('Review & Submit') : t('Next')}<Icon name="arrow" size={17} /></Button></div></div></Card><div className="exam-runner-mobile-nav" aria-label={t('Question controls')}><Button variant="outline" disabled={current === 0 || questionLoading} onClick={() => moveTo(current - 1)}>{t('Previous')}</Button><Button disabled={questionLoading || !question} onClick={() => moveTo(current + 1)}>{current === questions.length - 1 ? t('Review & Submit') : t('Next')}<Icon name="arrow" size={17} /></Button></div></section>
      <aside className="exam-runner-aside"><QuestionNavigator translate={t} questions={questions} answers={answers} marked={marked} current={current} onSelect={selectQuestion} /><Card className="exam-preview-reminder"><Icon name="bell" size={19} /><div><strong>{t('Your progress is saved')}</strong><p>{t('Your responses and review flags are saved to this attempt and restored if you return.')}</p></div></Card></aside>
    </main>
    <footer className="exam-runner-footer"><span><Icon name="cap" size={15} />{t(api.mode === 'quick' ? 'School Assessment Platform' : 'School Assessment Platform · Student portal')}</span><Button variant="ghost" size="small" onClick={handleAttemptNavigation}>{t('Exit examination')}</Button></footer>

    <Modal open={confirmOpen} onClose={() => !submitting && setConfirmOpen(false)} title={t("Review & Submit")} closeLabel={t("Close dialog")} canClose={!submitting} className="submit-exam-modal" footer={<><Button variant="outline" disabled={submitting} onClick={() => setConfirmOpen(false)}>{t('Continue Reviewing')}</Button><Button loading={submitting} onClick={confirmSubmit}>{t('Submit Exam')}</Button></>}>
      <p>{t('Submit your examination when you are ready. You cannot change answers after submission.')}</p><div className="submit-summary"><span>{t('Answered')}<strong>{answeredCount}</strong></span><span>{t('Unanswered')}<strong>{questions.length - answeredCount}</strong></span><span>{t('Marked for Review')}<strong>{markedCount}</strong></span></div>{saveError && <p className="auth-error" role="alert">{saveError}</p>}
    </Modal>
  </div>
}
