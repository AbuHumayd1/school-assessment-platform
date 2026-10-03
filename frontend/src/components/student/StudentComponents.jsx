import { useId } from 'react'
import Badge from '../common/Badge.jsx'
import Button from '../common/Button.jsx'
import Card from '../common/Card.jsx'
import Icon from '../common/Icon.jsx'

export function StudentPageHeader({ eyebrow, title, children, action }) {
  return <header className="student-page-header"><div>{eyebrow && <p className="student-eyebrow">{eyebrow}</p>}<h1>{title}</h1>{children && <p className="student-page-header__description">{children}</p>}</div>{action && <div className="student-page-header__action">{action}</div>}</header>
}

export function ExamStatusBadge({ state }) {
  const labels = { available: 'Available now', in_progress: 'In progress', upcoming: 'Upcoming', completed: 'Completed', pending: 'Result pending', released: 'Result available' }
  const variants = { available: 'success', in_progress: 'primary', upcoming: 'neutral', completed: 'neutral', pending: 'warning', released: 'success' }
  return <Badge variant={variants[state] || 'neutral'} className="exam-status"><span className={`exam-status__dot exam-status__dot--${state || 'neutral'}`} aria-hidden="true" />{labels[state] || state}</Badge>
}

export function ResultStatusBadge({ outcome, pending = false, withheld = false }) {
  if (pending) return <Badge variant="warning">Result pending</Badge>
  if (withheld) return <Badge variant="warning">Not yet released</Badge>
  const passed = outcome === 'pass'
  return <Badge variant={passed ? 'success' : 'error'}>{passed ? 'Pass' : 'Fail'}</Badge>
}

export function StudentEmptyState({ title, description }) {
  const titleId = useId()
  return <section className="empty-state" aria-labelledby={titleId}><span className="empty-state__icon" aria-hidden="true">–</span><h2 id={titleId}>{title}</h2>{description && <p>{description}</p>}</section>
}

export function ExamCard({ exam, action, actionLabel, onAction, children, className = '' }) {
  const state = exam.status || exam.state
  const subject = exam.subject?.name || exam.subject
  const group = exam.group?.name || exam.cohort
  return <Card as="article" className={`student-exam-card student-exam-card--${state} ${className}`}>
    <div className="student-exam-card__top"><ExamStatusBadge state={state} /><span>{subject}</span><span>{group}</span></div>
    <h2>{exam.title}</h2>
    <div className="student-exam-card__facts">
      <span><small>Duration</small><strong>{exam.duration_minutes} min</strong></span>
      <span><small>Assessment</small><strong>{exam.assessment_type_label || exam.assessment_type}</strong></span>
      <span><small>Total marks</small><strong>{exam.total_marks}</strong></span>
    </div>
    <div className="student-exam-card__bottom"><span className="student-exam-card__availability"><Icon name="bell" size={16} />{state === 'upcoming' ? exam.start_at : state === 'completed' ? 'Attempt limit reached or assessment ended' : `${exam.attempts_remaining} attempt${exam.attempts_remaining === 1 ? '' : 's'} remaining`}</span>{onAction && <Button onClick={onAction}>{actionLabel}<Icon name="arrow" size={17} /></Button>}{action}</div>
    {children}
  </Card>
}

export function QuestionNavigator({ questions, answers, marked, current, onSelect, translate = text => text }) {
  function questionState(index) {
    if (index === current) return 'current'
    if (marked.has(index) || questions[index]?.marked_for_review) return 'marked'
    if (questions[index]?.answered || (answers[index] !== undefined && (Array.isArray(answers[index]) ? answers[index].length > 0 : answers[index] !== ''))) return 'answered'
    return 'unanswered'
  }
  const answeredCount = questions.filter((_, index) => {
    const value = answers[index]
    return questions[index]?.answered || (Array.isArray(value) ? value.length > 0 : Boolean(value))
  }).length
  const counts = { answered: answeredCount, unanswered: questions.length - answeredCount, marked: marked.size }
  return <Card as="section" className="question-navigator" aria-labelledby="question-nav-title">
    <div className="question-navigator__heading"><div><h2 id="question-nav-title">{translate('Question navigator')}</h2><p>{translate(`${questions.length} questions`)}</p></div><Icon name="clipboard" /></div>
    <ul className="question-legend" aria-label={translate('Question status legend')}><li><i className="question-dot question-dot--current" />{translate('Current')}</li><li><i className="question-dot question-dot--answered" />{translate('Answered')}</li><li><i className="question-dot question-dot--unanswered" />{translate('Unanswered')}</li><li><i className="question-dot question-dot--marked" />{translate('Marked for review')}</li></ul>
    <div className="question-number-grid" role="group" aria-label={translate('Go to question')}>{questions.map((question, index) => <button key={question.id} type="button" className={`question-number question-number--${questionState(index)}${index === current && marked.has(index) ? ' question-number--current-marked' : ''}`} aria-current={index === current ? 'step' : undefined} aria-label={translate(`Question ${index + 1}`) + ', ' + translate(questionState(index).replace('_', ' ')) + (marked.has(index) ? ', ' + translate('marked for review') : '')} onClick={() => onSelect(index)}>{String(index + 1).padStart(2, '0')}{marked.has(index) && <span aria-hidden="true">{translate('◆')}</span>}</button>)}</div>
    <div className="question-navigator__summary"><span>{translate('Answered ')}<strong>{counts.answered}</strong></span><span>{translate('Unanswered ')}<strong>{counts.unanswered}</strong></span><span>{translate('Marked for review ')}<strong>{counts.marked}</strong></span></div>
  </Card>
}

export function QuestionRenderer({ question, value, onChange, translate = text => text }) {
  const isMultiple = question.type === 'multiple_select'
  const selected = Array.isArray(value) ? value : value ? [value] : []
  function toggle(optionId) {
    if (!isMultiple) { onChange(optionId); return }
    onChange(selected.includes(optionId) ? selected.filter(id => id !== optionId) : [...selected, optionId])
  }
  const inputType = isMultiple ? 'checkbox' : 'radio'
  return <fieldset className="question-renderer"><legend>{question.prompt}</legend><p className="question-renderer__instruction">{translate(isMultiple ? 'Select all that apply.' : question.type === 'true_false' ? 'Choose True or False.' : 'Select one answer.')}</p><div className="answer-options">{question.options.map((option, index) => {
    const checked = selected.includes(option.id)
    return <label key={option.id} className={`answer-option${checked ? ' answer-option--selected' : ''}`}><input type={inputType} name={`question-${question.id}`} checked={checked} onChange={() => toggle(option.id)} /><span className="answer-option__letter">{question.type === 'true_false' ? (/^true$/i.test(option.label.trim()) ? 'T' : 'F') : String.fromCharCode(65 + index)}</span><span>{option.label}</span>{checked && <span className="answer-option__selected-label">{translate('Selected')}</span>}</label>
  })}</div></fieldset>
}

export function ExamTimer({ seconds, translate = text => text }) {
  const minutes = Math.floor(seconds / 60)
  const remainder = seconds % 60
  return <div className={`exam-timer${seconds <= 300 ? ' exam-timer--urgent' : ''}`} role="timer" aria-label={translate(`${minutes} minutes ${remainder} seconds remaining`)}><Icon name="clock" size={19} /><span>{String(minutes).padStart(2, '0')}:{String(remainder).padStart(2, '0')}</span><small>{translate('time remaining')}</small></div>
}

export function ResultDetails({ result }) {
  if (!result || result.resultStatus !== 'released') return <p className="result-withheld">This result has not been released. Score and review information are unavailable.</p>
  return <div className="result-details"><div className="result-detail-summary"><p><span>Examination</span><strong>{result.exam}</strong></p><p><span>Subject</span><strong>{result.subject}</strong></p><p><span>Class / Cohort</span><strong>{result.cohort}</strong></p><p><span>Date completed</span><strong>{result.dateCompleted}</strong></p><p><span>Submission time</span><strong>{result.submissionTime}</strong></p><p><span>Result</span><ResultStatusBadge outcome={result.outcome} /></p><p><span>Score</span><strong>{result.score} / {result.totalMarks}</strong></p><p><span>Percentage</span><strong>{result.percentage}%</strong></p><p><span>Grade</span><strong>{result.grade}</strong></p><p><span>Pass mark</span><strong>{result.passMark} / {result.totalMarks}</strong></p><p><span>Questions</span><strong>{result.questionCount}</strong></p><p><span>Correct · Incorrect · Unanswered</span><strong>{result.correct} · {result.incorrect} · {result.unanswered}</strong></p></div>
    {result.reviewAllowed && result.questionReview?.length > 0 && <section className="result-question-review"><h3>Question review</h3><p>Review is available for this released result.</p>{result.questionReview.map((item, index) => <article className="result-review-item" key={`${result.id}-${index}`}><h4>Question {index + 1}</h4><p>{item.question}</p><dl><div><dt>Your answer</dt><dd>{item.studentAnswer || 'Unanswered'}</dd></div><div><dt>Correct answer</dt><dd>{item.correctAnswer}</dd></div></dl><Badge variant={item.status === 'correct' ? 'success' : 'error'}>{item.status === 'correct' ? 'Correct' : item.status === 'incorrect' ? 'Incorrect' : 'Unanswered'}</Badge>{item.explanation && <p className="result-review-item__explanation">{item.explanation}</p>}</article>)}</section>}
    {!result.reviewAllowed && <p className="form-hint">Question-level review is not available for this result.</p>}
  </div>
}
