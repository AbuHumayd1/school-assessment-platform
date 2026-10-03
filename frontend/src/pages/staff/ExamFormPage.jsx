import { useEffect, useRef, useState } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { getExam, examRequest, examError, examFields, localDateValue } from '../../services/assessments.js'
import Button from '../../components/common/Button.jsx'
import { useExamCopy, useOwnerRead, ReadState, ExamPagination } from './exam-ui.jsx'

const defaults = { title: '', description: '', assessment_type: 'test', subject: '', group: '', duration_minutes: 60, pass_mark: '0.00', start_at: '', end_at: '', attempt_limit: 1, resume_allowed: true, review_allowed: false, randomize_questions: false, randomize_options: false, security_level: 'standard', candidate_access: 'assigned_group', result_visibility: 'hidden', result_release_mode: 'approval_required' }
const labels = { title: 'Title', description: 'Description', assessment_type: 'Assessment type', subject: 'Subject', group: 'Group / Cohort', duration_minutes: 'Duration (minutes)', pass_mark: 'Pass mark', start_at: 'Start (local time)', end_at: 'End (local time)', attempt_limit: 'Attempt limit', resume_allowed: 'Resume allowed', review_allowed: 'Review allowed', randomize_questions: 'Randomize questions', randomize_options: 'Randomize options', security_level: 'Security level', candidate_access: 'Candidate access', result_visibility: 'Result visibility', result_release_mode: 'Release policy' }
export function ExamFields({ values, options, t, onChange, disabled }) {
  return <fieldset disabled={disabled} className="exam-form"><legend>{t('Exam configuration')}</legend>{Object.keys(defaults).map(key => {
    const name = labels[key]
    const props = { className: 'form-control', name: key, value: values[key], onChange: event => onChange(key, event.target.value) }
    if (typeof defaults[key] === 'boolean') return <label className="exam-checkbox" key={key}><input type="checkbox" checked={values[key]} onChange={event => onChange(key, event.target.checked)} />{t(name)}</label>
    const choices = key === 'subject' ? options.subjects.map(row => ({ value: row.id, label: row.name, raw: true })) : key === 'group' ? options.groups.map(row => ({ value: row.id, label: row.name, raw: true })) : options.choices[key]
    if (choices) return <label key={key}>{t(name)}<select {...props} required={key === 'subject'}>{['subject', 'group'].includes(key) && <option value="">{t('Not set')}</option>}{key === 'candidate_access' && values[key] === 'specific_candidates' && <option value="specific_candidates">{t('specific_candidates')}</option>}{choices.map(row => <option key={row.value} value={row.value}>{row.raw ? row.label : t(row.value)}</option>)}</select></label>
    if (key === 'description') return <label className="exam-wide" key={key}>{t(name)}<textarea {...props} rows={3} /></label>
    const numeric = ['duration_minutes', 'pass_mark', 'attempt_limit'].includes(key)
    return <label key={key}>{t(name)}<input {...props} type={['start_at', 'end_at'].includes(key) ? 'datetime-local' : numeric ? 'number' : 'text'} min={key === 'pass_mark' ? 0 : numeric ? 1 : undefined} step={key === 'pass_mark' ? '.01' : numeric ? '1' : undefined} required={['title', 'duration_minutes', 'pass_mark', 'attempt_limit'].includes(key)} maxLength={key === 'title' ? 200 : undefined} /></label>
  })}</fieldset>
}
function AttachedQuestion({ row, t, busy, onSave, onRemove }) {
  const [order, setOrder] = useState(row.order)
  const [marks, setMarks] = useState(row.marks)
  return <div className="exam-question"><p><bdi>{row.question_text}</bdi></p><form className="exam-actions" onSubmit={event => { event.preventDefault(); onSave(row.id, { order: Number(order), marks }) }}><label>{t('Order')}<input type="number" min={1} required className="form-control" value={order} onChange={event => setOrder(event.target.value)} /></label><label>{t('Marks')}<input type="number" min=".01" step=".01" required className="form-control" value={marks} onChange={event => setMarks(event.target.value)} /></label><Button type="submit" disabled={busy} variant="outline">{t('Update question')}</Button><Button disabled={busy} variant="outline" onClick={() => onRemove(row)}>{t('Remove question')}</Button></form></div>
}
function QuestionAttachment({ institutionId, exam, t }) {
  const [revision, setRevision] = useState(0)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState('')
  const [order, setOrder] = useState(1)
  const [marks, setMarks] = useState('1.00')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const state = useOwnerRead(`${institutionId}:${exam.id}:links:${revision}`, signal => examRequest(institutionId, `${exam.id}/questions/`, { signal }))
  const options = useOwnerRead(`${institutionId}:${exam.subject}:${page}:${query}`, signal => examRequest(institutionId, 'question-options/', { signal }, { subject: String(exam.subject), page: String(page), search: query }))
  useEffect(() => { if (state.data) setOrder(Math.max(0, ...state.data.map(row => row.order)) + 1) }, [state.data])
  async function mutate(path, method, body) {
    setBusy(true); setError('')
    try { await examRequest(institutionId, `${exam.id}/questions/${path}`, { method, body }); setRevision(value => value + 1); setSelected('') }
    catch (failure) { setError(examError(failure)) }
    finally { setBusy(false) }
  }
  return <section className="exam-panel"><h2>{t('Attached questions')}</h2><p>{t('Save subject changes before attaching questions. Only approved questions in the saved subject are available.')}</p>{error && <p role="alert" className="exam-error">{t(error)}</p>}<ReadState state={state} t={t}>{state.data?.map(row => <AttachedQuestion key={`${row.id}:${revision}`} row={row} t={t} busy={busy} onSave={(id, body) => mutate(`${id}/`, 'PATCH', body)} onRemove={item => { if (window.confirm(t('Remove this question from the exam?'))) mutate(`${item.id}/`, 'DELETE') }} />)}</ReadState>
    <form className="exam-actions" onSubmit={event => { event.preventDefault(); setQuery(search); setPage(1); setSelected('') }}><label>{t('Search approved questions')}<input className="form-control" value={search} onChange={event => setSearch(event.target.value)} /></label><Button type="submit">{t('Search')}</Button></form>
    <ReadState state={options} t={t}>{options.data && <><form className="exam-form" onSubmit={event => { event.preventDefault(); mutate('', 'POST', { question: Number(selected), order: Number(order), marks }) }}><label className="exam-wide">{t('Approved question')}<select className="form-control" required value={selected} onChange={event => setSelected(event.target.value)}><option value="">{t('Select question')}</option>{options.data.results.filter(row => !state.data?.some(link => link.question === row.id)).map(row => <option key={row.id} value={row.id}>{row.text}</option>)}</select></label><label>{t('Order')}<input type="number" min={1} className="form-control" required value={order} onChange={event => setOrder(event.target.value)} /></label><label>{t('Marks')}<input type="number" min=".01" step=".01" className="form-control" required value={marks} onChange={event => setMarks(event.target.value)} /></label><Button type="submit" disabled={busy}>{t('Attach question')}</Button></form><ExamPagination page={page} count={options.data.count} onChange={value => { setPage(value); setSelected('') }} t={t} /></>}</ReadState></section>
}
function Form({ institutionId, id }) {
  const { t, direction } = useExamCopy()
  const navigate = useNavigate()
  const state = useOwnerRead(`${institutionId}:${id || 'new'}:form`, async signal => {
    const [options, exam] = await Promise.all([examRequest(institutionId, 'form-options/', { signal }), id ? getExam(institutionId, id, { signal }) : Promise.resolve(null)])
    return { options, exam }
  })
  const [values, setValues] = useState(defaults)
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => { const exam = state.data?.exam; if (exam) setValues({ ...defaults, ...exam, group: exam.group || '', start_at: localDateValue(exam.start_at), end_at: localDateValue(exam.end_at) }) }, [state.data])
  const blocked = state.data?.exam && (state.data.exam.status !== 'draft' || state.data.exam.has_attempt_history)
  async function save(event) {
    event.preventDefault(); setBusy(true); setError('')
    try {
      const exam = await examRequest(institutionId, id ? `${id}/` : '', { method: id ? 'PATCH' : 'POST', body: examFields(values) })
      if (alive.current) navigate(id ? `/app/exams/${id}` : `/app/exams/${exam.id}/edit`, { replace: true })
    } catch (failure) { if (alive.current) setError(examError(failure)) }
    finally { if (alive.current) setBusy(false) }
  }
  return <section className="exam-page" dir={direction}><Link to={id ? `/app/exams/${id}` : '/app/exams'}>{t('Back to Exams')}</Link><h1>{t(id ? 'Edit Exam' : 'Create Exam')}</h1><ReadState state={state} t={t}>{state.data && <>{blocked ? <p role="alert">{t('Only drafts without attempt history can be edited.')}</p> : <><form className="exam-panel" onSubmit={save}><ExamFields values={values} options={state.data.options} t={t} disabled={busy} onChange={(key, value) => setValues(previous => ({ ...previous, [key]: value }))} />{error && <p role="alert" className="exam-error">{t(error)}</p>}<div className="exam-actions"><Button type="submit" loading={busy}>{t(id ? 'Save exam' : 'Create Exam')}</Button></div></form>{!id && <p>{t('Create the draft first, then attach approved questions.')}</p>}{id && <QuestionAttachment institutionId={institutionId} exam={state.data.exam} t={t} />}</>}</>}</ReadState></section>
}
export default function ExamFormPage() {
  const { currentWorkspace } = useWorkspace()
  const { assessmentId } = useParams()
  return <Form key={`${currentWorkspace.institution.id}:${assessmentId || 'new'}`} institutionId={currentWorkspace.institution.id} id={assessmentId} />
}
