import { useState } from 'react'
import { Link } from 'react-router-dom'
import Badge from '../../components/common/Badge.jsx'
import Button from '../../components/common/Button.jsx'
import Card from '../../components/common/Card.jsx'
import Icon from '../../components/common/Icon.jsx'
import './public-pages.css'

const capabilities = [
  ['Question Bank', 'Create, organise, review and reuse questions.', 'file'],
  ['Create Exams', 'Build examinations from approved questions and configure duration, marks and availability.', 'clipboard'],
  ['Online Examinations', 'Allow learners to take scheduled examinations through the candidate portal.', 'inbox'],
  ['Automatic Marking', 'Automatically mark supported objective question types.', 'chart'],
  ['Results Management', 'Generate, review and publish examination results.', 'layers'],
  ['Students & Classes', 'Organise learners into classes or cohorts.', 'users'],
  ['Examination Security', 'Use server-controlled timing, attempt limits, access rules and integrity controls.', 'staff'],
  ['Performance Reports', 'Understand examination performance using result-based reports.', 'chart'],
]

const workflow = [
  ['Set Up Your Institution', 'Add your institution and organise the people who manage assessments.', 'staff'],
  ['Create Questions', 'Build a question bank organised for the subjects and topics you teach.', 'file'],
  ['Create Examination', 'Choose approved questions and set the examination schedule and rules.', 'clipboard'],
  ['Students Take Exam', 'Learners access their scheduled examination through the candidate portal.', 'inbox'],
  ['Mark Submissions', 'Supported objective question types are marked automatically.', 'chart'],
  ['Review & Publish Results', 'Review completed results and release them when ready.', 'layers'],
  ['Understand Performance', 'Use result-based reports to see how assessments went.', 'chart'],
]

const workflowDetails = [
  {
    title: 'Set Up Your Institution, Staff, and Classes',
    copy: 'Get started without complicated administration. Add your institution details, organise staff and candidate groups, then prepare the subjects used for assessments.',
    points: ['Institution profile and contact details', 'Teachers, examiners and candidates', 'Groups and subject catalogues'],
    preview: 'institution',
  },
  {
    title: 'Create and Organize Your Questions',
    copy: 'Build questions for the subjects and topics you teach. Organise them for reuse and review question content before it is used in an examination.',
    points: ['Organise by subject and topic', 'Use supported objective question types', 'Review questions before use'],
    preview: 'questions',
  },
  {
    title: 'Create and Schedule Your Examination',
    copy: 'Select questions and configure the examination duration, marks, candidate access and availability window.',
    points: ['Choose questions for the assessment', 'Set duration and examination rules', 'Schedule the access window'],
    preview: 'assessment',
  },
  {
    title: 'Students Take the Exam Calmly Online',
    copy: 'Candidates see a focused examination screen with clear question navigation, review flags and a visible timer.',
    points: ['Access assigned examinations', 'Move between questions', 'Mark questions to review'],
    preview: 'candidate',
  },
  {
    title: 'Objective Questions Marked Automatically',
    copy: 'Supported objective responses are scored using the assessment answer key when an attempt is submitted.',
    points: ['Consistent scoring rules', 'Calculated candidate outcomes', 'Review results before release'],
    preview: 'marking',
  },
  {
    title: 'Review, Moderate, and Publish Results',
    copy: 'Staff can review completed outcomes and control when results become available to candidates.',
    points: ['Review results by candidate', 'Keep results private while reviewing', 'Publish when ready'],
    preview: 'results',
  },
  {
    title: 'Understand Student and Class Performance',
    copy: 'Use straightforward outcome summaries to review assessment performance by candidate group and subject.',
    points: ['Review score and grade distributions', 'Compare outcomes across groups', 'Identify areas for follow-up'],
    preview: 'reports',
  },
]

function PageIntro({ eyebrow, title, children, centered = false }) {
  return <header className={`public-page-intro${centered ? ' public-page-intro--centered' : ''}`}>
    <Badge variant="primary">{eyebrow}</Badge><h1>{title}</h1>{children && <p>{children}</p>}
  </header>
}

function CTASection({ title = 'Ready to simplify your examinations?', copy = 'See how the platform can support your organisation.', children }) {
  return <section className="public-cta"><div><p className="public-kicker public-kicker--light">School Assessment Platform</p><h2>{title}</h2><p>{copy}</p></div><div className="public-cta__actions">{children || <Button as={Link} to="/contact" variant="outline">Contact us</Button>}</div></section>
}

export function FeaturesPage() {
  const featureDetails = [
    { title: 'Build Your Question Bank', subtitle: 'Create and organise questions for every subject and topic.', icon: 'file', points: ['Organise questions by subject, topic and difficulty', 'Create supported objective question types', 'Review questions before using them in examinations', 'Import questions to prepare a reusable bank'], preview: 'question-bank' },
    { title: 'Create Better Examinations', subtitle: 'Build quizzes, tests, mock exams, term exams and other assessments.', icon: 'clipboard', points: ['Create class quizzes, end-of-term exams and assessments', 'Select approved questions or add new ones directly', 'Set examination duration, marks and availability', 'Schedule examinations for their intended candidates'], preview: 'exam-builder' },
    { title: 'Conduct Exams Online', subtitle: 'Give candidates a simple examination experience on desktop or mobile.', icon: 'inbox', points: ['Provide candidates access to their assigned examinations', 'Save responses as candidates work through questions', 'Navigate between questions and mark items for review', 'Submit responses when the examination is complete'], preview: 'candidate-exam' },
    { title: 'Mark Automatically', subtitle: 'Save time with automatic marking for supported objective questions.', icon: 'chart', points: ['Mark supported objective question types', 'Calculate outcomes from submitted answers', 'Review results before making them available', 'Use consistent marking rules across candidates'], preview: 'marking' },
    { title: 'Manage Results', subtitle: 'Review, publish and manage examination results from one place.', icon: 'layers', points: ['View results for completed examinations', 'Review candidate outcomes before publication', 'Publish results when they are ready', 'Keep candidate access aligned with release status'], preview: 'results' },
    { title: 'Understand Performance', subtitle: 'See clear result-based reports on examination outcomes.', icon: 'chart', points: ['Review outcomes by assessment and group', 'Compare subject results where available', 'Use score and grade distributions to review outcomes', 'Identify topics for further teaching or question review'], preview: 'reports' },
    { title: 'Manage Your Institution', subtitle: 'Keep learners, teachers, classes and subjects organised.', icon: 'users', points: ['Organise candidates within your institution', 'Assign staff the appropriate institution roles', 'Group learners into classes or cohorts', 'Configure institution subjects and examination access'], preview: 'institution' },
    { title: 'Protect Your Examinations', subtitle: 'Control access, timing, attempts and submitted answers.', icon: 'staff', points: ['Secure candidate access to assigned examinations', 'Use server-controlled examination timing', 'Apply attempt limits to reduce duplicate submissions', 'Lock submitted answers and record key security events'], preview: 'security' },
  ]

  return <div className="public-page public-features">
    <section className="features-hero" aria-labelledby="features-title">
      <div className="features-hero__inner">
        <Badge variant="primary"><span className="features-hero__dot" />School &amp; Institution Assessment Platform</Badge>
        <h1 id="features-title">Everything You Need to Run Better Assessments</h1>
        <p>Create questions, conduct examinations, mark submissions and publish results — all from one simple platform built for educational institutions.</p>
        <div className="features-hero__actions"><Button as={Link} to="/setup">Setup Preview</Button><Button as={Link} to="/how-it-works" variant="outline">See How It Works</Button></div>
        <div className="features-audience-strip" aria-label="Organisations supported">
          {['Schools', 'Madrasahs & Islamic Institutes', 'CBT Centres', 'Training Organisations', 'Competitions'].map((label, index) => <span key={label}>{index > 0 && <i aria-hidden="true">•</i>}<b>{label}</b></span>)}
        </div>
      </div>
    </section>
    <div className="features-promise"><span>One platform. Every stage: Create, Assess, Mark, Analyse, Improve.</span></div>

    <section className="features-detail-section" aria-labelledby="features-detail-title">
      <header className="features-section-heading"><Badge variant="primary">Features &amp; Capabilities</Badge><h2 id="features-detail-title">Designed for Clarity, Built for Schools</h2><p>Everything you need to manage your institution&apos;s exams with confidence.</p></header>
      <div className="features-detail-list">
        {featureDetails.map((feature, index) => <article className={`features-detail${index % 2 ? ' features-detail--reverse' : ''}`} key={feature.title}>
          <div className="features-detail__copy"><Badge variant="primary"><Icon name={feature.icon} size={13} />Feature {index + 1}</Badge><h3>{feature.title}</h3><p className="features-detail__subtitle">{feature.subtitle}</p><ul>{feature.points.map(point => <li key={point}><Icon name="check" size={15} />{point}</li>)}</ul></div>
          <FeaturePreview type={feature.preview} />
        </article>)}
      </div>
    </section>

    <section className="features-audiences" aria-labelledby="features-audiences-title"><div className="features-audiences__inner"><header className="features-section-heading"><Badge variant="primary">Institutions We Serve</Badge><h2 id="features-audiences-title">Built for Your Learning Environment</h2><p>Structured assessment tools that adapt to diverse academic settings.</p></header><div className="features-audience-grid">{[['Schools', 'Primary and secondary schools running regular assessments, mock exams and term examinations.', 'cap'], ['Madrasahs & Islamic Institutes', 'Institutions delivering Islamic studies, Arabic language, memorisation and core academic subjects.', 'book'], ['CBT Centres', 'Centres preparing learners for online tests and computer-based examinations.', 'inbox'], ['Training Organisations', 'Professional bodies and vocational institutions assessing learners through structured tests and certifications.', 'staff'], ['Competitions', 'Academic olympiads, inter-school quizzes and educational competitions with clear ranking and result release.', 'chart']].map(([title, description, icon]) => <Card as="article" className="features-audience-card" key={title}><span className="public-icon"><Icon name={icon} size={21} /></span><h3>{title}</h3><p>{description}</p></Card>)}</div></div></section>

    <section className="features-cta" aria-labelledby="features-cta-title"><div><Badge variant="primary">Assessment made simpler</Badge><h2 id="features-cta-title">Ready to Run Clearer, More Dependable Assessments?</h2><p>Explore how the platform can support your institution&apos;s examination workflow.</p></div><div className="features-cta__actions"><Button as={Link} to="/how-it-works" variant="outline">See How It Works</Button><Button as={Link} to="/contact">Contact Us</Button></div></section>
  </div>
}

function FeaturePreview({ type }) {
  const title = {
    'question-bank': 'Question editor preview', 'exam-builder': 'Assessment configuration', 'candidate-exam': 'Candidate examination preview',
    marking: 'Marking workflow', results: 'Results review', reports: 'Outcome overview', institution: 'Institution workspace', security: 'Examination safeguards',
  }[type]
  return <div className={`feature-preview feature-preview--${type}`} role="img" aria-label={`${title} illustration`}>
    {type === 'question-bank' && <><PreviewBar title="Question editor" badge="Multiple choice" /><div className="feature-preview__body"><div className="preview-meta"><span>Subject</span><b>Choose a subject</b><span>Topic</span><b>Choose a topic</b></div><div className="preview-prompt"><i /><i /><i /></div>{['Answer option', 'Answer option', 'Answer option', 'Answer option'].map((item, index) => <div className={`preview-option${index === 1 ? ' is-selected' : ''}`} key={`${item}-${index}`}><i />{item}</div>)}<div className="preview-explanation"><strong>Answer explanation</strong><i /><i /></div></div></>}
    {type === 'exam-builder' && <><PreviewBar title="Assessment configuration" badge="Draft" /><div className="feature-preview__body"><div className="preview-fields">{['Examination name', 'Class or cohort', 'Duration', 'Availability'].map(label => <div key={label}><span>{label}</span><i /></div>)}</div><div className="preview-schedule"><span>Selected questions</span><i /><span>Schedule window</span><i /></div></div></>}
    {type === 'candidate-exam' && <><PreviewBar title="Candidate examination" badge="In progress" /><div className="feature-preview__body"><div className="preview-question-head"><span>Question</span><span>Time remaining</span></div><div className="preview-prompt"><i /><i /></div>{['Response option', 'Response option', 'Response option'].map((item, index) => <div className={`preview-option${index === 0 ? ' is-selected' : ''}`} key={`${item}-${index}`}><i />{item}</div>)}<div className="preview-exam-controls"><span>Mark for review</span><b>Next question <Icon name="arrow" size={13} /></b></div></div></>}
    {type === 'marking' && <><PreviewBar title="Automatic marking" badge="Review available" /><div className="feature-preview__body"><div className="preview-summary"><div><span>Question type</span><strong>Objective</strong></div><div><span>Marking status</span><strong>Ready for review</strong></div></div>{['Submitted answers', 'Marking rules', 'Result review'].map((label, index) => <div className="preview-status-row" key={label}><i className={`preview-status-row__dot preview-status-row__dot--${index}`} /><span>{label}</span><b>{index === 0 ? 'Received' : index === 1 ? 'Applied' : 'Available'}</b></div>)}</div></>}
    {type === 'results' && <><PreviewBar title="Examination results" badge="Review before release" /><div className="feature-preview__body"><div className="preview-table-head"><span>Candidate</span><span>Outcome</span></div>{['Candidate result', 'Candidate result', 'Candidate result'].map((label, index) => <div className="preview-table-row" key={`${label}-${index}`}><span><i />{label}</span><b>{index === 0 ? 'Ready to review' : 'Pending review'}</b></div>)}<div className="preview-release"><Icon name="check" size={14} />Results remain private until released</div></div></>}
    {type === 'reports' && <><PreviewBar title="Assessment outcomes" badge="Selected assessment" /><div className="feature-preview__body"><div className="preview-chart"><div><i style={{ height: '42%' }} /><span>Subject</span></div><div><i style={{ height: '68%' }} /><span>Subject</span></div><div><i style={{ height: '55%' }} /><span>Subject</span></div><div><i style={{ height: '32%' }} /><span>Subject</span></div></div><div className="preview-report-footer"><span>Outcome distribution</span><b>Review results by group and subject</b></div></div></>}
    {type === 'institution' && <><PreviewBar title="Institution workspace" badge="Institution context" /><div className="feature-preview__body preview-institution-grid">{[['Learners', 'users'], ['Teachers & Examiners', 'staff'], ['Classes & Cohorts', 'layers'], ['Subjects', 'book']].map(([label, icon]) => <div key={label}><Icon name={icon} size={16} /><span>{label}</span><small>Manage within your institution</small></div>)}</div></>}
    {type === 'security' && <><PreviewBar title="Institutional safeguards" badge="Enabled" /><div className="feature-preview__body">{['Assigned candidate access', 'Server-controlled timing', 'Attempt limit', 'Submitted answer lock', 'Security audit events'].map((label, index) => <div className="preview-security-row" key={label}><Icon name={['users', 'clock', 'staff', 'check', 'file'][index]} size={15} /><span>{label}</span><b>{['Enforced', 'Active', 'Protected', 'Locked', 'Recorded'][index]}</b></div>)}</div></>}
  </div>
}

function PreviewBar({ title, badge }) {
  return <div className="feature-preview__bar"><div><i /><i /><i /></div><strong>{title}</strong><span>{badge}</span></div>
}

export function HowItWorksPage() {
  return <div className="public-how">
    <section className="workflow-hero">
      <div className="workflow-hero__copy">
        <Badge variant="primary">Simple, dependable assessments</Badge>
        <h1>How assessments work, from setup to final results</h1>
        <p>A clear, dependable walkthrough of how schools, colleges, madrasahs and training centres prepare and manage examinations from start to finish.</p>
        <div className="workflow-hero__actions"><Button as={Link} to="/setup">Get started<Icon name="arrow" size={17} /></Button><Button as={Link} to="/features" variant="outline"><Icon name="layers" size={16} />Explore features</Button></div>
        <div className="workflow-hero__assurances"><span><Icon name="check" size={14} />Assessment-focused setup</span><span><Icon name="check" size={14} />Clear online exam room</span><span><Icon name="check" size={14} />Objective marking</span></div>
      </div>
      <WorkflowPreview type="candidate" hero />
    </section>

    <section className="workflow-overview" aria-labelledby="workflow-overview-title">
      <div className="workflow-overview__heading"><div><p className="public-kicker">The complete examination journey</p><h2 id="workflow-overview-title">The 7-step assessment process</h2><p>A straightforward path built for school administrators, teachers and examiners.</p></div><Badge variant="success"><Icon name="check" size={13} />Simple, human &amp; orderly</Badge></div>
      <ol className="workflow-overview__grid">{workflow.map(([title, , icon], index) => <li className="workflow-overview__step" key={title}><span className="workflow-overview__top"><b>{String(index + 1).padStart(2, '0')}</b><Icon name={icon} size={16} /></span><strong>{['Set Up Institution', 'Create Questions', 'Build Exam', 'Take the Exam', 'Mark Papers', 'Publish Results', 'View Insights'][index]}</strong><span>{['Institution setup', 'Question bank', 'Exam schedule', 'Student room', 'Automatic tally', 'Staff review', 'Class reports'][index]}</span></li>)}</ol>
    </section>

    <section className="workflow-details" aria-label="Assessment process details">
      {workflowDetails.map((step, index) => <article className={`workflow-detail${index % 2 ? ' workflow-detail--reverse' : ''}`} key={step.title}>
        <div className="workflow-detail__copy"><Badge variant="primary">Step {String(index + 1).padStart(2, '0')} · {['Institution setup', 'Question bank', 'Exam schedule', 'Student exam room', 'Automatic marking', 'Staff publication', 'Performance reports'][index]}</Badge><h2>{step.title}</h2><p>{step.copy}</p><ul>{step.points.map(point => <li key={point}><Icon name="check" size={15} />{point}</li>)}</ul></div>
        <WorkflowPreview type={step.preview} />
      </article>)}
    </section>

    <section className="workflow-cta"><div><p className="public-kicker public-kicker--light">Simpler assessment routines</p><h2>Ready to run simpler, more dependable assessments?</h2><p>Explore the assessment workflow or prepare an institution preview.</p></div><div className="workflow-cta__actions"><Button as={Link} to="/setup" variant="outline">Get started</Button><Button as={Link} to="/contact">Contact us</Button></div></section>
  </div>
}

function WorkflowPreview({ type, hero = false }) {
  const title = { institution: 'Institution setup', questions: 'Question bank', assessment: 'Examination configuration', candidate: 'Online examination', marking: 'Automatic marking', results: 'Results review', reports: 'Performance overview' }[type]
  const rows = {
    institution: [['Institution profile', 'Ready'], ['Staff and candidates', 'Organised'], ['Groups and subjects', 'Prepared']],
    assessment: [['Questions', 'Selected'], ['Duration and marks', 'Configured'], ['Candidate access', 'Scheduled']],
    marking: [['Objective responses', 'Scored'], ['Outcome totals', 'Calculated'], ['Staff review', 'Available']],
    results: [['Candidate outcomes', 'In review'], ['Publication status', 'Private'], ['Staff decision', 'Required']],
  }[type]
  return <div className={`workflow-preview${hero ? ' workflow-preview--hero' : ''} workflow-preview--${type}`} aria-hidden="true">
    <div className="workflow-preview__top"><span className="workflow-preview__brand"><i /><i /><i /></span><strong>{title}</strong><span className="workflow-preview__badge">{type === 'candidate' ? 'Preview' : 'Workspace'}</span></div>
    {type === 'candidate' ? <div className="workflow-preview__exam"><div className="workflow-preview__exam-meta"><span>Question 1</span><b><Icon name="clock" size={13} /> Time remaining</b></div><h3>Examination question</h3><div className="workflow-preview__text-lines"><i /><i /></div><div className="workflow-preview__answer is-selected"><i />Answer option</div><div className="workflow-preview__answer"><i />Answer option</div><div className="workflow-preview__answer"><i />Answer option</div><div className="workflow-preview__exam-footer"><span><Icon name="file" size={13} />Mark for review</span><b>Next question<Icon name="arrow" size={13} /></b></div></div>
      : type === 'questions' ? <div className="workflow-preview__question"><div className="workflow-preview__tags"><span>Subject</span><b>Question type</b><span>Topic</span><b>Difficulty</b></div><h3>Question editor</h3><div className="workflow-preview__text-lines"><i /><i /><i /></div>{[1, 2, 3, 4].map((item, index) => <div className={`workflow-preview__answer${index === 1 ? ' is-selected' : ''}`} key={item}><i />Answer option</div>)}<div className="workflow-preview__footnote">Answer explanation</div></div>
        : <div className="workflow-preview__workspace">{type === 'reports' ? <div className="workflow-preview__chart">{[58, 78, 42, 65, 33].map((height, index) => <i key={index} style={{ height: `${height}%` }} />)}</div> : <>{(rows || [['Assessment overview', 'Ready'], ['Review status', 'Available'], ['Next step', 'Continue']]).map(([label, status]) => <div className="workflow-preview__row" key={label}><span><i />{label}</span><b>{status}</b></div>)}</>}<div className="workflow-preview__summary"><span>Assessment workflow</span><i /><i /><i /></div></div>}
  </div>
}

export function PricingPage() {
  const tiers = [
    { level: 'Tier I', name: 'Starter', copy: 'For smaller schools, independent learning centres and institutions getting started with online assessments.', quote: 'Contact us for an institutional quote', items: ['Core examination setup and scheduling', 'Question bank for supported question types', 'Online candidate examination', 'Automatic marking for supported questions', 'Result review and release controls', 'Onboarding guidance'], action: 'Contact us' },
    { level: 'Tier II', name: 'Professional', copy: 'For growing schools, colleges and training organisations managing regular examinations across terms.', quote: 'Contact us for an institutional quote', items: ['Everything in Starter', 'Expanded student cohorts and exam batches', 'Unlimited staff, teacher and examiner accounts', 'Subject catalogue and topic taxonomy', 'Configurable pass benchmarks and grade bands', 'Result moderation and controlled release', 'Multi-class comparative reporting', 'Priority institutional support'], action: 'Request institutional demo' },
    { level: 'Tier III', name: 'Institution', copy: 'For larger institutions, multi-campus schools, exam boards and organisations with broader assessment needs.', quote: 'Custom institutional plan', items: ['Everything in Professional', 'Multi-campus and multi-branch coordination', 'Coordinated exam schedules across departments', 'Custom grading scales and transcripts', 'Dedicated account manager and exam support line', 'High-volume exam session planning'], action: 'Contact sales' },
  ]
  const questions = [
    ['How is institutional pricing structured?', 'Pricing is discussed based on your active candidate volume and assessment requirements over the academic year. Contact us to talk through your institution’s needs.'],
    ['Can the platform support both small quizzes and major term exams?', 'The assessment workflow is designed for different exam formats and schedules. Contact us to discuss how it fits your programme.'],
    ['How is institutional assessment data managed?', 'Access to institution records is scoped to authorised memberships. Staff control when reviewed results are released to candidates.'],
  ]
  return <div className="public-page public-pricing">
    <section className="pricing-hero"><Badge variant="primary"><Icon name="check" size={14} />Plans built for educational institutions</Badge><h1>Transparent, institution-grade pricing</h1><p>Plans designed for institutions of different sizes. Tailored to your student cohort and assessment schedule with no hidden fees or surprise surcharges.</p><div className="pricing-assurances"><span><Icon name="check" />Multi-campus ready</span><span><Icon name="check" />Secure examination data</span><span><Icon name="check" />Calm, reliable delivery</span></div><small className="pricing-preview-note">Plan names and inclusions are illustrative. Contact the team to confirm current availability and receive an institutional quote.</small></section>
    <div className="pricing-grid">{tiers.map((tier, index) => <Card as="article" className={`pricing-card${index === 1 ? ' pricing-card--featured' : ''}`} key={tier.name}>{index === 1 && <Badge variant="primary">Most popular</Badge>}<p className="pricing-card__eyebrow">{tier.level}</p><h2>{tier.name}</h2><p className="pricing-card__copy">{tier.copy}</p><div className="pricing-quote"><small>{index === 2 ? 'Tailored agreement' : 'Pricing model'}</small><strong>{tier.quote}</strong><span>{index === 2 ? 'A tailored discussion around your institution’s examination calendar.' : 'Annual or term-based cohort licensing tailored to your institution.'}</span></div><h3>Included platform features</h3><ul>{tier.items.map(item => <li key={item}><Icon name="check" size={14} />{item}</li>)}</ul><Button as={Link} to="/contact" variant={index === 1 ? 'primary' : 'outline'}>{tier.action}<Icon name="arrow" size={17} /></Button></Card>)}</div>
    <section className="pricing-capacity"><div className="pricing-capacity__heading"><div><p className="public-kicker">Institutional delivery &amp; capacity</p><h2>From individual classroom quizzes to campus-wide term examinations</h2><p>Discuss a setup that fits your institution’s assessment schedule.</p></div><div className="pricing-capacity__legend"><span>Small schools &amp; centres</span><span>Mid-sized colleges</span><span>Multi-campus institutions</span></div></div><div className="pricing-scale" aria-label="Institution size from single school setup through multi-class batching to network-wide exams"><div className="pricing-scale__line"/><span className="pricing-scale__point pricing-scale__point--one">Single school setup</span><span className="pricing-scale__point pricing-scale__point--two">Multi-class batching</span><span className="pricing-scale__point pricing-scale__point--three">Institution-wide exams</span></div><div className="pricing-capacity__notes"><div><strong>Flexible structure</strong><span>Discuss campus and cohort needs</span></div><div><strong>Exam scheduling</strong><span>Plan around your academic calendar</span></div><div><strong>Clear requirements</strong><span>Talk with the team before deciding</span></div></div></section>
    <section className="pricing-faq"><header><p className="public-kicker">Guidance &amp; compliance</p><h2>Institutional frequently asked questions</h2><p>Clear answers to institutional licensing, examination scheduling and deployment.</p></header>{questions.map(([question, answer]) => <article key={question}><span className="public-icon"><Icon name="file" size={17} /></span><div><h3>{question}</h3><p>{answer}</p></div></article>)}</section>
    <section className="pricing-cta"><div><p className="public-kicker public-kicker--light">Institutional onboarding</p><h2>Ready to simplify assessment management for your institution?</h2><p>Speak with our team to discuss your assessment schedule, student numbers and institutional requirements.</p></div><div><Button as={Link} to="/contact" variant="outline">Request institutional demo</Button><Button as={Link} to="/contact">Contact us</Button></div></section>
  </div>
}

export function AboutPage() {
  const principles = [
    ['Simplicity over complexity', 'Focused examination tools without unrelated administration modules or settings.', 'layers'],
    ['A calm student experience', 'A clear exam room with a visible timer and question review controls.', 'clock'],
    ['Teacher and staff control', 'Staff review results and control when outcomes are published.', 'staff'],
    ['Clear, actionable reports', 'Straightforward summaries help educators review assessment outcomes.', 'chart'],
  ]
  const audiences = [
    ['Schools & Colleges', 'Run classroom quizzes, weekly tests, mock exams and end-of-term assessments.', 'cap'],
    ['Madrasahs & Islamic Institutes', 'Organise student evaluations across Islamic studies, Arabic and core subjects.', 'book'],
    ['CBT & Tutorial Centres', 'Prepare computer-based testing and practice examination sessions.', 'inbox'],
    ['Training & Professional Programmes', 'Manage end-of-course assessments and certification checks.', 'staff'],
  ]
  return <div className="about-contact-page">
    <section className="about-contact-hero"><Badge variant="primary"><Icon name="check" size={14} />Simple, dependable assessments</Badge><h1>Empowering educational institutions to manage assessments with confidence</h1><p>We build straightforward, accessible examination software for schools, madrasahs, colleges, training providers and examination coordinators. Create questions, conduct exams, mark submissions and review results in one focused platform.</p><div className="about-contact-hero__pillars">{[['Clean question banking', 'Organised by subject & topic'], ['Calm exam room', 'For desktop & tablet'], ['Automatic marking', 'Supported objective questions'], ['Controlled results', 'Staff review before release']].map(([title, copy], index) => <div key={title}><strong>{title}</strong><span>{copy}</span></div>)}</div></section>

    <div className="about-contact-grid">
      <section className="about-mission"><p className="public-kicker"><Icon name="file" size={14} />Our mission</p><h2>Making examination management straightforward, calm, and dependable for every educator.</h2><p>Running examinations often involves paper printing, complicated spreadsheets and hours spent tallying scores. School Assessment Platform brings question organisation, online exams, marking and results together in a clear assessment workflow.</p><div className="assessment-lifecycle"><div><strong>Assessment lifecycle</strong><span>Clear &amp; structured</span></div><ol>{['Create questions', 'Schedule exam', 'Take exam', 'Mark & publish', 'Review outcomes'].map((step, index) => <li key={step}><b>{index + 1}.</b> {step}</li>)}</ol></div></section>

      <section className="about-contact-card" id="about-contact"><p className="public-kicker"><Icon name="inbox" size={14} />Direct engagement</p><h2>Let&apos;s talk</h2><p>Have a question about the platform or want to discuss your school, course or examination needs? Get in touch with the team.</p><Button as={Link} to="/contact" className="about-contact-card__button"><Icon name="arrow" size={16} />Contact us</Button><div className="about-contact-card__details"><div><span className="public-icon"><Icon name="inbox" size={17} /></span><p><strong>Enquiries</strong><span>Use the contact page to reach us.</span></p></div><div><span className="public-icon"><Icon name="staff" size={17} /></span><p><strong>For institutions</strong><span>Schools, training providers and exam teams.</span></p></div></div><div className="about-contact-card__status"><span>Assessment support</span><strong>Contact the team</strong></div></section>

      <section className="about-metrics" aria-label="Platform capabilities">{[['Objective marking', 'Supported question types can be scored automatically.', 'check'], ['Online examination', 'Provide a focused examination experience for candidates.', 'clock'], ['Institution focus', 'Built around schools, centres and training programmes.', 'staff']].map(([title, copy, icon], index) => <article className="about-metric" key={title}><span className="public-icon"><Icon name={icon} size={18} /></span><strong>0{index + 1}</strong><h3>{title}</h3><p>{copy}</p></article>)}</section>

      <section className="about-principles"><p className="public-kicker"><Icon name="check" size={14} />Guiding principles</p><h2>What we stand for</h2><div>{principles.map(([title, copy, icon]) => <article key={title}><h3><Icon name={icon} size={16} />{title}</h3><p>{copy}</p></article>)}</div></section>

      <section className="about-audiences"><p className="public-kicker"><Icon name="users" size={14} />Who we serve</p><h2>Built for diverse educational environments</h2><p>Support for classroom tests, training courses and independent examination programmes.</p><div>{audiences.map(([title, copy, icon]) => <article key={title}><h3><Icon name={icon} size={17} />{title}</h3><p>{copy}</p></article>)}</div></section>
      <section className="about-trusted"><p>Designed for schools, centres and institutional educators</p><div>{['Schools', 'Colleges', 'Training', 'CBT centres', 'Examination teams'].map(name => <strong key={name}>{name}</strong>)}</div></section>
    </div>
  </div>
}

export function ContactPage() {
  const [submitted, setSubmitted] = useState(false)
  function handleSubmit(event) { event.preventDefault(); setSubmitted(true) }
  return <div className="public-page public-contact">
    <PageIntro eyebrow="Contact" title="Let’s talk about your assessments">Tell us a little about your organisation and what you need. This form is a visual preview and is not connected to message delivery.</PageIntro>
    <div className="contact-grid"><section className="contact-copy"><span className="public-icon"><Icon name="inbox" size={24} /></span><h2>Start a conversation</h2><p>Share a question about using School Assessment Platform for your school, training programme or examination organisation.</p><div className="contact-prompt"><strong>What happens next?</strong><p>This demo form does not send or store your information. Contact submission will be connected when a supported contact channel is configured.</p></div></section>
      <form className="public-form contact-form" onSubmit={handleSubmit}>
        <div className="public-form__row"><label className="form-field"><span className="form-label">Name</span><input className="form-control" name="name" autoComplete="name" required /></label><label className="form-field"><span className="form-label">Email</span><input className="form-control" type="email" name="email" autoComplete="email" required /></label></div>
        <label className="form-field"><span className="form-label">Organisation</span><input className="form-control" name="organisation" autoComplete="organization" /></label>
        <label className="form-field"><span className="form-label">Message</span><textarea className="form-control form-textarea" name="message" rows="5" required /></label>
        <Button type="submit">{submitted ? 'Preview noted' : 'Send message'}<Icon name="arrow" size={17} /></Button>
        {submitted && <p className="form-hint" role="status">This form is not connected yet, so your message has not been sent.</p>}
      </form></div>
  </div>
}

export function SignInPage() {
  const [notice, setNotice] = useState(false)
  const [showPassword, setShowPassword] = useState(false)
  function handleSubmit(event) { event.preventDefault(); setNotice(true) }
  return <div className="public-page public-auth-page"><section className="auth-panel"><div className="auth-panel__brand"><span className="wordmark__mark" aria-hidden="true">SA</span><span>School Assessment<br />Platform</span></div><div className="auth-panel__message"><p className="public-kicker public-kicker--light">Assessment workspace</p><h1>Welcome back</h1><p className="auth-panel__slogan">Create. Assess. Mark. Analyse. Improve.</p><p>Sign in to manage examinations, assessments and results.</p><div className="auth-panel__flow"><span>Create</span><i /><span>Assess</span><i /><span>Mark</span><i /><span>Results</span></div></div><p className="auth-panel__foot">For schools, training providers and examination organisations.</p></section>
    <section className="auth-form-panel"><div className="auth-form-wrap"><PageIntro eyebrow="Institutional access" title="Sign in to your account">Enter your details to continue.</PageIntro><form className="public-form" onSubmit={handleSubmit}><label className="form-field"><span className="form-label">Email address</span><input className="form-control" type="email" name="email" autoComplete="username" required /></label><label className="form-field"><span className="form-label">Password</span><div className="auth-password"><input className="form-control" type={showPassword ? 'text' : 'password'} name="password" autoComplete="current-password" required /><button type="button" aria-label={showPassword ? 'Hide password' : 'Show password'} onClick={() => setShowPassword(value => !value)}><Icon name="eye" size={18} /></button></div></label><div className="auth-options"><label><input type="checkbox" />Remember this device <small>(preview only)</small></label><button type="button" className="text-action" disabled aria-disabled="true">Forgot password?</button></div><Button type="submit" className="auth-submit">Sign In<Icon name="arrow" size={17} /></Button>{notice && <p className="form-hint" role="status">Sign-in is not connected yet. No login was attempted.</p>}</form><p className="auth-form__foot">Sign-in and remembered-device controls are visual previews; no account session is stored.</p></div></section></div>
}

export function SetupPage() {
  const [notice, setNotice] = useState(false)
  return <div className="public-page public-setup"><aside className="setup-aside"><div className="setup-aside__top"><div className="auth-panel__brand"><span className="wordmark__mark" aria-hidden="true">SA</span><span>AssessIQ<small>Institutional</small></span></div><Badge variant="primary"><i className="setup-status-dot"/>Institution onboarding</Badge></div><div className="setup-aside__main"><Badge variant="primary"><i className="setup-status-dot"/>Step 1 of 2</Badge><h1>Set Up Your Institution</h1><p>Get your organisation ready to create assessments, conduct examinations and manage results.</p><div className="setup-journey"><strong>Assessment journey</strong><div><span>Create</span><i/><span>Assess</span><i/><span>Mark</span><i/><span>Results</span></div></div><ul>{['Schools & colleges','Madrasahs & Islamic institutes','Courses & training programmes','CBT & tutorial centres'].map(item=><li key={item}><Icon name="check" size={15}/>{item}</li>)}</ul></div><div className="setup-aside__footer"><span>AssessIQ Institutional Platform</span><span><Icon name="staff" size={15}/>Secure data protection</span></div></aside>
    <section className="setup-content"><div className="setup-form-wrap"><header className="setup-form-heading"><h2>Set up your institution</h2><p>Enter your institution details to get started.</p></header><form className="public-form setup-form" onSubmit={event => { event.preventDefault(); setNotice(true) }}><label className="form-field"><span className="form-label">Institution name <b>*</b></span><div className="setup-input"><Icon name="home" size={20}/><input className="form-control" name="institution" placeholder="e.g. Al-Hikmah Academy or Greenfield College" required /></div></label><label className="form-field"><span className="form-label">Institution type <b>*</b></span><div className="setup-input"><Icon name="layers" size={20}/><select className="form-control form-select" name="type" defaultValue="" required><option value="" disabled>Select institution type...</option><option>School or College</option><option>Madrasah or Islamic Institute</option><option>Training Programme</option><option>Professional Examination Programme</option><option>CBT or Tutorial Centre</option><option>Competition or Educational Programme</option></select></div></label><label className="form-field"><span className="form-label setup-label-split">Email address <b>*</b><small>Contact email for administrative notices</small></span><div className="setup-input"><Icon name="inbox" size={20}/><input className="form-control" type="email" name="email" placeholder="admin@example.com" required /></div></label><label className="form-field"><span className="form-label">Phone number <b>*</b></span><div className="setup-input"><Icon name="staff" size={20}/><input className="form-control" type="tel" name="phone" placeholder="+1 (555) 000-0000" required /></div></label><label className="form-field"><span className="form-label">Address <b>*</b></span><div className="setup-input"><Icon name="home" size={20}/><input className="form-control" name="address" placeholder="Street address, City, Region" required /></div></label><Button type="submit" className="setup-submit">Continue<Icon name="arrow" size={17}/></Button>{notice && <p className="form-hint" role="status">This is a design preview. No institution or account was created.</p>}</form><div className="setup-help">Need help? <Link to="/contact">Contact support</Link></div></div></section>
  </div>
}
