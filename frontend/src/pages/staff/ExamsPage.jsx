import { useState } from 'react'
import { Link } from 'react-router-dom'
import { canPrepareWorkspace } from '../../utils/staffCapabilities.js'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { listExams, examStatuses } from '../../services/assessments.js'
import Button from '../../components/common/Button.jsx'
import Icon from '../../components/common/Icon.jsx'
import { useExamCopy, useOwnerRead, ReadState, ExamPagination } from './exam-ui.jsx'

export function ExamList({ rows, t }) {
  if (!rows.length) return <div className="exam-panel"><h2>{t('No exams found')}</h2><p>{t('Create an exam or change your filters.')}</p></div>
  return <div className="exam-table-scroll data-surface" tabIndex={0} role="region" aria-label={t('Exams')}><table className="exam-table"><thead><tr>{['Exam', 'Status', 'Subject', 'Questions', 'Duration', 'Access'].map(value => <th key={value}>{t(value)}</th>)}</tr></thead><tbody>{rows.map(exam => <tr key={exam.id}><td><Link to={`/app/exams/${exam.id}`}><bdi>{exam.title}</bdi></Link><small>{t(exam.assessment_type)}{exam.start_at && <> &middot; <bdi>{new Date(exam.start_at).toLocaleString()}</bdi></>}</small></td><td><span className={`status-pill status-pill--${exam.status}`}>{t(exam.status)}</span></td><td><span className="exam-subject"><Icon name="book" size={16} /><bdi>{exam.subject_name}</bdi></span></td><td><strong className="exam-count">{exam.question_count}</strong></td><td>{exam.duration_minutes} {t('minutes')}</td><td className="exam-delivery">{exam.quick_access_configured ? t('Quick Exam configured') : t(exam.candidate_access)}</td></tr>)}</tbody></table></div>
}
export default function ExamsPage() {
  const { currentWorkspace, currentRole } = useWorkspace()
  const institutionId = currentWorkspace.institution.id
  const { t, direction } = useExamCopy()
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const state = useOwnerRead(`${institutionId}:${query}:${status}:${page}`, signal => listExams(institutionId, { search: query, status, page: String(page) }, { signal }))
  return <section className="exam-page exams-list-page" dir={direction}><header className="exam-heading"><div><h1>{t('Exams')}</h1><p>{t('Manage examinations in this workspace.')}</p></div>{canPrepareWorkspace(currentRole, currentWorkspace.institution.workspace_mode) && <Button as={Link} to="/app/exams/new">{t('Create Exam')}</Button>}</header>
    <form className="exam-actions workspace-toolbar" onSubmit={event => { event.preventDefault(); setQuery(search); setPage(1) }}><label className="toolbar-search">{t('Search exams')}<span className="search-field"><Icon name="search" className="search-field__icon" /><input type="search" className="form-control search-field__input" value={search} onChange={event => setSearch(event.target.value)} /></span></label><label>{t('Status')}<select className="form-control" value={status} onChange={event => { setStatus(event.target.value); setPage(1) }}><option value="">{t('All statuses')}</option>{examStatuses.map(value => <option key={value} value={value}>{t(value)}</option>)}</select></label><Button type="submit">{t('Search')}</Button></form>
    <ReadState state={state} t={t}>{state.data && <><ExamList rows={state.data.results} t={t} /><ExamPagination page={page} count={state.data.count} onChange={setPage} t={t} /></>}</ReadState></section>
}
