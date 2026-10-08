import { PublicLocaleTree } from '../../context/PublicLocaleContext.jsx'

const areas = [
  ['Teach', 'Curriculum and scheme-of-work support, lesson planning, teaching resources, AI-assisted lesson notes and presentation preparation.'],
  ['Learn', 'Learning materials, structured practice, assignments and submissions, feedback, targeted support and remediation based on learning gaps.'],
  ['Assess', 'Question banks, examinations, tests, quizzes, assignments, candidate delivery, marking, results and reports.'],
  ['Analyse', 'Student, class, subject and topic performance; learning gaps, trends, intervention needs and useful institutional insights.'],
  ['Improve', 'Better teaching decisions, targeted practice, remediation, intervention and feedback loops that support measurable learning improvement.'],
]

export default function MadaarVision() {
  return <PublicLocaleTree><section id="madaar-vision" className="madaar-vision" aria-labelledby="vision-title">
    <header className="madaar-vision__intro">
      <p className="madaar-kicker">Where We're Going</p>
      <h2 id="vision-title">Assessment is where we're starting.<br /><span>Better education is where we're going.</span></h2>
      <p>Madaar begins with one of education's most important feedback loops: assessment. But education does not begin with an examination, and it should not end with a score.</p>
      <p>We are building towards a connected education platform that supports the wider journey from teaching and learning to assessment, insight and continuous improvement.</p>
    </header>
    <div className="madaar-vision__direction">
      <h3>Where Madaar is going</h3>
      <p>This is our product direction, not a list of capabilities available today. Managed Examinations is available now; Institution Workspace is currently in pilot.</p>
    </div>
    <ol className="madaar-vision__loop" aria-label="Connected education vision">
      {areas.map(([title, description], index) => <li key={title} className={title === 'Assess' ? 'madaar-vision__area madaar-vision__area--current' : 'madaar-vision__area'}>
        <span className="madaar-vision__number" aria-hidden="true">0{index + 1}</span>
        <h4>{title}</h4>
        <p className="madaar-vision__status">{title === 'Assess' ? 'Starting with Assessment' : 'Future Direction'}</p>
        <p>{description}</p>
        {title === 'Assess' && <p className="madaar-vision__note">Assessment is our current foundation. We are delivering examination workflows today; this wider scope will develop over time.</p>}
        {title === 'Analyse' && <p className="madaar-vision__note">Basic assessment reporting is available today. Broader learning analytics are part of our future direction.</p>}
      </li>)}
    </ol>
    <aside className="madaar-vision__foundation" aria-labelledby="foundation-title">
      <div><p className="madaar-kicker">Currently in Pilot</p><h3 id="foundation-title">Built on your institution</h3></div>
      <div><p>A connected platform needs an institutional foundation: students, staff, classes and cohorts, subjects, roles and permissions, academic records, settings and administration.</p><p>Institution Workspace is currently in pilot. This foundation will grow with the platform; broader school-management capabilities are not generally available.</p></div>
    </aside>
  </section></PublicLocaleTree>
}
