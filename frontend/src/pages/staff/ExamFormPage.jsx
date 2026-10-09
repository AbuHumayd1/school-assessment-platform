import { useEffect, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useParams } from 'react-router-dom'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { getExam, examRequest, examError, examFields, localDateValue } from '../../services/assessments.js'
import Button from '../../components/common/Button.jsx'
import { SubjectEmptyState } from './SubjectsPage.jsx'
import { useExamCopy, useOwnerRead, ReadState } from './exam-ui.jsx'
import { resultAvailability, resultAvailabilityChoices, resultAvailabilityExplanation } from '../../services/resultAvailability.js'

const defaults = { title: '', description: '', assessment_type: 'test', subject: '', group: '', duration_minutes: 60, pass_mark: '0.00', start_at: '', end_at: '', attempt_limit: 1, resume_allowed: true, review_allowed: false, randomize_questions: false, randomize_options: false, security_level: 'standard', candidate_access: 'assigned_group', result_visibility: 'hidden', show_score_immediately: false, result_release_mode: 'approval_required' }
const labels = { title: 'Title', description: 'Description', assessment_type: 'Assessment type', subject: 'Subject', group: 'Group / Cohort', duration_minutes: 'Duration (minutes)', pass_mark: 'Pass mark', start_at: 'Start (local time)', end_at: 'End (local time)', attempt_limit: 'Attempt limit', resume_allowed: 'Resume allowed', review_allowed: 'Review allowed', randomize_questions: 'Randomize questions', randomize_options: 'Randomize options', security_level: 'Security level', candidate_access: 'Candidate access', result_visibility: 'Result visibility', result_release_mode: 'Release policy' }
export function ExamFields({ values, options, t, onChange, disabled, subjectLocked }) {
  return <fieldset disabled={disabled} className="exam-form"><legend>{t('Exam configuration')}</legend>{Object.keys(defaults).map(key => {
    if (['result_release_mode', 'group', 'candidate_access'].includes(key)) return null
    if (key === 'result_visibility') return <div className="exam-wide" key={key} id="result-availability"><label>{t('Result availability')}<select className="form-control" name="result_availability" value={resultAvailability(values)} aria-describedby="result-availability-help" onChange={event => {
      const choice = resultAvailabilityChoices.find(row => row.value === event.target.value)
      onChange('result_visibility', choice.result_visibility); onChange('result_release_mode', choice.result_release_mode)
    }}>{resultAvailabilityChoices.map(choice => <option key={choice.value} value={choice.value}>{t(choice.label)}</option>)}</select></label><p id="result-availability-help">{t('When should candidates see their results?')} {t(resultAvailabilityExplanation(values))}</p></div>
    if (key === 'show_score_immediately') return <div className="exam-wide" key={key}><label className="exam-checkbox"><input name={key} type="checkbox" checked={Boolean(values[key])} onChange={event => onChange(key, event.target.checked)} aria-describedby="immediate-score-help" />{t('Show score immediately after submission')}</label><p id="immediate-score-help">{t('Candidates see only their score after submitting. Grades, pass/fail status, answers and full results remain hidden until results are released.')}</p></div>
    const name = labels[key]
    if (key === 'subject' && options.subjects.length === 0) return <div key={key}><SubjectEmptyState t={t} /></div>
    const props = { className: 'form-control', name: key, value: values[key], onChange: event => onChange(key, event.target.value) }
    if (typeof defaults[key] === 'boolean') return <label className="exam-checkbox" key={key}><input type="checkbox" checked={values[key]} onChange={event => onChange(key, event.target.checked)} />{t(name)}</label>
    const choices = key === 'subject' ? options.subjects.map(row => ({ value: row.id, label: row.name, raw: true })) : key === 'group' ? options.groups.map(row => ({ value: row.id, label: row.name, raw: true })) : options.choices[key]
    if (choices) return <label key={key}>{t(name)}<select {...props} required={key === 'subject'} disabled={key === 'subject' && subjectLocked}>{['subject', 'group'].includes(key) && <option value="">{t('Not set')}</option>}{key === 'candidate_access' && values[key] === 'specific_candidates' && <option value="specific_candidates">{t('specific_candidates')}</option>}{choices.map(row => <option key={row.value} value={row.value}>{row.raw ? row.label : t(row.value)}</option>)}</select>{key === 'subject' && subjectLocked && <small>{t('Remove attached questions before changing the subject.')}</small>}</label>
    if (key === 'description') return <label className="exam-wide" key={key}>{t(name)}<textarea {...props} rows={3} /></label>
    const numeric = ['duration_minutes', 'pass_mark', 'attempt_limit'].includes(key)
    return <label key={key}>{t(name)}<input {...props} type={['start_at', 'end_at'].includes(key) ? 'datetime-local' : numeric ? 'number' : 'text'} min={key === 'pass_mark' ? 0 : numeric ? 1 : undefined} step={key === 'pass_mark' ? '.01' : numeric ? '1' : undefined} required={['title', 'duration_minutes', 'pass_mark', 'attempt_limit'].includes(key)} maxLength={key === 'title' ? 200 : undefined} /></label>
  })}</fieldset>
}
export function DeliveryChoice({ t, onChoose }) {
  return <section className="exam-panel"><h2>{t('How will candidates enter this exam?')}</h2>
    <div className="exam-actions"><Button onClick={() => onChoose('quick_exam')}>{t('Quick Exam')}</Button><Button variant="outline" onClick={() => onChoose('account_login')}>{t('Through their account')}</Button></div>
    <p>{t('Candidates use Exam Code + Candidate ID + PIN.')}</p><p>{t('Quick Exam candidates do not need platform accounts.')}</p>
    <p>{t('Candidates sign in using their platform account.')}</p><p>{t('Delivery method is fixed when the exam is created.')}</p>
  </section>
}
export function Form({ institutionId, id }) {
  const { t, direction } = useExamCopy()
  const navigate = useNavigate()
  const { hash } = useLocation()
  const state = useOwnerRead(`${institutionId}:${id || 'new'}:form`, async signal => {
    const [options, exam] = await Promise.all([examRequest(institutionId, 'form-options/', { signal }), id ? getExam(institutionId, id, { signal }) : Promise.resolve(null)])
    return { options, exam }
  })
  const [delivery, setDelivery] = useState(null)
  const [values, setValues] = useState(defaults)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => { const exam = state.data?.exam; if (exam) setValues({ ...defaults, ...exam, group: exam.group || '', start_at: localDateValue(exam.start_at), end_at: localDateValue(exam.end_at) }) }, [state.data])
  useEffect(() => {
    if (hash === '#result-availability' && state.data) {
      const target = document.getElementById('result-availability')
      target?.scrollIntoView({ block: 'center' })
      target?.querySelector('select')?.focus({ preventScroll: true })
    }
  }, [hash, state.data])
  const blocked = state.data?.exam && (state.data.exam.status !== 'draft' || state.data.exam.has_attempt_history)
  async function save(event) {
    event.preventDefault(); if (busy || (!id && !delivery)) return; setBusy(true); setError('')
    try {
      const body = examFields(values)
      delete body.group; delete body.candidate_access
      if (!id) body.delivery_mode = delivery
      const exam = await examRequest(institutionId, id ? `${id}/` : '', { method: id ? 'PATCH' : 'POST', body })
      if (alive.current) navigate(id ? `/app/exams/${id}` : `/app/exams/${exam.id}?section=questions`, { replace: true })
    } catch (failure) { if (alive.current) setError(examError(failure)) }
    finally { if (alive.current) setBusy(false) }
  }
  if (!id && !delivery) return <section className="exam-page" dir={direction}><Link to="/app/exams">{t('Back to Exams')}</Link><h1>{t('Create Exam')}</h1><DeliveryChoice t={t} onChoose={setDelivery} /></section>
  return <section className="exam-page" dir={direction}><Link to={id ? `/app/exams/${id}` : '/app/exams'}>{t('Back to Exams')}</Link><h1>{t(id ? 'Edit Exam' : 'Create Exam')}</h1><p>{t((id ? state.data?.exam?.delivery_mode : delivery) === 'quick_exam' ? 'Quick Exam' : 'Through their account')}</p><ReadState state={state} t={t}>{state.data && <>{blocked ? <p role="alert">{t('Only drafts without attempt history can be edited.')}</p> : <><form className="exam-panel" onSubmit={save}><ExamFields values={values} options={state.data.options} t={t} disabled={busy} subjectLocked={state.data.exam?.question_count > 0} onChange={(key, value) => setValues(previous => ({ ...previous, [key]: value }))} />{error && <p role="alert" className="exam-error">{t(error)}</p>}<div className="exam-actions"><Button type="submit" loading={busy}>{t(id ? 'Save exam' : 'Create Exam')}</Button></div></form>{!id && <p>{t('Create the draft, then manage questions and candidates in the exam workspace.')}</p>}{id && <div className="exam-actions"><Link to={`/app/exams/${id}?section=questions`}>{t('Manage Questions')}</Link><Link to={`/app/exams/${id}?section=candidates`}>{t('Manage Candidates')}</Link></div>}</>}</>}</ReadState></section>
}
export default function ExamFormPage() {
  const { currentWorkspace } = useWorkspace()
  const { assessmentId } = useParams()
  return <Form key={`${currentWorkspace.institution.id}:${assessmentId || 'new'}`} institutionId={currentWorkspace.institution.id} id={assessmentId} />
}
