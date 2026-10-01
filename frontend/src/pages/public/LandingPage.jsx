import { Link } from 'react-router-dom'
import Badge from '../../components/common/Badge.jsx'
import Button from '../../components/common/Button.jsx'
import Card from '../../components/common/Card.jsx'
import Icon from '../../components/common/Icon.jsx'
import './landing.css'

const audiences = [
  { title: 'Schools & Colleges', description: 'Create class tests, continuous assessments, mock exams and examinations.', icon: 'book' },
  { title: 'Courses & Training', description: 'Assess learners at the end of courses and training programmes.', icon: 'layers' },
  { title: 'Professional Exams', description: 'Conduct structured professional and certification assessments.', icon: 'staff' },
  { title: 'Madrasahs & Islamic Institutes', description: 'Manage examinations for Islamic education and learning programmes.', icon: 'cap' },
  { title: 'CBT & Tutorial Centres', description: 'Create and conduct computer-based examinations.', icon: 'clipboard' },
  { title: 'Competitions & Educational Programmes', description: 'Run structured quizzes, competitions and educational assessments.', icon: 'chart' },
]

const features = [
  { title: 'Question Bank', description: 'Create and organise reusable examination questions.', icon: 'file', tag: 'QUESTION BANK' },
  { title: 'Create Examinations', description: 'Build structured exams from your approved question bank.', icon: 'clipboard', tag: 'EXAM BUILDER' },
  { title: 'Online Examinations', description: 'Let students and learners take examinations online.', icon: 'inbox', tag: 'CANDIDATE EXPERIENCE' },
  { title: 'Automatic Marking', description: 'Automatically mark supported objective question types.', icon: 'chart', tag: 'INSTANT SCORING' },
  { title: 'Results Management', description: 'Review submissions, manage results and release approved outcomes.', icon: 'layers', tag: 'RESULTS' },
  { title: 'Students & Classes', description: 'Organise learners into classes or cohorts for assessment.', icon: 'users', tag: 'LEARNER GROUPS' },
  { title: 'Examination Security', description: 'Protect examination access, attempts and submitted answers.', icon: 'staff', tag: 'ASSESSMENT INTEGRITY' },
  { title: 'Performance Reports', description: 'Review examination outcomes through result-based reports.', icon: 'chart', tag: 'RESULTS REVIEW' },
]

const steps = [
  { title: 'Create Questions', description: 'Build a reusable question bank for your assessments.', icon: 'file' },
  { title: 'Build an Exam', description: 'Select questions and configure an examination.', icon: 'clipboard' },
  { title: 'Invite Learners', description: 'Provide candidates access to their examination.', icon: 'users' },
  { title: 'Mark Submissions', description: 'Objective question types are marked automatically.', icon: 'chart' },
  { title: 'Publish Results', description: 'Review outcomes and release results when ready.', icon: 'layers' },
  { title: 'Review Performance', description: 'Use result-based reports to understand outcomes.', icon: 'staff' },
]

const plans = [
  { name: 'Starter', description: 'For a single school, centre or programme getting started with structured assessments.', items: ['Institution requirements', 'Learner groups and subjects', 'Examination schedule'], action: 'Contact us' },
  { name: 'Professional', description: 'For organisations managing regular examinations across courses or cohorts.', items: ['Organisation requirements', 'Learner groups and subjects', 'Examination schedule'], action: 'Contact us', featured: true },
  { name: 'Institution', description: 'For institutions with broader assessment and coordination requirements.', items: ['Institution requirements', 'Learner groups and subjects', 'Examination schedule'], action: 'Contact us' },
]

function ProductPreview() {
  return (
    <div className="product-preview" aria-label="Illustration of an assessment workspace">
      <div className="product-preview__browserbar" aria-hidden="true">
        <div className="product-preview__dots"><i /><i /><i /></div>
        <span>Assessment workspace</span>
        <span className="product-preview__browser-status"><i /> Workspace preview</span>
      </div>
      <div className="product-preview__workspace">
        <div className="product-preview__summary" aria-hidden="true">
          <div><span>Question bank</span><strong><Icon name="file" size={16} /></strong><small>Organise questions</small></div>
          <div><span>Examinations</span><strong><Icon name="clipboard" size={16} /></strong><small>Prepare assessments</small></div>
          <div><span>Candidate access</span><strong><Icon name="users" size={16} /></strong><small>Manage learners</small></div>
          <div><span>Results</span><strong><Icon name="chart" size={16} /></strong><small>Review outcomes</small></div>
        </div>
        <div className="product-preview__schedule">
          <div className="product-preview__schedule-heading"><strong>Assessment workflow</strong><span>Workspace overview</span></div>
          {[
            ['Question bank', 'Prepare and organise questions', 'In progress'],
            ['Examinations', 'Configure candidate assessments', 'Ready to review'],
            ['Results', 'Review and release outcomes', 'Available'],
          ].map(([title, description, state], index) => (
            <div className="product-preview__schedule-row" key={title}>
              <i className={`product-preview__status product-preview__status--${index}`} />
              <span><strong>{title}</strong><small>{description}</small></span>
              <em>{state}</em>
            </div>
          ))}
          <div className="product-preview__schedule-footer"><span><Icon name="file" size={14} /> Questions</span><span><Icon name="clipboard" size={14} /> Assessments</span><span><Icon name="chart" size={14} /> Results</span></div>
        </div>
      </div>
    </div>
  )
}

function ContentCard({ item, className = '' }) {
  return (
    <Card as="article" className={['landing-card', className].filter(Boolean).join(' ')}>
      <span className="landing-card__icon"><Icon name={item.icon} size={19} /></span>
      {item.tag && <span className="landing-card__tag">{item.tag}</span>}
      <h3>{item.title}</h3>
      <p>{item.description}</p>
    </Card>
  )
}

export default function LandingPage() {
  return (
    <div className="landing-page">
      <section className="landing-hero" aria-labelledby="landing-title">
        <div className="landing-hero__copy">
          <Badge variant="primary" className="landing-eyebrow"><Icon name="staff" size={13} /> Assessment &amp; Examination Platform</Badge>
          <h1 id="landing-title">Create. Assess.<br className="landing-title-break--mobile" />{' '}Mark.<br className="landing-title-break--desktop" /><br className="landing-title-break--mobile" />{' '}Analyse. Improve.</h1>
          <p className="landing-hero__description">
            A simple platform for creating questions, conducting examinations, marking submissions and managing results — whether you&apos;re running a school, course, training programme or professional examination.
          </p>
          <div className="landing-hero__actions">
            <Button as={Link} to="/setup" size="large">Setup Preview<Icon name="arrow" size={18} /></Button>
            <Button as={Link} to="/how-it-works" variant="outline" size="large"><Icon name="eye" size={17} />See How It Works</Button>
          </div>
          <p className="landing-hero__note"><Icon name="check" size={15} /> Built for education, training and certification organisations.</p>
        </div>
        <ProductPreview />
      </section>

      <section className="landing-section landing-audiences" aria-labelledby="audiences-title">
        <div className="landing-section__heading landing-section__heading--center">
          <p className="landing-kicker">Organisations we support</p>
          <h2 id="audiences-title">Designed for Anyone Running Structured Assessments</h2>
          <p>From classroom quizzes to certification examinations, the platform adapts to your assessment format.</p>
        </div>
        <div className="landing-grid landing-grid--audiences">
          {audiences.map(item => <ContentCard key={item.title} item={item} />)}
        </div>
      </section>

      <section className="landing-section landing-process" aria-labelledby="process-title">
        <div className="landing-section__heading landing-section__heading--center">
          <p className="landing-kicker">Simple assessment workflow</p>
          <h2 id="process-title">How It Works</h2>
          <p>A straightforward process from initial question authoring to final results.</p>
        </div>
        <ol className="landing-steps">
          {steps.map((step, index) => (
            <li className="landing-step" key={step.title}>
              <div className="landing-step__top"><span className="landing-step__number">{String(index + 1).padStart(2, '0')}</span><span className="landing-step__label">STEP {index + 1}</span></div>
              <h3>{step.title}</h3><p>{step.description}</p>
            </li>
          ))}
        </ol>
      </section>

      <section className="landing-section landing-features" aria-labelledby="features-title">
        <div className="landing-section__heading landing-section__heading--split">
          <div><p className="landing-kicker">Practical capabilities</p><h2 id="features-title">Everything Needed to Manage Assessments Dependably</h2></div>
          <p>Run structured assessments with a clear workflow focused on question creation, examination delivery and results.</p>
        </div>
        <div className="landing-grid landing-grid--features">
          {features.map(item => <ContentCard key={item.title} item={item} className="landing-card--feature" />)}
        </div>
      </section>

      <section className="landing-section landing-pricing" aria-labelledby="pricing-title">
        <div className="landing-section__heading landing-section__heading--center">
          <p className="landing-kicker">Institutional solutions</p>
          <h2 id="pricing-title">Simple Plans Sized for Your Institution</h2>
          <p>Explore an approach suited to your organisation and assessment needs.</p>
        </div>
        <div className="landing-plans">
          {plans.map(plan => (
            <Card as="article" className={`landing-plan${plan.featured ? ' landing-plan--featured' : ''}`} key={plan.name}>
              {plan.featured && <span className="landing-plan__recommended">Flexible requirements</span>}
              <span className="landing-plan__eyebrow">{plan.name.toUpperCase()}</span>
              <h3>{plan.name}</h3><p>{plan.description}</p>
              <ul>{plan.items.map(item => <li key={item}><Icon name="check" size={15} />{item}</li>)}</ul>
              <Button as={Link} to="/contact" variant={plan.featured ? 'primary' : 'secondary'}>{plan.action}</Button>
            </Card>
          ))}
        </div>
        <p className="landing-pricing__note">Contact us to discuss an arrangement for your organisation.</p>
      </section>

      <section className="landing-final-cta" aria-labelledby="final-cta-title">
        <div>
          <p className="landing-kicker landing-kicker--light">Clearer assessment workflow</p>
          <h2 id="final-cta-title">Ready to Run Simpler, More Dependable Assessments?</h2>
          <p>Join schools, colleges, training providers and exam organisations to manage each examination with assurance.</p>
        </div>
        <div className="landing-final-cta__actions">
          <Button as={Link} to="/how-it-works" variant="outline-light">See How It Works</Button>
          <Button as={Link} to="/setup" className="landing-final-cta__primary">Setup Preview<Icon name="arrow" size={17} /></Button>
        </div>
      </section>
    </div>
  )
}
