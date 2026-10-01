import { useEffect, useMemo, useState } from 'react'
import { Link, useNavigate, useSearchParams } from 'react-router-dom'
import Badge from '../../components/common/Badge.jsx'
import Button from '../../components/common/Button.jsx'
import Card from '../../components/common/Card.jsx'
import Icon from '../../components/common/Icon.jsx'
import SearchField from '../../components/common/SearchField.jsx'
import { ExamCard, StudentEmptyState, StudentPageHeader } from '../../components/student/StudentComponents.jsx'
import { previewExams } from '../../data/studentPreviewData.js'

const tabs = [['available', 'Available'], ['upcoming', 'Upcoming'], ['completed', 'Completed']]
const belongsToTab = (exam, tab) => tab === 'available' ? ['available', 'in_progress'].includes(exam.state) : exam.state === tab

export default function StudentExamsPage() {
  const [searchParams, setSearchParams] = useSearchParams()
  const navigate = useNavigate()
  const requestedTab = tabs.some(([key]) => key === searchParams.get('tab')) ? searchParams.get('tab') : 'available'
  const [activeTab, setActiveTab] = useState(requestedTab)
  const [selectedId, setSelectedId] = useState(() => searchParams.get('exam') || previewExams.find(exam => belongsToTab(exam, requestedTab))?.id || null)
  const [search, setSearch] = useState('')
  const [subject, setSubject] = useState('all')
  const subjects = [...new Set(previewExams.map(exam => exam.subject))]
  const filtered = useMemo(() => previewExams.filter(exam => {
    const matchesSearch = `${exam.title} ${exam.subject} ${exam.cohort}`.toLowerCase().includes(search.trim().toLowerCase())
    return belongsToTab(exam, activeTab) && matchesSearch && (subject === 'all' || exam.subject === subject)
  }), [activeTab, search, subject])

  useEffect(() => {
    setActiveTab(requestedTab)
    setSelectedId(searchParams.get('exam') || previewExams.find(exam => belongsToTab(exam, requestedTab))?.id || null)
  }, [requestedTab, searchParams])

  const selectedExam = filtered.find(exam => exam.id === selectedId) || filtered[0]
  const otherExams = filtered.filter(exam => exam.id !== selectedExam?.id)

  function chooseTab(tab) {
    setActiveTab(tab)
    setSelectedId(previewExams.find(exam => belongsToTab(exam, tab))?.id || null)
    setSearchParams(tab === 'available' ? {} : { tab })
  }

  function selectExam(exam) {
    if (exam.state === 'in_progress') {
      navigate('/student/exam', { state: { examId: exam.id } })
      return
    }
    setSelectedId(exam.id)
    setSearchParams({ ...(activeTab === 'available' ? {} : { tab: activeTab }), exam: exam.id })
  }

  function startExam(exam) { navigate('/student/exam', { state: { examId: exam.id } }) }

  function renderExamDetails(exam) {
    return <Card as="article" className="exam-before-start exam-before-start--featured" aria-labelledby="before-start-title">
      <div className="exam-featured-meta"><div><Badge variant={exam.state === 'available' ? 'success' : exam.state === 'in_progress' ? 'primary' : 'neutral'}>{exam.state === 'available' ? 'Available now' : exam.state === 'in_progress' ? 'In progress' : exam.state}</Badge><Badge>{exam.subject}</Badge><Badge>{exam.cohort}</Badge></div><span><Icon name="clock" size={16} />{exam.state === 'available' ? 'Available now' : exam.startsAt}</span></div>
      <div className="exam-before-start__heading"><div><h2 id="before-start-title">{exam.title}</h2><p>{exam.summary}</p></div></div>
      <div className="exam-detail-facts exam-detail-facts--wide"><span><small>Duration</small><strong>{exam.durationMinutes} minutes</strong></span><span><small>Questions</small><strong>{exam.questionCount}</strong></span><span><small>Total marks</small><strong>{exam.totalMarks}</strong></span><span><small>Attempts</small><strong>{exam.attemptsAllowed} allowed · {exam.attemptsRemaining} remaining</strong></span><span><small>Start time</small><strong>{exam.startsAt}</strong></span><span><small>End time</small><strong>{exam.endsAt}</strong></span></div>
      <div className="exam-instructions"><h3>Before you start</h3><ul>{(exam.instructions.length ? exam.instructions : ['Review the examination schedule before opening this assessment.']).slice(0, 4).map(item => <li key={item}><Icon name="check" size={17} />{item}</li>)}</ul></div>
      <div className="exam-before-start__footer"><p><Icon name="file" size={16} />This is a local interface preview. No attempt is created or saved.</p>{exam.state === 'available' ? <Button onClick={() => startExam(exam)}>Start Exam<Icon name="arrow" size={17} /></Button> : exam.state === 'in_progress' ? <Button onClick={() => startExam(exam)}>Continue Exam<Icon name="arrow" size={17} /></Button> : exam.state === 'completed' && exam.resultStatus === 'released' ? <Button as={Link} to={`/student/results?result=${exam.resultId}`}>View Result<Icon name="arrow" size={17} /></Button> : null}</div>
    </Card>
  }

  return <div className="student-page student-exams-page">
    <StudentPageHeader eyebrow="Academic portal · Assessment schedule" title="My Exams">View your examinations and start an exam when you&apos;re ready.</StudentPageHeader>
    <div className="student-exam-tabs" role="tablist" aria-label="Examination status">{tabs.map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={activeTab === key} aria-controls="student-exam-panel" className={activeTab === key ? 'is-active' : ''} onClick={() => chooseTab(key)}>{label}<span>{previewExams.filter(exam => belongsToTab(exam, key)).length}</span></button>)}</div>
    <Card className="student-exam-filters"><SearchField id="student-exam-search" label="Search examinations" placeholder="Search exams..." value={search} onChange={event => setSearch(event.target.value)} /><label className="form-field student-exam-subject-filter"><span>Filter subject</span><select className="form-control form-select" value={subject} onChange={event => setSubject(event.target.value)}><option value="all">All subjects</option>{subjects.map(value => <option key={value}>{value}</option>)}</select></label></Card>
    <section id="student-exam-panel" role="tabpanel" aria-label={`${tabs.find(([key]) => key === activeTab)?.[1]} examinations`} className="student-exam-panel">
      {selectedExam ? <>{renderExamDetails(selectedExam)}{otherExams.length > 0 && <div className="student-card-list">{otherExams.map(exam => <ExamCard key={exam.id} exam={exam} onAction={exam.state === 'completed' ? undefined : () => selectExam(exam)} actionLabel={exam.state === 'in_progress' ? 'Continue Exam' : 'View Exam'} action={exam.state === 'completed' ? (exam.resultStatus === 'released' ? <Button as={Link} to={`/student/results?result=${exam.resultId}`} variant="outline">View Result<Icon name="arrow" size={16} /></Button> : <span className="student-pending-label">Not yet released</span>) : undefined} />)}</div>}</> : <StudentEmptyState title={`No ${activeTab} exams`} description={activeTab === 'completed' ? 'Completed examinations will appear here.' : activeTab === 'upcoming' ? 'You have no scheduled examinations at the moment.' : 'There are no examinations available to start right now.'} />}
    </section>
    <p className="student-preview-note"><Icon name="file" size={15} />Sample examination content for interface preview.</p>
  </div>
}
