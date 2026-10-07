import { useEffect, useMemo, useState } from 'react'
import { useNavigate, useSearchParams } from 'react-router-dom'
import Badge from '../../components/common/Badge.jsx'
import Button from '../../components/common/Button.jsx'
import Card from '../../components/common/Card.jsx'
import Icon from '../../components/common/Icon.jsx'
import LoadingState from '../../components/common/LoadingState.jsx'
import SearchField from '../../components/common/SearchField.jsx'
import { ExamCard, ExamStatusBadge, StudentEmptyState, StudentPageHeader } from '../../components/student/StudentComponents.jsx'
import useCandidatePortalData from '../../hooks/useCandidatePortalData.js'
import { formatCandidateDate } from '../../utils/candidatePortal.js'
import { startAttempt } from '../../services/attempts.js'

const tabs = [['available', 'Available'], ['upcoming', 'Upcoming'], ['completed', 'Completed']]
const belongsToTab = (exam, tab) => tab === 'available' ? ['available', 'in_progress'].includes(exam.status) : exam.status === tab

function PortalState({ portal }) {
  if (portal.loading) return <LoadingState label="Loading your examinations…" />
  if (portal.accessState === 'unlinked') return <StudentEmptyState title="Candidate profile not linked" description="Your account is not linked to a candidate profile. Contact your institution for help." />
  if (portal.accessState === 'restricted') return <StudentEmptyState title="Candidate access unavailable" description="Your candidate profile needs attention. Contact your institution for assistance." />
  if (portal.error) return <section className="portal-load-error" role="alert"><p>{portal.error}</p><Button variant="outline" onClick={portal.retry}>Try again</Button></section>
  return null
}

export default function StudentExamsPage() {
  const navigate = useNavigate()
  const portal = useCandidatePortalData()
  const [searchParams, setSearchParams] = useSearchParams()
  const requestedTab = tabs.some(([key]) => key === searchParams.get('tab')) ? searchParams.get('tab') : 'available'
  const [activeTab, setActiveTab] = useState(requestedTab)
  const [selectedId, setSelectedId] = useState(searchParams.get('exam') || null)
  const [search, setSearch] = useState('')
  const [subject, setSubject] = useState('all')
  const [launchNotice, setLaunchNotice] = useState('')
  const [launching, setLaunching] = useState(false)
  const exams = portal.exams || []
  const subjects = [...new Set(exams.map(exam => exam.subject.name))]

  useEffect(() => {
    setActiveTab(requestedTab)
    setSelectedId(searchParams.get('exam') || null)
  }, [requestedTab, searchParams])

  const filtered = useMemo(() => exams.filter(exam => {
    const matchesSearch = `${exam.title} ${exam.subject.name} ${exam.group?.name || ''}`.toLowerCase().includes(search.trim().toLowerCase())
    return belongsToTab(exam, activeTab) && matchesSearch && (subject === 'all' || exam.subject.name === subject)
  }), [exams, activeTab, search, subject])

  const selectedExam = filtered.find(exam => String(exam.id) === String(selectedId)) || filtered[0]
  const otherExams = filtered.filter(exam => exam.id !== selectedExam?.id)

  function chooseTab(tab) {
    setActiveTab(tab)
    setSelectedId(null)
    setLaunchNotice('')
    setSearchParams(tab === 'available' ? {} : { tab })
  }

  function selectExam(exam) {
    setSelectedId(exam.id)
    setLaunchNotice('')
    setSearchParams({ ...(activeTab === 'available' ? {} : { tab: activeTab }), exam: String(exam.id) })
  }

  async function launchExam(exam) {
    setLaunchNotice('')
    setLaunching(true)
    try {
      const attempt = await startAttempt(exam.id)
      navigate(`/student/exam/${attempt.id}`)
    } catch (error) {
      setLaunchNotice(error.message || 'The examination could not be started. Please try again.')
    } finally {
      setLaunching(false)
    }
  }

  function renderExamDetails(exam) {
    const state = exam.status
    const startable = exam.can_start || exam.can_resume
    return <Card as="article" className="exam-before-start exam-before-start--featured" aria-labelledby="before-start-title">
      <div className="exam-featured-meta"><div><ExamStatusBadge state={state} /><Badge>{exam.subject.name}</Badge>{exam.group?.name && <Badge>{exam.group.name}</Badge>}</div><span><Icon name="clock" size={16} />{state === 'upcoming' ? `Starts ${formatCandidateDate(exam.start_at, portal.institution?.timezone)}` : state === 'completed' ? 'Assessment window ended or attempts used' : 'Available now'}</span></div>
      <div className="exam-before-start__heading"><div><h2 id="before-start-title">{exam.title}</h2><p>{exam.assessment_type_label}</p></div></div>
      <div className="exam-detail-facts exam-detail-facts--wide"><span><small>Duration</small><strong>{exam.duration_minutes} minutes</strong></span><span><small>Assessment type</small><strong>{exam.assessment_type_label}</strong></span><span><small>Total marks</small><strong>{exam.total_marks}</strong></span><span><small>Attempts</small><strong>{exam.attempts_used} used · {exam.attempts_remaining} remaining of {exam.attempt_limit}</strong></span><span><small>Start time</small><strong>{formatCandidateDate(exam.start_at, portal.institution?.timezone)}</strong></span><span><small>End time</small><strong>{formatCandidateDate(exam.end_at, portal.institution?.timezone)}</strong></span></div>
      {launchNotice && <p className="form-hint" role="status">{launchNotice}</p>}
      <div className="exam-before-start__footer"><p><Icon name="file" size={16} />{exam.can_resume ? 'Your in-progress attempt is ready to resume.' : 'Your timer starts when you open the examination.'}</p>{startable && <Button loading={launching} onClick={() => launchExam(exam)}>{exam.can_resume ? 'Resume Exam' : 'Start Exam'}<Icon name="arrow" size={17} /></Button>}</div>
    </Card>
  }

  const blocked = portal.loading || portal.error || portal.accessState !== 'ready'
  if (blocked) return <div className="student-page student-exams-page"><PortalState portal={portal} /></div>

  return <div className="student-page student-exams-page">
    <StudentPageHeader eyebrow="Academic portal · Assessment schedule" title="My Exams">View examinations assigned to you or your active class or cohort.</StudentPageHeader>
    <div className="student-exam-tabs" role="tablist" aria-label="Examination status">{tabs.map(([key, label]) => <button key={key} type="button" role="tab" aria-selected={activeTab === key} aria-controls="student-exam-panel" className={activeTab === key ? 'is-active' : ''} onClick={() => chooseTab(key)}>{label}<span>{exams.filter(exam => belongsToTab(exam, key)).length}</span></button>)}</div>
    <Card className="student-exam-filters"><SearchField id="student-exam-search" label="Search examinations" placeholder="Search exams..." value={search} onChange={event => setSearch(event.target.value)} /><label className="form-field student-exam-subject-filter"><span>Filter subject</span><select className="form-control form-select" value={subject} onChange={event => setSubject(event.target.value)}><option value="all">All subjects</option>{subjects.map(value => <option key={value}>{value}</option>)}</select></label></Card>
    <section id="student-exam-panel" role="tabpanel" aria-label={`${tabs.find(([key]) => key === activeTab)?.[1]} examinations`} className="student-exam-panel">
      {selectedExam ? <>{renderExamDetails(selectedExam)}{otherExams.length > 0 && <div className="student-card-list">{otherExams.map(exam => <ExamCard key={exam.id} exam={exam} onAction={() => selectExam(exam)} actionLabel="View details" />)}</div>}</> : <StudentEmptyState title={exams.length ? `No ${activeTab} exams match these filters` : 'No examinations are available yet'} description={exams.length ? 'Try a different search or subject.' : 'Assigned examinations will appear here when they are available to you.'} />}
    </section>
  </div>
}
