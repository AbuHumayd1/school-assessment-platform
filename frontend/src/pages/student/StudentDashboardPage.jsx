import { Link } from 'react-router-dom'
import Badge from '../../components/common/Badge.jsx'
import Button from '../../components/common/Button.jsx'
import Card from '../../components/common/Card.jsx'
import Icon from '../../components/common/Icon.jsx'
import LoadingState from '../../components/common/LoadingState.jsx'
import { ExamCard, ExamStatusBadge, StudentEmptyState } from '../../components/student/StudentComponents.jsx'
import useCandidatePortalData from '../../hooks/useCandidatePortalData.js'
import { formatCandidateDate } from '../../utils/candidatePortal.js'

function PortalState({ portal }) {
  if (portal.loading) return <LoadingState label="Loading your student portal…" />
  if (portal.accessState === 'unlinked') return <StudentEmptyState title="Candidate profile not linked" description="Your account is not linked to a candidate profile. Contact your institution for help." />
  if (portal.accessState === 'restricted') return <StudentEmptyState title="Candidate access unavailable" description="Your candidate profile needs attention. Contact your institution for assistance." />
  if (portal.error) return <section className="portal-load-error" role="alert"><p>{portal.error}</p><Button variant="outline" onClick={portal.retry}>Try again</Button></section>
  return null
}

export default function StudentDashboardPage() {
  const portal = useCandidatePortalData()
  const blocked = portal.loading || portal.error || portal.accessState !== 'ready'
  const available = portal.exams.filter(exam => ['available', 'in_progress'].includes(exam.status))
  const upcoming = portal.exams.filter(exam => exam.status === 'upcoming').slice(0, 2)
  const completed = portal.exams.filter(exam => exam.status === 'completed').length
  if (blocked) return <div className="student-page student-dashboard"><PortalState portal={portal} /></div>

  const candidate = portal.candidate
  const candidateName = [candidate?.first_name, candidate?.last_name].filter(Boolean).join(' ')
  const groupNames = (portal.groups || []).map(group => group.name).join(', ')
  return <div className="student-page student-dashboard">
    <section className="student-welcome"><div><p className="student-eyebrow">Student portal · {candidate.candidate_id}</p><h1>Welcome back, {candidate.first_name}</h1><p>{portal.institution?.name}</p></div><div className="student-welcome__identity"><span className="student-identity-icon"><Icon name="cap" size={24} /></span><span><small>Candidate · {candidate.candidate_id}</small><strong>{candidateName}</strong><small>{groupNames || 'No active group'}</small></span></div></section>
    <section className="student-section" aria-labelledby="dashboard-available-title"><div className="student-section-heading"><div><p className="student-eyebrow">Your next step</p><h2 id="dashboard-available-title">Available Exams</h2></div><Badge variant="primary">{available.length} available</Badge></div>
      {available.length ? <div className="student-card-list">{available.map(exam => <ExamCard key={exam.id} exam={exam} action={<Button as={Link} to={`/student/exams?exam=${exam.id}`} variant="outline">View details<Icon name="arrow" size={17} /></Button>} />)}</div> : <StudentEmptyState title="No available exams" description="Exams will appear here when they are available to you." />}
    </section>
    <div className="student-dashboard-columns">
      <section className="student-section" aria-labelledby="dashboard-upcoming-title"><div className="student-section-heading"><h2 id="dashboard-upcoming-title">Upcoming Exams</h2><Link to="/student/exams?tab=upcoming">View schedule<Icon name="arrow" size={16} /></Link></div>
        {upcoming.length ? <div className="student-mini-list">{upcoming.map(exam => <Card as="article" className="student-mini-card" key={exam.id}><div className="student-mini-card__top"><Badge>{exam.subject.name}</Badge><ExamStatusBadge state="upcoming" /></div><h3>{exam.title}</h3><p>{exam.group.name}</p><div className="student-mini-card__facts"><span><small>Date &amp; time</small><strong>{formatCandidateDate(exam.start_at, portal.institution?.timezone)}</strong></span><span><small>Duration</small><strong>{exam.duration_minutes} min</strong></span></div></Card>)}</div> : <StudentEmptyState title="No upcoming exams" description="Your scheduled examinations will appear here." />}
      </section>
      <section className="student-section" aria-labelledby="dashboard-results-title"><div className="student-section-heading"><h2 id="dashboard-results-title">Recent Results</h2></div>
        {completed ? <StudentEmptyState title="Results are not connected yet" description="Your completed exam activity is shown in My Exams. Result details will be available in a later integration step." /> : <StudentEmptyState title="No released results" description="Results will appear here after the results service is connected and your institution releases them." />}
      </section>
    </div>
    <Card className="student-help-strip"><span className="student-summary-icon"><Icon name="inbox" /></span><p>Need help with an examination? Contact your institution for guidance.</p><Link to="/student/exams">Go to My Exams<Icon name="arrow" size={16} /></Link></Card>
  </div>
}
