import { Link } from 'react-router-dom'
import Badge from '../../components/common/Badge.jsx'
import Button from '../../components/common/Button.jsx'
import Card from '../../components/common/Card.jsx'
import Icon from '../../components/common/Icon.jsx'
import { ExamCard, ExamStatusBadge, ResultStatusBadge, StudentEmptyState, StudentPageHeader } from '../../components/student/StudentComponents.jsx'
import { previewExams, previewResults, previewStudent } from '../../data/studentPreviewData.js'

export default function StudentDashboardPage() {
  const available = previewExams.filter(exam => ['available', 'in_progress'].includes(exam.state))
  const upcoming = previewExams.filter(exam => exam.state === 'upcoming').slice(0, 2)
  const released = previewResults.filter(result => result.resultStatus === 'released').slice(0, 2)
  return <div className="student-page student-dashboard">
    <section className="student-welcome"><div><p className="student-eyebrow">Student portal · {previewStudent.candidateCode}</p><h1>Welcome back</h1><p>Here&apos;s an overview of your examination activity.</p></div><div className="student-welcome__identity"><span className="student-identity-icon"><Icon name="cap" size={24} /></span><span><small>Candidate</small><strong>{previewStudent.displayName}</strong><small>{previewStudent.className}</small></span></div></section>
    <section className="student-section" aria-labelledby="dashboard-available-title"><div className="student-section-heading"><div><p className="student-eyebrow">Your next step</p><h2 id="dashboard-available-title">Available Exams</h2></div><Badge variant="primary">{available.length} available</Badge></div>
      {available.length ? <div className="student-card-list">{available.map(exam => <ExamCard key={exam.id} exam={exam} actionLabel={exam.state === 'in_progress' ? 'Continue Exam' : 'View Exam'} action={exam.state === 'in_progress' ? <Button as={Link} to="/student/exam" state={{ examId: exam.id }}>Continue Exam<Icon name="arrow" size={17} /></Button> : <Button as={Link} to={`/student/exams?exam=${exam.id}`} variant="outline">View Exam<Icon name="arrow" size={17} /></Button>} />)}</div> : <StudentEmptyState title="No available exams" description="Exams will appear here when they are available to you." />}
    </section>
    <div className="student-dashboard-columns">
      <section className="student-section" aria-labelledby="dashboard-upcoming-title"><div className="student-section-heading"><h2 id="dashboard-upcoming-title">Upcoming Exams</h2><Link to="/student/exams?tab=upcoming">View schedule<Icon name="arrow" size={16} /></Link></div>
        {upcoming.length ? <div className="student-mini-list">{upcoming.map(exam => <Card as="article" className="student-mini-card" key={exam.id}><div className="student-mini-card__top"><Badge>{exam.subject}</Badge><ExamStatusBadge state="upcoming" /></div><h3>{exam.title}</h3><p>{exam.cohort}</p><div className="student-mini-card__facts"><span><small>Date & time</small><strong>{exam.startsAt}</strong></span><span><small>Duration</small><strong>{exam.durationMinutes} min</strong></span></div></Card>)}</div> : <StudentEmptyState title="No upcoming exams" description="Your scheduled examinations will appear here." />}
      </section>
      <section className="student-section" aria-labelledby="dashboard-results-title"><div className="student-section-heading"><h2 id="dashboard-results-title">Recent Results</h2><Link to="/student/results">View all<Icon name="arrow" size={16} /></Link></div>
        {released.length ? <div className="student-mini-list">{released.map(result => <Card as="article" className="student-result-mini" key={result.id}><div><h3>{result.exam}</h3><p>{result.subject} · {result.dateCompleted}</p></div><span className="student-result-mini__score">{result.score} / {result.totalMarks}<small>{result.percentage}%</small></span><ResultStatusBadge outcome={result.outcome} /><Button as={Link} to={`/student/results?result=${result.id}`} variant="ghost" size="small">View Result<Icon name="arrow" size={15} /></Button></Card>)}</div> : <StudentEmptyState title="No released results" description="Results will appear here after they are released." />}
      </section>
    </div>
    <Card className="student-help-strip"><span className="student-summary-icon"><Icon name="inbox" /></span><p>Need help with an examination? Contact your institution for guidance.</p><Link to="/student/exams">Go to My Exams<Icon name="arrow" size={16} /></Link></Card>
  </div>
}
