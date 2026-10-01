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

function PageIntro({ eyebrow, title, children, centered = false }) {
  return <header className={`public-page-intro${centered ? ' public-page-intro--centered' : ''}`}>
    <Badge variant="primary">{eyebrow}</Badge><h1>{title}</h1>{children && <p>{children}</p>}
  </header>
}

function CTASection({ title = 'Ready to simplify your examinations?', copy = 'See how the platform can support your organisation.', children }) {
  return <section className="public-cta"><div><p className="public-kicker public-kicker--light">School Assessment Platform</p><h2>{title}</h2><p>{copy}</p></div><div className="public-cta__actions">{children || <Button as={Link} to="/contact" variant="outline">Contact us</Button>}</div></section>
}

export function FeaturesPage() {
  return <div className="public-page public-features">
    <PageIntro eyebrow="Capabilities" title="Everything you need to run better assessments">Create questions, conduct examinations, mark submissions and manage results in one clear workflow.</PageIntro>
    <div className="public-feature-grid">{capabilities.map(([title, copy, icon]) => <Card as="article" className="public-feature-card" key={title}><span className="public-icon"><Icon name={icon} size={23} /></span><h2>{title}</h2><p>{copy}</p></Card>)}</div>
    <CTASection title="A clearer way to assess" copy="Explore a workflow built for schools, training programmes and examination organisations."><Button as={Link} to="/how-it-works" variant="outline">How it works<Icon name="arrow" size={17} /></Button><Button as={Link} to="/contact">Contact us<Icon name="arrow" size={17} /></Button></CTASection>
  </div>
}

export function HowItWorksPage() {
  return <div className="public-page public-how">
    <PageIntro eyebrow="A simple assessment workflow" title="From setup to results">A straightforward process to prepare assessments and understand outcomes.</PageIntro>
    <ol className="workflow-list">{workflow.map(([title, copy, icon], index) => <li className="workflow-step" key={title}><span className="workflow-step__number">{String(index + 1).padStart(2, '0')}</span><Card as="article" className="workflow-step__card"><span className="public-icon"><Icon name={icon} size={22} /></span><div><h2>{title}</h2><p>{copy}</p></div></Card></li>)}</ol>
    <CTASection title="Move through each stage with clarity" copy="Explore the capabilities that support your assessment process."><Button as={Link} to="/features">Explore features<Icon name="arrow" size={17} /></Button></CTASection>
  </div>
}

export function PricingPage() {
  const tiers = [
    ['Starter', 'For a single school, centre or programme getting started with structured assessments.'],
    ['Professional', 'For organisations managing regular examinations across courses or cohorts.'],
    ['Institution', 'For institutions with broader assessment and coordination requirements.'],
  ]
  return <div className="public-page public-pricing">
    <PageIntro eyebrow="Institutional requirements" title="Plans shaped around your assessments">The right setup depends on your organisation, learners and examination schedule.</PageIntro>
    <div className="pricing-grid">{tiers.map(([name, copy], index) => <Card as="article" className={`pricing-card${index === 1 ? ' pricing-card--featured' : ''}`} key={name}>{index === 1 && <Badge variant="primary">Flexible requirements</Badge>}<p className="pricing-card__eyebrow">{index === 0 ? 'STARTER' : index === 1 ? 'PROFESSIONAL' : 'INSTITUTION'}</p><h2>{name}</h2><p>{copy}</p><div className="pricing-card__rule" /><p className="pricing-card__note">Contact us to discuss your institution&apos;s requirements.</p><Button as={Link} to="/contact" variant={index === 1 ? 'primary' : 'outline'}>Contact us<Icon name="arrow" size={17} /></Button></Card>)}</div>
    <section className="pricing-note"><span className="public-icon"><Icon name="users" /></span><div><h2>Let&apos;s discuss what you need</h2><p>We can learn about your assessment programme and discuss a suitable approach. No online checkout or payment is available here.</p></div><Button as={Link} to="/contact" variant="ghost">Get in touch<Icon name="arrow" size={17} /></Button></section>
  </div>
}

export function AboutPage() {
  return <div className="public-page public-about">
    <PageIntro eyebrow="About the platform" title="Assessment management with clarity">School Assessment Platform is built to simplify how organisations prepare and manage examinations.</PageIntro>
    <section className="about-feature"><div className="about-feature__visual" aria-hidden="true"><span className="about-feature__symbol"><Icon name="clipboard" size={44} /></span><div><i /><i /><i /></div><div><i /><i /></div><div><i /><i /><i /></div></div><div className="about-feature__copy"><p className="public-kicker">Create. Assess. Mark. Analyse. Improve.</p><h2>One clear journey from questions to results</h2><p>Bring question management, examination administration, marking, results and performance understanding into a single assessment workflow.</p><p>The platform is intended for schools, educational institutes, training programmes, professional examination programmes, madrasahs and CBT centres.</p><Button as={Link} to="/features" variant="outline">Explore platform features<Icon name="arrow" size={17} /></Button></div></section>
    <div className="about-pillars">{[['Organise questions', 'Prepare reusable questions for your assessments.'], ['Conduct examinations', 'Schedule and deliver examinations to learners.'], ['Manage outcomes', 'Review results and understand performance.']].map(([title, copy]) => <Card as="article" className="about-pillar" key={title}><span className="public-icon"><Icon name={title === 'Organise questions' ? 'file' : title === 'Conduct examinations' ? 'clipboard' : 'chart'} /></span><h2>{title}</h2><p>{copy}</p></Card>)}</div>
    <CTASection title="Built around the work of assessment" copy="See the platform workflow and its available capabilities."><Button as={Link} to="/how-it-works" variant="outline">How it works<Icon name="arrow" size={17} /></Button></CTASection>
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
  function handleSubmit(event) { event.preventDefault(); setNotice(true) }
  return <div className="public-page public-auth-page"><section className="auth-panel"><div className="auth-panel__brand"><span className="wordmark__mark" aria-hidden="true">SA</span><span>School Assessment<br />Platform</span></div><div className="auth-panel__message"><p className="public-kicker public-kicker--light">Assessment workspace</p><h1>Welcome back</h1><p className="auth-panel__slogan">Create. Assess. Mark. Analyse. Improve.</p><p>Sign in to manage examinations, assessments and results.</p><div className="auth-panel__flow"><span>Create</span><i /><span>Assess</span><i /><span>Mark</span><i /><span>Results</span></div></div><p className="auth-panel__foot">For schools, training providers and examination organisations.</p></section>
    <section className="auth-form-panel"><div className="auth-form-wrap"><PageIntro eyebrow="Institutional access" title="Sign in to your account">Enter your details to continue.</PageIntro><form className="public-form" onSubmit={handleSubmit}><label className="form-field"><span className="form-label">Email address</span><input className="form-control" type="email" name="email" autoComplete="username" required /></label><label className="form-field"><span className="form-label">Password</span><input className="form-control" type="password" name="password" autoComplete="current-password" required /></label><button type="button" className="text-action" disabled aria-disabled="true">Forgot password?</button><Button type="submit" className="auth-submit">Sign In<Icon name="arrow" size={17} /></Button>{notice && <p className="form-hint" role="status">Sign-in is not connected yet. No login was attempted.</p>}</form><p className="auth-form__foot">Institution access is managed by your organisation.</p></div></section></div>
}

export function SetupPage() {
  return <div className="public-page public-setup"><aside className="setup-aside"><div className="auth-panel__brand"><span className="wordmark__mark" aria-hidden="true">SA</span><span>School Assessment<br />Platform</span></div><p className="public-kicker public-kicker--light">Institution onboarding</p><h1>Set up your institution</h1><p>Get your organisation ready to create assessments, conduct examinations and manage results.</p><div className="setup-flow"><span>Create</span><i /><span>Assess</span><i /><span>Mark</span><i /><span>Results</span></div><div className="setup-aside__note"><Icon name="staff" /><span>Institution setup is not available online yet.</span></div></aside>
    <section className="setup-content"><PageIntro eyebrow="Institution profile" title="Set Up Your Institution">Prepare your organisation profile for the assessment journey.</PageIntro><div className="setup-step"><span>01</span><div><strong>Institution details</strong><small>Organisation profile</small></div><span className="setup-step__total">STEP 1 OF 2</span></div><form className="public-form setup-form" onSubmit={event => event.preventDefault()}><label className="form-field"><span className="form-label">Institution Name</span><input className="form-control" name="institution" placeholder="Enter institution name" disabled /></label><label className="form-field"><span className="form-label">Institution Type</span><select className="form-control form-select" name="type" defaultValue="" disabled><option value="" disabled>Select institution type</option><option>School or College</option><option>Madrasah or Islamic Institute</option><option>Training Programme</option><option>Professional Examination Programme</option><option>CBT or Tutorial Centre</option><option>Competition or Educational Programme</option></select></label><div className="public-form__row"><label className="form-field"><span className="form-label">Email</span><input className="form-control" type="email" placeholder="name@organisation.org" disabled /></label><label className="form-field"><span className="form-label">Phone</span><input className="form-control" type="tel" placeholder="Phone number" disabled /></label></div><label className="form-field"><span className="form-label">Address</span><textarea className="form-control form-textarea" rows="3" placeholder="Institution address" disabled /></label><Button type="button" disabled className="setup-submit">Registration is not available yet<Icon name="arrow" size={17} /></Button><p className="form-hint">This screen is a design preview. It does not create an institution or account.</p></form></section>
  </div>
}
