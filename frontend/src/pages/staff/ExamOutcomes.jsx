import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Button from '../../components/common/Button.jsx'
import Modal from '../../components/common/Modal.jsx'
import QuestionMedia from '../../components/common/QuestionMedia.jsx'
import { ownerOutcomes, downloadReport, saveReport, releaseOutcomes } from '../../services/outcomes.js'
import { examError } from '../../services/assessments.js'
import { ReadState, useOwnerRead, ExamPagination, Facts } from './exam-ui.jsx'
import { submissionLabels } from './outcomes-copy.js'
import { canReleaseResults, canEditResultSettings, resultAvailabilityExplanation } from '../../services/resultAvailability.js'
import './outcomes.css'

const date = value => value ? new Date(value).toLocaleString() : '—'
const value = number => number == null ? '—' : String(number)
export function OutcomeSummary({ summary, t, performance = false }) {
  const fields = performance ? [['total_candidates', 'Candidates'], ['results_count', 'Results available'], ['average_percentage', 'Average %'], ['pass_rate', 'Pass rate %'], ['highest_percentage', 'Highest %'], ['lowest_percentage', 'Lowest %']]
    : [['total_candidates', 'Candidates'], ['not_started_count', 'Not started'], ['in_progress_count', 'In progress'], ['submitted_count', 'Submitted'], ['auto_submitted_count', 'Auto-submitted'], ['not_submitted_count', 'Not submitted']]
  return <div className="outcome-summary">{fields.map(([field, label]) => <div className="exam-panel" key={field}><span>{t(label)}</span><strong>{value(summary[field])}</strong></div>)}</div>
}
export function OutcomeTable({ rows, t, performance, onOpen, administrator, onRelease, busy }) {
  const columns = performance ? ['Candidate', 'Candidate ID', 'Score', 'Total', 'Percentage', 'Grade', 'Pass / Fail', 'Status', 'Candidate results', 'Actions'] : ['Candidate', 'Candidate ID', 'Status', 'Started', 'Submitted at', 'Time used', 'Score', 'Actions']
  return <div className="exam-table-scroll" tabIndex={0} role="region" aria-label={t(performance ? 'Results' : 'Submissions')}><table className="exam-table outcome-table"><thead><tr>{columns.map(label => <th key={label}>{t(label)}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.candidate}>
    <td><bdi>{row.name}</bdi></td><td><bdi>{row.candidate_id}</bdi></td>
    {performance ? <><td>{value(row.score)}</td><td>{value(row.total_marks)}</td><td>{value(row.percentage)}</td><td>{value(row.grade)}</td><td>{row.passed == null ? '—' : t(row.passed ? 'Pass' : 'Fail')}</td><td>{t(submissionLabels[row.submission_status])}</td><td>{row.result ? t(row.publication === 'released' ? 'Released' : 'Not released') : '—'}</td></> : <><td>{t(submissionLabels[row.submission_status])}</td><td>{date(row.started_at)}</td><td>{date(row.submitted_at)}</td><td>{row.time_used_seconds == null ? '—' : `${row.time_used_seconds} ${t('seconds')}`}</td><td>{value(row.score)}</td></>}
    <td><div className="exam-actions">{['submitted', 'auto_submitted'].includes(row.submission_status) && <Button variant="outline" onClick={() => onOpen(row)}>{t(performance && row.result ? 'View result' : 'View submission')}</Button>}{performance && administrator && row.result && row.publication !== 'released' && <Button disabled={busy} onClick={() => onRelease(row)}>{t('Release result')}</Button>}</div></td>
  </tr>)}</tbody></table></div>
}
export function SubmissionBreakdown({ data, t }) {
  const row = data.candidate
  return <><h2><bdi>{row.name}</bdi></h2><Facts t={t} entries={[["Candidate ID", row.candidate_id], ['Exam', data.exam], ['Status', t(submissionLabels[row.submission_status])], ['Started', date(row.started_at)], ['Submitted at', date(row.submitted_at)], ['Time used', row.time_used_seconds == null ? null : `${row.time_used_seconds} ${t('seconds')}`], ['Score', row.score], ['Total', row.total_marks], ['Percentage', row.percentage], ['Pass / Fail', row.passed == null ? null : t(row.passed ? 'Pass' : 'Fail')], ['Candidate results', t(row.publication === 'released' ? 'Released' : 'Not released')]]} />
    {data.questions.map(question => <article className="exam-question" key={question.order}><h3>{t('Question')} {question.order}</h3><p className="outcome-prompt"><bdi>{question.question.text}</bdi></p><QuestionMedia media={question.question.media} /><ul>{question.options.map((option, index) => <li key={index}><bdi>{option.text}</bdi>{option.selected && <> · {t('Candidate response')}</>}{option.is_correct && <> · {t('Correct answer')}</>}</li>)}</ul>{!question.options.some(option => option.selected) && <p>{t('Unanswered')}</p>}<p>{t({ correct: 'Correct', incorrect: 'Incorrect', unanswered: 'Unanswered', invalid: 'Invalid', not_marked: 'Not marked' }[question.status])} · {value(question.marks_obtained)} / {question.marks_available} {t('marks')}</p></article>)}</>
}
export function ReportButtons({ t, onDownload, busy, available = true }) {
  return <div className="exam-actions">{[['csv', 'CSV'], ['pdf', 'PDF'], ['docx', 'Word']].map(([format, label]) => <Button key={format} disabled={busy || !available} onClick={() => onDownload(format)}>{t(label)}</Button>)}</div>
}
export function PublicationStatus({ summary, t }) {
  return <span className="outcome-publication" role="status">{t({ no_results: 'No results yet', not_released: 'Not released', partially_released: 'Partially released', released: 'Released' }[summary.release_state] || 'No results yet')}</span>
}
export function ResultsPublication({ summary, t, administrator, allowed, busy, onRelease, exam, settingsAdministrator = administrator }) {
  const pending = summary.release_pending_count ?? summary.unreleased_count ?? 0
  return <div className="exam-panel outcome-publication-header"><div><h2>{t('Candidate results')}</h2><PublicationStatus summary={summary} t={t} />{summary.results_count > 0 && <p>{summary.released_count} / {summary.results_count} {t('Released')}</p>}</div>
    {administrator && allowed && pending > 0 && <Button disabled={busy} onClick={() => onRelease({ bulk: true, count: pending })}>{t(summary.release_state === 'partially_released' ? 'Release Remaining Results' : 'Release Results')}</Button>}
    {exam && <div className="exam-wide"><p>{t(resultAvailabilityExplanation(exam))}</p>{settingsAdministrator && (canEditResultSettings(exam, settingsAdministrator)
      ? <Button as={Link} variant="outline" to={`/app/exams/${exam.id}/edit#result-availability`}>{t('Change Result Settings')}</Button>
      : <p>{t(exam.has_attempt_history ? 'Result settings cannot be changed after an exam attempt has started. Configure result availability on a new draft before candidates start.' : 'Result settings can only be changed on a draft exam. Review the exam workflow in Overview.')} {!exam.has_attempt_history && <Link to="?section=overview">{t('Overview')}</Link>}</p>)}</div>}
  </div>
}
export function ReleaseConfirmation({ release, t, busy, onCancel, onPublish, error }) {
  return <>{release?.bulk ? <><p>{release.count} {t('candidate results will become available according to this exam’s result visibility settings.')}</p><p>{t('Once released, candidates with portal access may be able to view their results.')}</p></> : <p>{t('Release this result to the candidate?')} <bdi>{release?.name}</bdi></p>}
    {error && <p role="alert">{t(error)}</p>}<div className="exam-actions"><Button variant="outline" disabled={busy} onClick={onCancel}>{t('Cancel')}</Button><Button loading={busy} onClick={onPublish}>{t(release?.bulk ? 'Release Results' : 'Release result')}</Button></div></>
}
export default function ExamOutcomes({ institutionId, exam, section, administrator, t, direction }) {
  const [search, setSearch] = useState(''), [status, setStatus] = useState('all'), [sort, setSort] = useState('name'), [page, setPage] = useState(1)
  const [selected, setSelected] = useState(null), [release, setRelease] = useState(null), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const active = useRef(true)
  useEffect(() => { active.current = true; return () => { active.current = false } }, [])
  const performance = section === 'results'
  const state = useOwnerRead(`${institutionId}:${exam.id}:${section}:${search}:${status}:${sort}:${page}`, signal => ownerOutcomes(institutionId, exam.id, section === 'reports' || section === 'overview' ? 'outcomes' : section, { search, status, sort, page }, { signal }))
  const detail = useOwnerRead(`${institutionId}:${exam.id}:submission:${selected?.attempt}`, signal => selected ? ownerOutcomes(institutionId, exam.id, `submissions/${selected.attempt}`, {}, { signal }) : Promise.resolve(null))
  async function download(format) {
    setBusy(true); setError('')
    try { const blob = await downloadReport(institutionId, exam.id, format); if (active.current) saveReport(blob, exam, format) }
    catch { if (active.current) setError('Download failed. Please try again.') }
    finally { if (active.current) setBusy(false) }
  }
  async function publish() {
    setBusy(true); setError(''); setSuccess('')
    try { await releaseOutcomes(institutionId, exam.id, release.bulk ? null : release.result); if (active.current) { setRelease(null); setSuccess('Results released successfully.'); state.retry(); detail.retry() } }
    catch (failure) { if (active.current) setError(examError(failure)) }
    finally { if (active.current) setBusy(false) }
  }
  const data = state.data
  const allowed = canReleaseResults(exam) && data?.summary.can_release_results === true
  const filter = (setter, next) => { setter(next); setPage(1) }
  return <div className="outcomes" dir={direction}><ReadState state={state} t={t}>{data && <>
    <OutcomeSummary summary={data.summary} t={t} performance={performance || section === 'reports'} />
    {performance && <ResultsPublication summary={data.summary} t={t} administrator={data.summary.can_release_results === true} settingsAdministrator={administrator} allowed={allowed} exam={exam} busy={busy || state.loading} onRelease={next => { setError(''); setSuccess(''); setRelease(next) }} />}
    {!data.delivery_supported && <p>{t('Specific-candidate delivery is not implemented.')}</p>}
    {!data.summary.total_candidates && <p>{t('No candidates have been added to this exam yet.')} <Link to="?section=candidates">{t('Go to Candidates')}</Link></p>}
    {section === 'overview' ? <div className="exam-actions">{['submissions', 'results', 'reports'].map(tab => <Link key={tab} to={`?section=${tab}`}>{t({ submissions: 'View Submissions', results: 'View Results', reports: 'View Report' }[tab])}</Link>)}</div> : section === 'reports' ? <><p>{t('Reports include all participants and the latest submission for each candidate.')}</p>{!data.summary.results_count && <p>{t('Results will appear here after submissions are marked.')}</p>}<ReportButtons t={t} onDownload={download} busy={busy} available={data.summary.results_count > 0} /></> : <>
      {performance && <p>{t('Only available results contribute to performance statistics.')}</p>}
      {!data.summary.submitted_count && data.summary.total_candidates > 0 && <p>{t('No submissions yet.')}</p>}
      {performance && !data.summary.results_count && <p>{t('Results will appear here after submissions are marked.')}</p>}
      <div className="outcome-filters"><label>{t('Search candidates')}<input type="search" value={search} onChange={event => filter(setSearch, event.target.value)} /></label><label>{t('Filter results')}<select value={status} onChange={event => filter(setStatus, event.target.value)}>{['all', ...(performance ? ['passed', 'failed', 'not_submitted', 'released', 'not_released'] : Object.keys(submissionLabels))].map(option => <option key={option} value={option}>{t(submissionLabels[option] || { all: 'All', passed: 'Passed', failed: 'Failed', released: 'Released', not_released: 'Not released' }[option])}</option>)}</select></label><label>{t('Sort results')}<select value={sort} onChange={event => filter(setSort, event.target.value)}>{[['name', 'Name'], ['-percentage', 'Highest percentage first'], ['-score', 'Highest score first'], ['-submitted_at', 'Latest submission first']].map(([option, label]) => <option key={option} value={option}>{t(label)}</option>)}</select></label><Button variant="outline" onClick={state.retry}>{t('Refresh')}</Button></div>
      {!data.results.length ? <p>{t('No candidates match these filters.')}</p> : <OutcomeTable rows={data.results} t={t} performance={performance} onOpen={setSelected} administrator={allowed} onRelease={row => { setError(''); setSuccess(''); setRelease(row) }} busy={busy || state.loading} />}
      <ExamPagination page={page} count={data.count} onChange={setPage} t={t} />
    </>}
  </>}</ReadState>{busy && !release && <p role="status">{t('Preparing download…')}</p>}{success && <p role="status">{t(success)}</p>}{error && <p role="alert">{t(error)}</p>}
    <Modal open={Boolean(selected)} title={t(performance && selected?.result ? 'View result' : 'View submission')} closeLabel={t('Close dialog')} onClose={() => setSelected(null)} dir={direction}><ReadState state={detail} t={t}>{detail.data && <SubmissionBreakdown data={detail.data} t={t} />}</ReadState></Modal>
    <Modal open={Boolean(release)} title={t(release?.bulk ? 'Release results?' : 'Release result')} closeLabel={t('Close dialog')} onClose={() => { setRelease(null); setError('') }} canClose={!busy} dir={direction}><ReleaseConfirmation release={release} t={t} busy={busy} error={error} onCancel={() => { setRelease(null); setError('') }} onPublish={publish} /></Modal>
  </div>
}
