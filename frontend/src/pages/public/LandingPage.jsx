import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import Badge from '../../components/common/Badge.jsx'
import Button from '../../components/common/Button.jsx'
import Card from '../../components/common/Card.jsx'
import Icon from '../../components/common/Icon.jsx'
import { PublicLocaleTree, usePublicLocale } from '../../context/PublicLocaleContext.jsx'
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

const audienceMessages = [
  { english: <>Create. Assess. Mark.<br />Analyse. Improve.</>, arabic: <>أنشئ. قيّم. صحّح.<br />حلّل. طوّر.</>, accent: '#6B74D6' },
  { english: <>Built for Schools<br />That Take Assessment Seriously.</>, arabic: <>للمدارس التي تأخذ<br />التقييم بجدية.</>, accent: '#587BD8' },
  { english: <>Built for Online Madrasahs<br />and Islamic Institutes</>, arabic: <>صُمِّم للمدارس والمعاهد<br />الإسلامية عبر الإنترنت</>, accent: '#559B91', madrasah: true },
  { english: <>Built for Courses &amp; Training<br />That Develop Skills.</>, arabic: <>للدورات والبرامج التدريبية<br />التي تصقل المهارات.</>, accent: '#8A75D8' },
  { english: <>Built for Professional<br />Examinations.</>, arabic: <>للامتحانات المهنية<br />والشهادات التخصصية.</>, accent: '#4546B4' },
  { english: <>Built for CBT<br />and Tutorial Centres.</>, arabic: <>لمراكز الاختبارات المحوسبة<br />والدروس التعليمية.</>, accent: '#647BD2' },
  { english: <>Built for Competitions<br />and Educational Programmes.</>, arabic: <>للمسابقات والبرامج<br />التعليمية المنظمة.</>, accent: '#756BD5' },
]

function HeroHeadline({ active }) {
  const { locale } = usePublicLocale()
  const slide = audienceMessages[active]
  return <h1 id="landing-title" className={`landing-hero__headline${slide.madrasah ? ' landing-hero__headline--madrasah' : ''}`}>
    <span key={`${locale}-${active}`} className="landing-hero__headline-content" lang={locale} dir={locale === 'ar' ? 'rtl' : 'ltr'}>
      {locale === 'ar' ? slide.arabic : slide.english}
      {slide.madrasah && locale === 'en' && <span className="landing-hero__headline-arabic" lang="ar" dir="rtl">صُمِّم للمدارس والمعاهد الإسلامية</span>}
    </span>
  </h1>
}

function ProductPreview() {
  return (
    <PublicLocaleTree><div className="product-preview" aria-label="Illustration of an assessment workspace">
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
    </div></PublicLocaleTree>
  )
}

function ContentCard({ item, className = '', gradientTone = '' }) {
  return (
    <PublicLocaleTree><Card as="article" className={['landing-card', gradientTone && `gradient-card gradient-card--${gradientTone}`, className].filter(Boolean).join(' ')}>
      <span className="landing-card__icon"><Icon name={item.icon} size={19} /></span>
      {item.tag && <span className="landing-card__tag">{item.tag}</span>}
      <h3>{item.title}</h3>
      <p>{item.description}</p>
    </Card></PublicLocaleTree>
  )
}

export default function LandingPage() {
  const [active, setActive] = useState(0)
  useEffect(() => {
    const reducedMotion = window.matchMedia?.('(prefers-reduced-motion: reduce)').matches
    if (reducedMotion) return undefined
    const timer = window.setInterval(() => setActive(index => (index + 1) % audienceMessages.length), 4500)
    return () => window.clearInterval(timer)
  }, [])
  return (
    <PublicLocaleTree><div className="landing-page">
      <section className="landing-hero" aria-labelledby="landing-title" style={{ '--hero-accent': audienceMessages[active].accent }}>
        <div className="landing-hero__copy">
          <Badge variant="primary" className="landing-eyebrow"><Icon name="staff" size={13} /> Assessment &amp; Examination Platform</Badge>
          <HeroHeadline active={active} />
          <p className="landing-hero__description">
            Create questions, conduct examinations, mark submissions and manage results in one place. Built for schools, courses, training programmes and professional examinations.
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
          {audiences.map((item, index) => <ContentCard key={item.title} item={item} gradientTone={['soft-indigo', 'soft-blue', 'soft-violet'][index % 3]} />)}
        </div>
      </section>

      <section className="landing-section landing-process" aria-labelledby="process-title">
        <div className="landing-section__heading landing-section__heading--center">
          <p className="landing-kicker">A clear assessment workflow</p>
          <h2 id="process-title">How It Works</h2>
          <p>A straightforward process from initial question authoring to final results.</p>
        </div>
        <ol className="landing-steps">
          {steps.map((step, index) => (
            <li className={`landing-step${index < 4 ? ` gradient-card gradient-card--${['soft-indigo', 'soft-blue', 'soft-violet'][index % 3]}` : ''}`} key={step.title}>
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
          {features.map((item, index) => <ContentCard key={item.title} item={item} className="landing-card--feature" gradientTone={index < 6 ? ['soft-indigo', 'soft-blue', 'soft-violet'][index % 3] : ''} />)}
        </div>
      </section>

      <section className="landing-vision gradient-card gradient-card--soft-indigo" aria-labelledby="landing-vision-title">
        <div className="landing-vision__copy">
          <p className="landing-kicker">Assessment is the starting point</p>
          <h2 id="landing-vision-title">Built for assessment today. Built to grow with education tomorrow.</h2>
          <p>Institutions can create, conduct, manage and evaluate structured examinations today. Our longer-term direction connects assessment with teaching, learning, academic management and the work of running an institution.</p>
          <strong>Assessment is where we’re starting. Better education is where we’re going.</strong>
        </div>
        <ol className="education-system" aria-label="Education platform direction">
          {[
            ['Assessment', 'Available now', 'current'],
            ['Teaching', 'Future direction', 'future'],
            ['Learning', 'Future direction', 'future'],
            ['Academic management', 'Future direction', 'future'],
            ['Insight & improvement', 'Future direction', 'future'],
          ].map(([label, status, state], index) => <li className={`education-system__node education-system__node--${state}`} key={label}>
            <span className="education-system__index">0{index + 1}</span><strong>{label}</strong><small>{status}</small>
          </li>)}
        </ol>
      </section>

      <section className="landing-section landing-pricing" aria-labelledby="pricing-title">
        <div className="landing-section__heading landing-section__heading--center">
          <p className="landing-kicker">Institutional solutions</p>
          <h2 id="pricing-title">Plans Aligned with Your Institution</h2>
          <p>Explore an approach suited to your organisation and assessment needs.</p>
        </div>
        <div className="landing-plans">
          {plans.map(plan => (
            <Card as="article" className={`landing-plan gradient-card gradient-card--${plan.featured ? 'accent' : plan.name === 'Starter' ? 'soft-indigo' : 'soft-blue'}${plan.featured ? ' landing-plan--featured' : ''}`} key={plan.name}>
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

      <section className="landing-final-cta gradient-card gradient-card--deep" aria-labelledby="final-cta-title">
        <div>
          <p className="landing-kicker landing-kicker--light">Clearer assessment workflow</p>
          <h2 id="final-cta-title">Ready to Manage Assessments with Confidence?</h2>
          <p>Join schools, colleges, training providers and exam organisations to manage each examination with assurance.</p>
        </div>
        <div className="landing-final-cta__actions">
          <Button as={Link} to="/how-it-works" variant="outline-light">See How It Works</Button>
          <Button as={Link} to="/setup" className="landing-final-cta__primary">Setup Preview<Icon name="arrow" size={17} /></Button>
        </div>
      </section>
    </div></PublicLocaleTree>
  )
}
