import { useEffect, useMemo, useState } from 'react'
import { Link, useLocation, useSearchParams } from 'react-router-dom'
import Button from '../../components/common/Button.jsx'
import Card from '../../components/common/Card.jsx'
import Icon from '../../components/common/Icon.jsx'
import Modal from '../../components/common/Modal.jsx'
import { ExamTimer, QuestionNavigator, QuestionRenderer, StudentEmptyState } from '../../components/student/StudentComponents.jsx'
import { previewExams, previewQuestions } from '../../data/studentPreviewData.js'

export default function StudentExamPage() {
  const location = useLocation()
  const [searchParams] = useSearchParams()
  const exam = previewExams.find(item => item.id === location.state?.examId) || previewExams.find(item => item.state === 'available')
  const [current, setCurrent] = useState(0)
  const [answers, setAnswers] = useState({})
  const [marked, setMarked] = useState(() => new Set())
  const [seconds, setSeconds] = useState(() => (exam?.durationMinutes ?? 30) * 60)
  const [confirmOpen, setConfirmOpen] = useState(false)
  const [submitted, setSubmitted] = useState(false)
  const forceExpired = searchParams.get('previewExpired') === '1'
  const expired = forceExpired || seconds <= 0
  const questions = previewQuestions
  const question = questions[current]
  const answeredCount = useMemo(() => Object.values(answers).filter(value => Array.isArray(value) ? value.length > 0 : Boolean(value)).length, [answers])

  useEffect(() => {
    if (expired || submitted) return undefined
    const timerId = window.setInterval(() => setSeconds(value => Math.max(0, value - 1)), 1000)
    return () => window.clearInterval(timerId)
  }, [expired, submitted])

  if (!exam) return <StudentEmptyState title="No examination selected" description="Choose an available examination from My Exams to open the preview." />

  if (submitted) return <section className="exam-terminal-state"><span className="exam-terminal-state__icon"><Icon name="clipboard" size={31} /></span><p className="student-eyebrow">Local preview complete</p><h1>Exam Submitted</h1><p>Your preview responses have been closed. No answers were sent to a server, and no result or score was created.</p><div className="exam-terminal-state__actions"><Button as={Link} to="/student/exams" variant="outline">Back to My Exams</Button></div></section>
  if (expired) return <section className="exam-terminal-state exam-terminal-state--expired"><span className="exam-terminal-state__icon"><Icon name="bell" size={31} /></span><p className="student-eyebrow">Local preview timer</p><h1>Time&apos;s Up</h1><p>The preview timer has ended. No server submission occurred; an integrated examination will use the server-provided expiry state.</p><div className="exam-terminal-state__actions"><Button as={Link} to="/student/exams" variant="outline">Back to My Exams</Button></div></section>

  function setAnswer(value) { setAnswers(previous => ({ ...previous, [current]: value })) }
  function toggleMarked() { setMarked(previous => { const next = new Set(previous); next.has(current) ? next.delete(current) : next.add(current); return next }) }
  function nextOrSubmit() { if (current === questions.length - 1) setConfirmOpen(true); else setCurrent(value => Math.min(value + 1, questions.length - 1)) }
  function submitPreview() { setConfirmOpen(false); setSubmitted(true) }

  return <div className="student-exam-runner">
    <header className="exam-runner-header"><Link className="exam-runner-brand" to="/student" aria-label="School Assessment Platform student portal"><span className="wordmark__mark" aria-hidden="true">SA</span><span>School Assessment<br /><small>Student portal</small></span></Link><div className="exam-runner-title"><h1>{exam.title}</h1><p>{exam.subject} · {exam.cohort}</p></div><div className="exam-runner-header__status"><span className="preview-save-state"><Icon name="file" size={16} />Preview only · not saved</span><ExamTimer seconds={seconds} /></div></header>
    <div className="exam-runner-context"><span><Icon name="clipboard" size={16} />Examination preview</span><span className="exam-runner-context__candidate">{exam.title} · {questions.length} questions</span><span>Responses stay in this page</span></div>
    <div className="exam-runner-progress"><div><strong>Question {current + 1} of {questions.length}</strong><span>{Math.round(((current + 1) / questions.length) * 100)}% viewed</span></div><div className="exam-progress-track" role="progressbar" aria-label="Question navigation progress" aria-valuemin="0" aria-valuemax={questions.length} aria-valuenow={current + 1}><span style={{ width: `${((current + 1) / questions.length) * 100}%` }} /></div><div className="exam-progress-counts"><span>{answeredCount} answered</span><span>{questions.length - answeredCount} unanswered</span><span>{marked.size} marked</span></div></div>
    <main className="exam-runner-content"><section className="exam-question-column"><Card as="article" className="exam-question-card"><div className="exam-question-card__heading"><span className="exam-question-index">Q{String(current + 1).padStart(2, '0')}</span><div><strong>{question.type === 'multiple_choice' ? 'Multiple choice' : question.type === 'multiple_select' ? 'Multiple select' : 'True or false'}</strong><span>Question {current + 1}</span></div><Button variant={marked.has(current) ? 'secondary' : 'outline'} size="small" aria-pressed={marked.has(current)} onClick={toggleMarked}><Icon name="file" size={16} />{marked.has(current) ? 'Marked for Review' : 'Mark for Review'}</Button></div><div className="exam-question-card__body"><QuestionRenderer question={question} value={answers[current]} onChange={setAnswer} /><p className="preview-answer-note"><Icon name="file" size={15} />Your choice is held in temporary page state for this preview only.</p></div><div className="exam-question-card__footer"><Button variant="outline" disabled={current === 0} onClick={() => setCurrent(value => Math.max(value - 1, 0))}><Icon name="arrow" size={16} className="icon-flip-horizontal" />Previous</Button><div><Button variant="ghost" onClick={toggleMarked}>{marked.has(current) ? 'Remove review mark' : 'Mark for review'}</Button><Button onClick={nextOrSubmit}>{current === questions.length - 1 ? 'Review & Submit' : 'Next'}<Icon name="arrow" size={17} /></Button></div></div></Card><div className="exam-runner-mobile-nav" aria-label="Question controls"><Button variant="outline" disabled={current === 0} onClick={() => setCurrent(value => Math.max(value - 1, 0))}>Previous</Button><Button onClick={nextOrSubmit}>{current === questions.length - 1 ? 'Review & Submit' : 'Next'}<Icon name="arrow" size={17} /></Button></div></section>
      <aside className="exam-runner-aside"><QuestionNavigator questions={questions} answers={answers} marked={marked} current={current} onSelect={setCurrent} /><Card className="exam-preview-reminder"><Icon name="bell" size={19} /><div><strong>Preview examination</strong><p>The timer and answers on this screen are local only. No answer checking or server save is connected.</p></div></Card></aside>
    </main>
    <footer className="exam-runner-footer"><span><Icon name="cap" size={15} />School Assessment Platform · Student portal</span><Link to="/student/exams">Exit preview</Link></footer>

    <Modal open={confirmOpen} onClose={() => setConfirmOpen(false)} title="Review & Submit" className="submit-exam-modal" footer={<><Button variant="outline" onClick={() => setConfirmOpen(false)}>Continue Reviewing</Button><Button onClick={submitPreview}>Submit Exam</Button></>}>
      <p>Check your progress before submitting this local preview.</p><div className="submit-summary"><span>Answered<strong>{answeredCount}</strong></span><span>Unanswered<strong>{questions.length - answeredCount}</strong></span><span>Marked for Review<strong>{marked.size}</strong></span></div><p className="form-hint">Submitting only changes this page to a preview confirmation. No server request will be made.</p>
    </Modal>
  </div>
}
