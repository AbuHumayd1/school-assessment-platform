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
  { title: 'Question Bank', description: 'Create and organise reusable examination questions.', icon: 'file' },
  { title: 'Create Exams', description: 'Build examinations from your approved question bank.', icon: 'clipboard' },
  { title: 'Online Examinations', description: 'Let students and learners take examinations online.', icon: 'inbox' },
  { title: 'Automatic Marking', description: 'Automatically mark supported objective question types.', icon: 'chart' },
  { title: 'Results', description: 'Manage, release and view examination results.', icon: 'layers' },
  { title: 'Students & Classes', description: 'Organise learners into classes or cohorts.', icon: 'users' },
  { title: 'Examination Security', description: 'Protect examination access, attempts and submitted answers.', icon: 'staff' },
  { title: 'Performance Reports', description: 'Understand examination performance through result-based reports.', icon: 'chart' },
]

const steps = [
  'Set Up Your Institution',
  'Create Questions',
  'Create Examination',
  'Students Take Exam',
  'Mark Submissions',
  'Review & Publish Results',
  'Understand Performance',
]

function ProductPreview() {
  return (
    <div className="product-preview" aria-label="Illustration of the assessment workspace">
      <div className="product-preview__topbar">
        <span className="product-preview__mark" aria-hidden="true">SA</span>
        <span>Assessment workspace</span>
        <span className="product-preview__account"><Icon name="user" size={17} /></span>
      </div>
      <div className="product-preview__content">
        <div className="product-preview__intro">
          <span>YOUR ASSESSMENT JOURNEY</span>
          <strong>From questions to results</strong>
        </div>
        <div className="product-preview__flow" aria-hidden="true">
          <span><Icon name="file" size={18} /></span><i />
          <span><Icon name="clipboard" size={18} /></span><i />
          <span><Icon name="chart" size={18} /></span>
        </div>
        <div className="product-preview__flow-labels" aria-hidden="true">
          <span>Create</span><span>Examine</span><span>Review</span>
        </div>
        <div className="product-preview__cards">
          <div><Icon name="file" /><span>Question bank</span><small>Build and organise questions</small></div>
          <div><Icon name="clipboard" /><span>Examinations</span><small>Prepare and conduct exams</small></div>
          <div><Icon name="chart" /><span>Marking & results</span><small>Review and release results</small></div>
        </div>
      </div>
    </div>
  )
}

function ContentCard({ item, className = '' }) {
  return (
    <Card as="article" className={['landing-card', className].filter(Boolean).join(' ')}>
      <span className="landing-card__icon"><Icon name={item.icon} size={21} /></span>
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
          <Badge variant="primary" className="landing-eyebrow">Examinations for every organisation</Badge>
          <h1 id="landing-title"><span>Create. Assess.</span><span>Mark. Analyse.</span><span>Improve.</span></h1>
          <p className="landing-hero__description">
            A simple platform for creating questions, conducting examinations, marking submissions and managing results — whether you&apos;re running a school, course, training programme or professional examination.
          </p>
          <div className="landing-hero__actions">
            <Button as={Link} to="/setup" size="large">Setup Preview<Icon name="arrow" size={18} /></Button>
            <Button as={Link} to="/signin" variant="outline" size="large">Sign In</Button>
          </div>
          <p className="landing-hero__note">For schools, training providers and examination organisations.</p>
        </div>
        <div className="landing-hero__visual"><ProductPreview /></div>
      </section>

      <section className="landing-section landing-audiences" aria-labelledby="audiences-title">
        <div className="landing-section__heading">
          <p className="landing-kicker">One platform, many possibilities</p>
          <h2 id="audiences-title">Built for different kinds of examinations</h2>
          <p>Support the way your organisation teaches, trains and assesses.</p>
        </div>
        <div className="landing-grid landing-grid--audiences">
          {audiences.map(item => <ContentCard key={item.title} item={item} />)}
        </div>
      </section>

      <section className="landing-section landing-features" aria-labelledby="features-title">
        <div className="landing-section__heading">
          <p className="landing-kicker">A clearer way to assess</p>
          <h2 id="features-title">Everything you need to manage assessments</h2>
          <p>Bring question creation, examinations and results together in one place.</p>
        </div>
        <div className="landing-grid landing-grid--features">
          {features.map(item => <ContentCard key={item.title} item={item} className="landing-card--feature" />)}
        </div>
      </section>

      <section className="landing-section landing-process" aria-labelledby="process-title">
        <div className="landing-section__heading">
          <p className="landing-kicker">A simple process</p>
          <h2 id="process-title">How it works</h2>
          <p>Move from preparing questions to understanding results in clear steps.</p>
        </div>
        <ol className="landing-steps">
          {steps.map((step, index) => (
            <li className="landing-step" key={step}>
              <span className="landing-step__number">{String(index + 1).padStart(2, '0')}</span>
              <span>{step}</span>
            </li>
          ))}
        </ol>
        <Link className="landing-text-link" to="/how-it-works">See how it works <Icon name="arrow" size={18} /></Link>
      </section>

      <section className="landing-message" aria-labelledby="message-title">
        <div className="landing-message__copy">
          <p className="landing-kicker landing-kicker--light">The complete examination journey</p>
          <h2 id="message-title">Create. Assess. Mark. Analyse. Improve.</h2>
          <p>Take your organisation from building a question bank through conducting examinations and managing results.</p>
        </div>
        <div className="landing-message__path" aria-hidden="true">
          <span><Icon name="file" />Create</span><i />
          <span><Icon name="clipboard" />Assess</span><i />
          <span><Icon name="chart" />Improve</span>
        </div>
      </section>

      <section className="landing-final-cta" aria-labelledby="final-cta-title">
        <div>
          <p className="landing-kicker">Start with a simpler process</p>
          <h2 id="final-cta-title">Ready to simplify your examinations?</h2>
          <p>Create assessments, conduct examinations and manage results from one place.</p>
        </div>
        <div className="landing-final-cta__actions">
          <Button as={Link} to="/setup" size="large">Setup Preview<Icon name="arrow" size={18} /></Button>
          <Button as={Link} to="/signin" variant="outline" size="large">Sign In</Button>
        </div>
      </section>
    </div>
  )
}
