import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { useLanguageMode } from '../../context/LanguageModeContext.jsx'
import { staffApiFetch } from '../../services/api.js'

export function SubjectEmptyState({ t = text => text }) {
  return <div role="status"><p>{t('No subjects have been created for this institution yet.')}</p><Link to="/app/subjects">{t('Create a subject')}</Link></div>
}

export async function listWorkspaceSubjects(institutionId, signal, request = staffApiFetch) {
  const rows = []
  let page = 1
  while (true) {
    const data = await request(`subjects/?institution=${institutionId}&page=${page}`, { signal })
    const batch = Array.isArray(data) ? data : data.results
    if (!Array.isArray(batch) || batch.some(row => String(row.institution) !== String(institutionId))) throw new Error('Workspace context changed.')
    rows.push(...batch)
    if (!data.next) return rows
    page += 1
  }
}

function Subjects({ institutionId }) {
  const { label, direction } = useLanguageMode()
  const [subjects, setSubjects] = useState(null)
  const [fields, setFields] = useState({ name: '', code: '' })
  const [error, setError] = useState('')
  const [busy, setBusy] = useState(false)
  const submission = useRef(null)
  useEffect(() => {
    const controller = new AbortController()
    listWorkspaceSubjects(institutionId, controller.signal).then(rows => { if (!controller.signal.aborted) setSubjects(rows) })
      .catch(failure => { if (failure.name !== 'AbortError') setError(label('Could not load subjects. Please try again.', 'تعذر تحميل المواد. يرجى المحاولة مجددًا.')) })
    return () => controller.abort()
  }, [institutionId])
  useEffect(() => {
    const controller = new AbortController()
    submission.current = controller
    return () => controller.abort()
  }, [])
  async function create(event) {
    event.preventDefault()
    if (busy) return
    setBusy(true); setError('')
    try {
      const subject = await staffApiFetch(`subjects/?institution=${institutionId}`, { method: 'POST', body: { institution: institutionId, ...fields }, signal: submission.current.signal })
      if (submission.current.signal.aborted) return
      setSubjects(rows => [...(rows || []), subject]); setFields({ name: '', code: '' })
    } catch (failure) {
      if (failure.name !== 'AbortError') setError(failure.status === 400 ? Object.values(failure.data || {}).flat().join(' ') : label('Could not create subject. Please try again.', 'تعذر إنشاء المادة. يرجى المحاولة مجددًا.'))
    } finally { if (!submission.current.signal.aborted) setBusy(false) }
  }
  return <section className="exam-page" dir={direction}><h1>{label('Subjects', 'المواد')}</h1>
    {error && <p role="alert">{error}</p>}
    {subjects === null ? <p>{label('Loading…', 'جارٍ التحميل…')}</p> : subjects.length ? <ul>{subjects.map(subject => <li key={subject.id}><bdi>{subject.name}</bdi> · <bdi>{subject.code}</bdi></li>)}</ul> : <p>{label('No subjects have been created for this institution yet.', 'لم تُنشأ أي مواد لهذه المؤسسة بعد.')}</p>}
    <form className="exam-panel" onSubmit={create}><fieldset disabled={busy || subjects === null}><legend>{label('Create a subject', 'إنشاء مادة')}</legend>
      <label>{label('Subject name', 'اسم المادة')}<input className="form-control" required maxLength={160} dir="auto" value={fields.name} onChange={event => setFields({ ...fields, name: event.target.value })} /></label>
      <label>{label('Subject code', 'رمز المادة')}<input className="form-control" required maxLength={64} dir="auto" value={fields.code} onChange={event => setFields({ ...fields, code: event.target.value })} /></label>
      <button type="submit">{label('Create subject', 'إنشاء المادة')}</button>
    </fieldset></form><Link to="/app/exams/new">{label('Create Exam', 'إنشاء اختبار')}</Link>{' · '}<Link to="/app/questions">{label('Question Bank', 'بنك الأسئلة')}</Link>
  </section>
}

export default function SubjectsPage() {
  const { currentWorkspace } = useWorkspace()
  const institutionId = currentWorkspace.institution.id
  return <Subjects key={institutionId} institutionId={institutionId} />
}
