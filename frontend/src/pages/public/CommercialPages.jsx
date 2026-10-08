import { Link, useSearchParams } from 'react-router-dom'
import ManagedExamCTA, { publicContactEmail, publicWhatsAppNumber } from '../../components/common/ManagedExamCTA.jsx'
import ManagedExamRequest from '../../components/common/ManagedExamRequest.jsx'
import { PublicLocaleTree } from '../../context/PublicLocaleContext.jsx'
import './madaar.css'

export const enquiryTypes = {
  'managed-exam': { label: 'Managed Examination', cta: 'Request an Examination', description: "Tell us about your examination and we'll discuss your requirements, candidate volume and next steps." },
  'institution-pilot': { label: 'Institution Workspace Pilot', cta: 'Discuss Institution Workspace', description: 'Interested in bringing Madaar to your institution? Tell us about your organisation and assessment needs.' },
  partnership: { label: 'Partnership', cta: 'Discuss a Partnership', description: "Tell us how you'd like to work with Madaar." },
  general: { label: 'General Enquiry', cta: 'Message Madaar', description: "Have a question about Madaar? Send us a message and we'll be happy to help." },
}
export function enquiryIntent(value) { return Object.hasOwn(enquiryTypes, value) ? value : 'general' }

export function PricingPage() {
  return <PublicLocaleTree><div className="madaar-commercial">
    <header className="madaar-section-heading"><p className="madaar-kicker">Pricing</p><h1>Assessment services for your organisation</h1><p>Choose the right way to run your assessments.</p></header>
    <div className="madaar-pricing-grid">
      <section className="madaar-price-card" data-public-reveal=""><span className="madaar-status">Available Now</span><h2>Managed Examinations</h2><p className="madaar-price-label">Custom pricing</p><p>Pricing reflects your candidate volume, examination requirements, duration and configuration, and preparation or service needs.</p><ul>{['Candidate volume', 'Examination requirements', 'Duration and configuration', 'Preparation and service requirements'].map(item => <li key={item}>{item}</li>)}</ul><ManagedExamCTA className="madaar-button" /></section>
      <section className="madaar-price-card" data-public-reveal=""><span className="madaar-status madaar-status--pilot">Currently in Pilot</span><h2>Institution Workspace</h2><p className="madaar-kicker">Planned plans</p><div className="madaar-planned-plans">{['Starter', 'Growth', 'Professional', 'Enterprise'].map(plan => <span key={plan}>{plan}</span>)}</div><p>Final plan pricing and limits will be announced before general availability.</p><Link className="madaar-button madaar-button--outline" to="/contact?interest=institution-pilot">Request Pilot Access</Link></section>
    </div><ManagedExamRequest />
  </div></PublicLocaleTree>
}

export function ContactPage() {
  const [search, setSearch] = useSearchParams()
  const intent = enquiryIntent(search.get('interest'))
  const enquiry = enquiryTypes[intent]
  const email = publicContactEmail()
  const number = publicWhatsAppNumber()
  const message = `Hello, I'd like to enquire about ${enquiry.label} with Madaar.`
  function selectIntent(value) {
    const next = new URLSearchParams(search); next.set('interest', value); setSearch(next, { replace: true })
  }
  return <PublicLocaleTree><div className="madaar-commercial">
    <header className="madaar-section-heading"><p className="madaar-kicker">Contact Madaar</p><h1>Tell us what you need.</h1></header>
    <section className="madaar-request" data-public-reveal=""><div><label className="form-field"><span className="form-label">Choose your enquiry</span><select className="form-control" aria-label="Choose your enquiry" value={intent} onChange={event => selectIntent(event.target.value)}>{Object.entries(enquiryTypes).map(([value, item]) => <option key={value} value={value}>{item.label}</option>)}</select></label><h2>{enquiry.label}</h2><p>{enquiry.description}</p></div>
      <div className="madaar-contact-actions">
        {intent === 'managed-exam' && (number || email) && <ManagedExamCTA className="madaar-button">{enquiry.cta}</ManagedExamCTA>}
        {email && <a className={intent !== 'managed-exam' && !number ? 'madaar-button' : 'madaar-button madaar-button--outline'} href={`mailto:${email}?subject=${encodeURIComponent(enquiry.label + ' enquiry')}&body=${encodeURIComponent(message)}`}>{intent !== 'managed-exam' && !number ? enquiry.cta : 'Email Madaar'}</a>}
        {number && intent !== 'managed-exam' && <a className="madaar-button" href={`https://wa.me/${number}?text=${encodeURIComponent(message)}`} target="_blank" rel="noopener noreferrer">{enquiry.cta}</a>}
        {!(email || number) && <p role="status">Public contact details are not configured yet. If you already have a Madaar coordinator, use your existing contact channel. No enquiry has been submitted here.</p>}
      </div>
    </section>
  </div></PublicLocaleTree>
}
