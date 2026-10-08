import { Link } from 'react-router-dom'
import { useEffect, useState } from 'react'
import ManagedExamCTA from '../../components/common/ManagedExamCTA.jsx'
import ManagedExamRequest from '../../components/common/ManagedExamRequest.jsx'
import MadaarVision from './MadaarVision.jsx'
import { PublicLocaleTree, usePublicLocale, translatePublicText } from '../../context/PublicLocaleContext.jsx'
import { heroAudiences, installHeroRotation } from '../../utils/heroRotation.js'
import './landing.css'
import './madaar.css'
const steps = [
  ['Send', 'Provide the assessment requirements, questions and candidate information.'],
  ['We Configure', 'Madaar prepares the examination, access rules and candidate setup.'],
  ['Candidates Take the Exam', 'Candidates access and complete the configured assessment.'],
  ['Results & Reports', 'Review submissions, results and useful assessment reports.'],
]
const capabilities = [
  ['Structured question management', 'Organise questions by subject and topic, with review and approval workflows.'],
  ['Flexible assessment setup', 'Configure question selection, timing and candidate assignments.'],
  ['Candidate access options', 'Use account access or Quick Exam credentials for the configured examination.'],
  ['Exam integrity controls', 'Controlled access, pinned question revisions and attempt integrity records.'],
  ['Automatic objective marking', 'Mark supported objective questions and control when results are released.'],
  ['Results and reporting', 'Review submissions and assessment outcomes within separate institution workspaces.'],
]
function RotatingAudience() {
 const [active, setActive] = useState(0)
 const { locale } = usePublicLocale()
 useEffect(() => installHeroRotation(window, () => setActive(index => (index + 1) % heroAudiences.length)), [])
 return <p className="madaar-audience-line"><span key={`${locale}-${active}`} className="landing-hero__headline-content">{locale === 'ar' ? translatePublicText(heroAudiences[active]) : heroAudiences[active]}</span></p>
}
export default function LandingPage() {
 return <PublicLocaleTree><div className="madaar-home">
  <section className="madaar-hero" aria-labelledby="landing-title"><div><p className="madaar-kicker">Madaar | Assessment & Examination</p><h1 id="landing-title">Every assessment.<br /><span>A clearer way forward.</span></h1><p className="madaar-product-line">Create. Assess. Mark. Analyse. Improve.</p><RotatingAudience /><p>Conduct examinations with confidence and turn results into useful performance information. From question preparation to candidate delivery, Madaar keeps your assessment workflow connected.</p><div className="madaar-actions"><ManagedExamCTA className="madaar-button" /><Link className="madaar-button madaar-button--outline" to="/signin">Sign In</Link></div></div><aside className="madaar-journey" aria-label="Managed examination workflow"><p>From preparation to results</p><ol>{['Prepare questions', 'Configure the examination', 'Deliver to candidates', 'Review results & reports'].map((step, index) => <li key={step}><b>0{index + 1}</b><span>{step}</span></li>)}</ol><div>Managed Examinations | Available Now</div></aside></section>
  <section id="managed-examinations" className="madaar-managed" aria-labelledby="managed-title" data-public-reveal=""><div><span className="madaar-status">Available Now</span><p className="madaar-kicker">Managed Examinations</p><h2 id="managed-title">You bring the assessment.<br />We handle the technology.</h2><p>A managed service for schools, training programmes, organisations, competitions, professional programmes and educational institutes.</p><ManagedExamCTA className="madaar-button" /></div><ul>{['Question preparation and setup', 'Candidate setup and access', 'Examination configuration and delivery', 'Submission monitoring', 'Objective results and assessment reports'].map(item => <li key={item}><span aria-hidden="true">&#10003;</span>{item}</li>)}</ul></section>
  <section id="how-it-works" aria-labelledby="steps-title"><div className="madaar-section-heading landing-section__heading" data-public-reveal=""><p className="madaar-kicker">How Managed Examinations Work</p><h2 id="steps-title">A clear path from questions to results.</h2></div><div className="madaar-steps" data-public-reveal-group="">{steps.map(([title, copy], index) => <article className="landing-step" data-public-reveal="" key={title}><b>0{index + 1}</b><h3>{title}</h3><p>{copy}</p></article>)}</div></section>
  <section id="institution-workspace" className="madaar-workspace" aria-labelledby="workspace-title" data-public-reveal=""><div><span className="madaar-status madaar-status--pilot">Currently in Pilot</span><h2 id="workspace-title">Madaar Institution Workspace</h2><p>Your self-service institutional assessment workspace. Manage question banks, examinations, candidates, submissions, results and reports with your own team.</p><p>Review assessment outcomes to inform your next steps. Pilot availability is coordinated with participating institutions. <Link to="/contact?interest=institution-pilot">Enquire about the pilot</Link>.</p><Link className="madaar-button madaar-button--outline" to="/signin">Sign In to Your Workspace</Link></div><div className="madaar-workspace__tiles">{['Question banks', 'Assessments & exams', 'Candidate management', 'Submissions', 'Results', 'Reports'].map(item => <span key={item}>{item}</span>)}</div></section>
  <MadaarVision />
  <section aria-labelledby="value-title"><div className="madaar-section-heading" data-public-reveal=""><p className="madaar-kicker">Built around your assessment</p><h2 id="value-title">Practical tools. Connected workflows.</h2></div><div className="madaar-capabilities landing-grid" data-public-reveal-group="">{capabilities.map(([title, copy]) => <article className="landing-card" data-public-reveal="" key={title}><h3>{title}</h3><p>{copy}</p></article>)}</div></section>
  <section className="madaar-audiences" aria-labelledby="audience-title" data-public-reveal=""><p className="madaar-kicker">Who it is for</p><h2 id="audience-title">For organisations that assess with purpose.</h2><ul>{['Schools & school groups', 'Training & certification programmes', 'Madrasahs & Islamic Educational Institutes', 'NGOs & youth programmes', 'Competitions', 'Tutorial/CBT centres', 'Other organisations conducting structured assessments'].map(item => <li key={item}>{item}</li>)}</ul></section>
  <ManagedExamRequest /><p className="madaar-existing">Already have access? <Link to="/signin">Sign In</Link> or <Link to="/take-exam">Take an Exam</Link>.</p>
 </div></PublicLocaleTree>
}
