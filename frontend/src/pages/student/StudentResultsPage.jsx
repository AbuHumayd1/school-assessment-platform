import { useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'
import Button from '../../components/common/Button.jsx'
import Card from '../../components/common/Card.jsx'
import Icon from '../../components/common/Icon.jsx'
import Modal from '../../components/common/Modal.jsx'
import SearchField from '../../components/common/SearchField.jsx'
import { ResultDetails, ResultStatusBadge, StudentEmptyState, StudentPageHeader } from '../../components/student/StudentComponents.jsx'
import { previewExams, previewResults } from '../../data/studentPreviewData.js'

export default function StudentResultsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const [search, setSearch] = useState('')
  const [subject, setSubject] = useState('all')
  const [status, setStatus] = useState('all')
  const [selectedId, setSelectedId] = useState(searchParams.get('result'))
  const released = previewResults.filter(result => result.resultStatus === 'released')
  const average = released.length ? (released.reduce((total, result) => total + result.percentage, 0) / released.length).toFixed(1) : null
  const subjects = [...new Set(previewResults.map(result => result.subject))]
  const visible = useMemo(() => previewResults.filter(result => {
    const matchesSearch = `${result.exam} ${result.subject}`.toLowerCase().includes(search.trim().toLowerCase())
    const matchesSubject = subject === 'all' || result.subject === subject
    const matchesStatus = status === 'all' || (status === 'pending' ? result.resultStatus !== 'released' : result.outcome === status)
    return matchesSearch && matchesSubject && matchesStatus
  }), [search, subject, status])
  const selected = previewResults.find(result => result.id === selectedId)

  useEffect(() => { if (searchParams.get('result')) setSelectedId(searchParams.get('result')) }, [searchParams])
  function closeDetails() { setSelectedId(null); setSearchParams({}) }
  function openDetails(id) { setSelectedId(id); setSearchParams({ result: id }) }

  return <div className="student-page student-results-page">
    <StudentPageHeader eyebrow="Academic portal" title="My Results">View results released by your institution. Results that are still pending do not show a score.</StudentPageHeader>
    <div className="result-summary-grid"><Card className="result-summary-card gradient-card gradient-card--soft-indigo"><span className="student-summary-icon"><Icon name="clipboard" /></span><p>Exams Completed</p><strong>{previewExams.filter(exam => exam.state === 'completed').length}</strong><small>Recorded in this preview</small></Card><Card className="result-summary-card gradient-card gradient-card--soft-blue"><span className="student-summary-icon"><Icon name="file" /></span><p>Results Available</p><strong>{released.length}</strong><small>Released in this preview</small></Card><Card className="result-summary-card gradient-card gradient-card--soft-violet"><span className="student-summary-icon"><Icon name="chart" /></span><p>Average Score</p><strong>{average === null ? 'N/A' : `${average}%`}</strong><small>Calculated from released preview results</small></Card></div>
    <Card className="result-filters"><SearchField id="student-result-search" label="Search results by examination or subject" placeholder="Search results…" value={search} onChange={event => setSearch(event.target.value)} /><label className="form-field result-filter"><span className="visually-hidden">Filter by subject</span><select className="form-control form-select" value={subject} onChange={event => setSubject(event.target.value)}><option value="all">All subjects</option>{subjects.map(value => <option key={value}>{value}</option>)}</select></label><label className="form-field result-filter"><span className="visually-hidden">Filter by result status</span><select className="form-control form-select" value={status} onChange={event => setStatus(event.target.value)}><option value="all">All results</option><option value="pass">Pass</option><option value="fail">Fail</option><option value="pending">Result pending</option></select></label></Card>
    {visible.length ? <div className="result-table-wrap"><table className="result-table"><caption className="visually-hidden">Examination results</caption><thead><tr><th scope="col">Examination</th><th scope="col">Subject</th><th scope="col">Date</th><th scope="col">Score</th><th scope="col">Percentage</th><th scope="col">Grade</th><th scope="col">Result</th><th scope="col">Action</th></tr></thead><tbody>{visible.map(result => { const unreleased = result.resultStatus !== 'released'; const pending = result.resultStatus === 'pending'; const withheld = result.resultStatus === 'withheld'; return <tr key={result.id}><td data-label="Examination"><strong>{result.exam}</strong><small>{result.cohort || 'Student preview'}</small></td><td data-label="Subject">{result.subject}</td><td data-label="Date">{unreleased ? 'Pending' : result.dateCompleted}</td><td data-label="Score">{unreleased ? <span className="result-withheld-label">Withheld</span> : `${result.score} / ${result.totalMarks}`}</td><td data-label="Percentage">{unreleased ? 'Withheld' : `${result.percentage}%`}</td><td data-label="Grade">{unreleased ? 'Withheld' : result.grade}</td><td data-label="Result"><ResultStatusBadge pending={pending} withheld={withheld} outcome={result.outcome} /></td><td data-label="Action">{unreleased ? <span className="result-withheld-label">{withheld ? 'Not yet released' : 'Result pending'}</span> : <Button size="small" variant="outline" onClick={() => openDetails(result.id)}>View Result<Icon name="arrow" size={15} /></Button>}</td></tr> })}</tbody></table></div> : <StudentEmptyState title="No matching results" description="Try changing your search or filters." />}
    <div className="student-preview-note"><Icon name="file" size={15} />Local preview results only. Released result details appear in a dialog; pending results remain hidden.</div>
    <Modal open={Boolean(selected)} onClose={closeDetails} title={selected?.exam || 'Result details'} className="result-details-modal" footer={<Button variant="outline" onClick={closeDetails}>Close</Button>}><ResultDetails result={selected} /></Modal>
  </div>
}
