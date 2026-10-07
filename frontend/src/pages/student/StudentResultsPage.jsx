import { useState } from 'react'
import Button from '../../components/common/Button.jsx'
import { ownResults } from '../../services/outcomes.js'
import { useExamCopy, useOwnerRead, ReadState } from '../staff/exam-ui.jsx'
import '../staff/outcomes.css'

export function CandidateResults({ rows, t }) {
  return !rows.length ? <p>{t('No released results yet.')}</p> : <div className="exam-table-scroll" tabIndex={0} role="region" aria-label={t('My results')}><table className="exam-table outcome-table"><thead><tr>{['Exam', 'Date', 'Score', 'Total', 'Percentage', 'Grade', 'Pass / Fail'].map(label => <th key={label}>{t(label)}</th>)}</tr></thead><tbody>{rows.map(row => <tr key={row.id}><td><bdi>{row.assessment_title}</bdi></td><td>{row.submitted_at ? new Date(row.submitted_at).toLocaleString() : '-'}</td><td>{row.marks_obtained}</td><td>{row.total_marks}</td><td>{row.percentage}%</td><td>{row.grade || '-'}</td><td>{t(row.passed ? 'Pass' : 'Fail')}</td></tr>)}</tbody></table></div>
}
export default function StudentResultsPage() {
  const { t, direction } = useExamCopy()
  const [search, setSearch] = useState('')
  const state = useOwnerRead('my-released-results', signal => ownResults({ signal }))
  const rows = state.data?.filter(row => row.assessment_title.toLocaleLowerCase().includes(search.trim().toLocaleLowerCase())) || []
  return <section className="student-page outcomes" dir={direction}><h1>{t('My results')}</h1><p>{t('Only your released results are shown.')}</p><div className="outcome-filters"><label>{t('Search exams')}<input type="search" value={search} onChange={event => setSearch(event.target.value)} /></label><Button variant="outline" onClick={state.retry}>{t('Refresh')}</Button></div><ReadState state={state} t={t}>{state.data && <CandidateResults rows={rows} t={t} />}</ReadState></section>
}
