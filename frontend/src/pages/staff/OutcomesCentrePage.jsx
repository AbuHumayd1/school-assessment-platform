import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import Button from '../../components/common/Button.jsx'
import Icon from '../../components/common/Icon.jsx'
import { outcomesIndex, downloadReport, saveReport } from '../../services/outcomes.js'
import { useExamCopy, useOwnerRead, ReadState, ExamPagination } from './exam-ui.jsx'
import { OutcomeSummary, PublicationStatus, ReportButtons } from './ExamOutcomes.jsx'

export const centreCopy = {
  results: ['Results', 'Review and manage assessment results across your institution.', 'View Results'],
  reports: ['Reports', 'Generate and download assessment reports.', 'View Report'],
  submissions: ['Submissions', 'Monitor assessment participation across your institution.', 'View Submissions'],
}

export function AssessmentOutcomesList({ rows, section, t, onDownload, busy }) {
  if (!rows.length) return <div className="exam-panel"><h2>{t('No assessments found')}</h2><p>{t('Assessments will appear here when they are created. Try changing your search.')}</p></div>
  return <div className="outcome-assessments">{rows.map(exam => <article className={section === 'submissions' ? 'exam-panel panel-surface submission-assessment accent-edge accent--indigo' : 'exam-panel'} key={exam.id}>
    <header className="exam-heading"><div><h2><bdi>{exam.title}</bdi></h2><p>{t('Subject')}: <bdi>{exam.subject_name || '—'}</bdi> · {section === 'submissions' ? <span className={`status-pill status-pill--${exam.status}`}>{t(exam.status)}</span> : t(exam.status)}</p></div>{section !== 'submissions' && <PublicationStatus summary={exam.summary} t={t} />}</header>
    <OutcomeSummary summary={exam.summary} t={t} performance={section !== 'submissions'} accented={section === 'submissions'} />
    {section === 'results' && <p>{t('Passed')}: {exam.summary.passed_count} · {t('Failed')}: {exam.summary.failed_count}</p>}
    {!exam.summary.total_candidates ? <p>{t('No candidates have been added to this exam yet.')}</p> : !exam.summary.submitted_count ? <p>{t('No submissions yet.')}</p> : <p>{exam.summary.submitted_count} / {exam.summary.total_candidates} {t('Submitted')}</p>}
    {section !== 'submissions' && !exam.summary.results_count && <p>{t('Results will appear here after submissions are marked.')}</p>}
    <div className="exam-actions"><Button as={Link} variant="outline" to={`/app/exams/${exam.id}?section=${section}`}>{t(centreCopy[section][2])}</Button>
      {section === 'reports' && <ReportButtons t={t} onDownload={format => onDownload(exam, format)} busy={busy} available={exam.report_available} />}
    </div>
  </article>)}</div>
}

function Centre({ institutionId, section }) {
  const { t, direction } = useExamCopy()
  const [search, setSearch] = useState(''), [query, setQuery] = useState(''), [page, setPage] = useState(1)
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  const active = useRef(true)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  const state = useOwnerRead(`${institutionId}:${section}:${query}:${page}`, signal => outcomesIndex(institutionId, section, { search: query, page }, { signal }))
  async function download(exam, format) {
    setBusy(true); setError('')
    try { const blob = await downloadReport(institutionId, exam.id, format); if (active.current) saveReport(blob, exam, format) }
    catch { if (active.current) setError('Download failed. Please try again.') }
    finally { if (active.current) setBusy(false) }
  }
  return <section className={`exam-page outcomes${section === 'submissions' ? ' submissions-centre' : ''}`} dir={direction}>
    <header className="exam-heading"><div><h1>{t(centreCopy[section][0])}</h1><p>{t(centreCopy[section][1])}</p></div></header>
    <form className={section === 'submissions' ? 'outcome-filters workspace-toolbar' : 'outcome-filters'} onSubmit={event => { event.preventDefault(); setQuery(search); setPage(1) }}><label className={section === 'submissions' ? 'toolbar-search' : undefined}>{t('Search assessments')}<span className={section === 'submissions' ? 'search-field' : undefined}>{section === 'submissions' && <Icon name="search" className="search-field__icon" />}<input className={section === 'submissions' ? 'form-control search-field__input' : undefined} type="search" value={search} onChange={event => setSearch(event.target.value)} /></span></label><Button type="submit">{t('Search')}</Button><Button variant="outline" onClick={state.retry}>{t('Refresh')}</Button></form>
    {busy && <p role="status">{t('Preparing download…')}</p>}{error && <p role="alert">{t(error)}</p>}
    <ReadState state={state} t={t}>{state.data && <><AssessmentOutcomesList rows={state.data.results} section={section} t={t} onDownload={download} busy={busy} /><ExamPagination page={page} count={state.data.count} onChange={setPage} t={t} /></>}</ReadState>
  </section>
}

export default function OutcomesCentrePage({ section }) {
  const { currentWorkspace } = useWorkspace()
  const institutionId = currentWorkspace.institution.id
  return <Centre key={`${institutionId}:${section}`} institutionId={institutionId} section={section} />
}
