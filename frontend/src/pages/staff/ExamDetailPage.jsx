import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { getExam, examRequest, examError } from '../../services/assessments.js'
import { examWorkflowActions, canManageQuickAccess } from '../../utils/staffCapabilities.js'
import Button from '../../components/common/Button.jsx'
import Modal from '../../components/common/Modal.jsx'
import ExamPreview from '../../components/staff/ExamPreview.jsx'
import ExamAccess from './ExamAccess.jsx'
import { useExamCopy, useOwnerRead, ReadState, Facts, ExamPagination } from './exam-ui.jsx'

export function ExamSections({ section, administrator, t, onChange }) {
  return <nav className="exam-sections" aria-label={t('Exam sections')}>{['overview', 'questions', 'candidates', ...(administrator ? ['access'] : [])].map(value => <Link key={value} to={`?section=${value}`} aria-current={section === value ? 'page' : undefined} onClick={onChange}>{t({ overview: 'Overview', questions: 'Questions', candidates: 'Candidates', access: 'Access' }[value])}</Link>)}</nav>
}
export function ExamOverview({ exam, t }) {
  const display = value => typeof value === 'string' ? t(value) : value
  return <div className="exam-panel"><p className="exam-description"><bdi>{exam.description}</bdi></p><Facts t={t} entries={[
    ['Assessment type', display(exam.assessment_type)], ['Status', display(exam.status)], ['Subject', exam.subject_name], ['Group / Cohort', exam.group_name],
    ['Duration', `${exam.duration_minutes} ${t('minutes')}`], ['Total marks', exam.total_marks], ['Pass mark', exam.pass_mark], ['Start', exam.start_at ? new Date(exam.start_at).toLocaleString() : null], ['End', exam.end_at ? new Date(exam.end_at).toLocaleString() : null], ['Attempt limit', exam.attempt_limit], ['Resume allowed', exam.resume_allowed], ['Review allowed', exam.review_allowed], ['Randomize questions', exam.randomize_questions], ['Randomize options', exam.randomize_options], ['Security level', display(exam.security_level)], ['Candidate access', display(exam.candidate_access)], ['Result visibility', display(exam.result_visibility)], ['Release policy', display(exam.result_release_mode)], ['Questions', exam.question_count], ['Quick Exam configured', exam.quick_access_configured], ['Created', new Date(exam.created_at).toLocaleString()], ['Updated', new Date(exam.updated_at).toLocaleString()]
  ]} /></div>
}
export function QuestionInspection({ rows, t }) {
  return <div className="exam-panel">{!rows.length && <p>{t('No questions attached')}</p>}{rows.map(row => <article className="exam-question" key={row.id}><h3>{t('Question')} {row.order} &middot; {row.marks} {t('marks')}</h3><p><bdi>{row.question.text}</bdi></p><p>{t(row.question.question_type)} &middot; {t(row.question.difficulty)} &middot; {t(row.question.status)}{row.question.topic_name && <> &middot; <bdi>{row.question.topic_name}</bdi></>}</p><ol>{row.question.options.map(option => <li key={option.id} className={option.is_correct ? 'exam-correct' : ''}><bdi>{option.text}</bdi>{option.is_correct && <> &middot; {t('Correct answer')}</>}</li>)}</ol>{row.question.explanation && <><h4>{t('Explanation')}</h4><p><bdi>{row.question.explanation}</bdi></p></>}</article>)}</div>
}
function QuestionsSection({ institutionId, id, t }) {
  const state = useOwnerRead(`${institutionId}:${id}:questions`, signal => examRequest(institutionId, `${id}/question-inspection/`, { signal }))
  return <ReadState state={state} t={t}>{state.data && <QuestionInspection rows={state.data} t={t} />}</ReadState>
}
export function EligibilityRoster({ data, t }) {
  return <div className="exam-panel"><p>{t(data.mode === 'access_code' ? 'These candidates have associated Quick credentials. Credential validity is managed separately in Access.' : data.mode === 'specific_candidates' ? 'Specific-candidate delivery is not implemented.' : 'Active candidates with effective group membership are shown.')}</p><p>{t('Status')}: {t(data.workflow_status)} &middot; {t('Window')}: {t(data.window)}</p>{!data.results.length ? <p>{t('No associated candidates')}</p> : <div className="exam-table-scroll"><table className="exam-table"><thead><tr>{['Candidate ID', 'Name', 'Status'].map(text => <th key={text}>{t(text)}</th>)}</tr></thead><tbody>{data.results.map(candidate => <tr key={candidate.id}><td><bdi>{candidate.candidate_id}</bdi></td><td><bdi>{candidate.name}</bdi></td><td>{t(candidate.status)}</td></tr>)}</tbody></table></div>}</div>
}
function CandidatesSection({ institutionId, id, t }) {
  const [page, setPage] = useState(1)
  const state = useOwnerRead(`${institutionId}:${id}:candidates:${page}`, signal => examRequest(institutionId, `${id}/eligibility/`, { signal }, { page: String(page) }))
  return <ReadState state={state} t={t}>{state.data && <><EligibilityRoster data={state.data} t={t} /><ExamPagination page={page} count={state.data.count} onChange={setPage} t={t} /></>}</ReadState>
}
function Detail({ institutionId, id, currentRole }) {
  const { t, direction } = useExamCopy()
  const [params] = useSearchParams()
  const administrator = canManageQuickAccess(currentRole)
  const requested = params.get('section') || 'overview'
  const section = ['overview', 'questions', 'candidates', ...(administrator ? ['access'] : [])].includes(requested) ? requested : 'overview'
  const state = useOwnerRead(`${institutionId}:${id}`, signal => getExam(institutionId, id, { signal }))
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const [confirmation, setConfirmation] = useState(null)
  const [previewOpen, setPreviewOpen] = useState(false)
  const preview = useOwnerRead(`${institutionId}:${id}:preview:${previewOpen}`, signal => previewOpen ? examRequest(institutionId, `${id}/preview/`, { signal }) : Promise.resolve(null))
  async function workflow(action) {
    setBusy(true); setError('')
    try { await examRequest(institutionId, `${id}/${action}/`, { method: 'POST', body: {} }); setConfirmation(null); state.retry() }
    catch (failure) { setError(examError(failure)) }
    finally { setBusy(false) }
  }
  const exam = state.data
  return <section className="exam-page" dir={direction}><Link to="/app/exams">{t('Back to Exams')}</Link><ReadState state={state} t={t}>{exam && <>
    <header className="exam-heading"><div><h1><bdi>{exam.title}</bdi></h1><p>{t(exam.status)}</p></div><div className="exam-actions"><Button variant="outline" onClick={() => setPreviewOpen(true)}>{t('Preview Exam')}</Button>{examWorkflowActions(currentRole, exam).map(action => action === 'edit' ? <Button as={Link} to={`/app/exams/${id}/edit`} key={action}>{t('Edit')}</Button> : <Button key={action} disabled={busy} variant="outline" onClick={() => { setError(''); setConfirmation(action) }}>{t(action)}</Button>)}</div></header>
    <ExamSections section={section} administrator={administrator} t={t} onChange={() => setPreviewOpen(false)} />
    {section === 'overview' && <ExamOverview exam={exam} t={t} />}
    {section === 'questions' && <QuestionsSection institutionId={institutionId} id={id} t={t} />}
    {section === 'candidates' && <CandidatesSection institutionId={institutionId} id={id} t={t} />}
    {section === 'access' && administrator && <ExamAccess key={`${institutionId}:${id}`} institutionId={institutionId} exam={exam} t={t} direction={direction} onUpdate={state.retry} />}
    <Modal open={Boolean(confirmation)} title={t('Confirm action')} closeLabel={t('Close dialog')} onClose={() => { setConfirmation(null); setError('') }} canClose={!busy} dir={direction}><p>{t('Confirm this workflow change?')} {t(confirmation || '')}</p>{error && <p role="alert" className="exam-error">{t(error)}</p>}<div className="exam-actions"><Button loading={busy} onClick={() => workflow(confirmation)}>{t('Confirm')}</Button><Button variant="outline" disabled={busy} onClick={() => setConfirmation(null)}>{t('Cancel')}</Button></div></Modal>
    <Modal open={previewOpen} title={t('Preview Exam')} closeLabel={t('Close dialog')} onClose={() => setPreviewOpen(false)} dir={direction}>{previewOpen && <ReadState state={preview} t={t}>{preview.data && <ExamPreview key={`${institutionId}:${id}`} paper={preview.data} t={t} onClose={() => setPreviewOpen(false)} />}</ReadState>}</Modal>
  </>}</ReadState></section>
}
export default function ExamDetailPage() {
  const { currentWorkspace, currentRole } = useWorkspace()
  const { assessmentId } = useParams()
  return <Detail key={`${currentWorkspace.institution.id}:${assessmentId}`} institutionId={currentWorkspace.institution.id} id={assessmentId} currentRole={currentRole} />
}
