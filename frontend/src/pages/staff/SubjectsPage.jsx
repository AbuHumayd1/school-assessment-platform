import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { useLanguageMode } from '../../context/LanguageModeContext.jsx'
import { staffApiFetch } from '../../services/api.js'
import Button from '../../components/common/Button.jsx'
import Icon from '../../components/common/Icon.jsx'
import Modal from '../../components/common/Modal.jsx'
import { canAccessWorkspaceCapability, canPrepareWorkspace } from '../../utils/staffCapabilities.js'
import './subjects.css'

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

export function SubjectCollection({ subjects, label }) {
  const accents = ['indigo', 'violet', 'blue', 'teal', 'emerald', 'amber', 'rose']
  return <div className="subject-collection">{subjects.map(subject => {
    const identity = String(subject.id)
    const hash = Array.from(identity).reduce((value, char) => (value * 31 + char.charCodeAt(0)) >>> 0, 0)
    return <article key={subject.id} className={`panel-surface entity-card accent-edge accent--${accents[hash % accents.length]}`}>
      <div className="entity-card__heading"><span className="accent-icon"><Icon name="book" /></span><div><h2><bdi>{subject.name}</bdi></h2><p className="subject-code"><span>{label('Code', 'الرمز')}</span> <bdi>{subject.code}</bdi></p></div></div>
      {subject.description && <p><bdi>{subject.description}</bdi></p>}
      {subject.is_active === false && <span className="status-pill">{label('Inactive', 'غير نشطة')}</span>}
    </article>
  })}</div>
}

export function SubjectCreateForm({ fields, setFields, busy, error, create, close, label }) {
  return <form className="subject-form" onSubmit={create}>
    {error && <p className="form-error" role="alert">{error}</p>}
    <fieldset disabled={busy} className="subject-fields">
      <label className="form-field">{label('Subject name', 'اسم المادة')}<input className="form-control" autoFocus required maxLength={160} dir="auto" value={fields.name} onChange={event => setFields({ ...fields, name: event.target.value })} /></label>
      <label className="form-field">{label('Subject code', 'رمز المادة')}<input className="form-control" required maxLength={64} dir="auto" value={fields.code} onChange={event => setFields({ ...fields, code: event.target.value })} /></label>
    </fieldset>
    <div className="subject-form-actions"><Button variant="outline" disabled={busy} onClick={close}>{label('Cancel', 'إلغاء')}</Button><Button type="submit" loading={busy}>{label('Create subject', 'إنشاء المادة')}</Button></div>
  </form>
}

function Subjects({ institutionId }) {
  const { label, direction } = useLanguageMode()
  const { currentWorkspace, currentRole } = useWorkspace()
  const canCreate = canAccessWorkspaceCapability(currentRole, 'subjects', currentWorkspace.institution.workspace_mode)
  const prepare = canPrepareWorkspace(currentRole, currentWorkspace.institution.workspace_mode)
  const [formOpen, setFormOpen] = useState(false)
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
    if (busy || !canCreate) return
    setBusy(true); setError('')
    try {
      const subject = await staffApiFetch(`subjects/?institution=${institutionId}`, { method: 'POST', body: { institution: institutionId, ...fields }, signal: submission.current.signal })
      if (submission.current.signal.aborted) return
      setSubjects(rows => [...(rows || []), subject]); setFields({ name: '', code: '' }); setFormOpen(false)
    } catch (failure) {
      if (failure.name !== 'AbortError') setError(failure.status === 400 ? Object.values(failure.data || {}).flat().join(' ') : label('Could not create subject. Please try again.', 'تعذر إنشاء المادة. يرجى المحاولة مجددًا.'))
    } finally { if (!submission.current.signal.aborted) setBusy(false) }
  }
  const close = () => { if (!busy) setFormOpen(false) }
  return <section className="exam-page subjects-page" dir={direction}>
    <header className="page-header"><div><h1 className="page-header__title">{label('Subjects', 'المواد')}</h1><p className="page-header__description">{label('Organise the learning areas used across your assessments.', 'نظّم المجالات التعليمية المستخدمة في اختباراتك.')}</p></div>
      {canCreate && <Button disabled={subjects === null || busy} onClick={() => setFormOpen(true)} aria-haspopup="dialog">+ {label('Add subject', 'إضافة مادة')}</Button>}
    </header>
    {error && !formOpen && <p className="error-state" role="alert">{error}</p>}
    {subjects === null ? <p className="loading-state" role="status">{label('Loading…', 'جارٍ التحميل…')}</p> : subjects.length ? <SubjectCollection subjects={subjects} label={label} /> : <div className="empty-state"><span className="accent-icon accent--indigo"><Icon name="book" /></span><p>{label('No subjects have been created for this institution yet.', 'لم تُنشأ أي مواد لهذه المؤسسة بعد.')}</p></div>}
    {formOpen && canCreate && <Modal open title={label('Add subject', 'إضافة مادة')} dir={direction} onClose={close} canClose={!busy} closeLabel={label('Close dialog', 'إغلاق النافذة')}><SubjectCreateForm {...{ fields, setFields, busy, error, create, close, label }} /></Modal>}
    {prepare && canCreate && <nav className="subject-related" aria-label={label('Subject workflows', 'مسارات المواد')}><Button as={Link} variant="outline" size="small" to="/app/exams/new">{label('Create Exam', 'إنشاء اختبار')}</Button><Button as={Link} variant="outline" size="small" to="/app/questions">{label('Question Bank', 'بنك الأسئلة')}</Button></nav>}
  </section>
}

export default function SubjectsPage() {
  const { currentWorkspace } = useWorkspace()
  const institutionId = currentWorkspace.institution.id
  return <Subjects key={institutionId} institutionId={institutionId} />
}
