import ManagedExamCTA, { managedExamDestination } from './ManagedExamCTA.jsx'
import { useOptionalPublicLocale, PublicLocaleTree } from '../../context/PublicLocaleContext.jsx'
export { publicContactEmail } from './ManagedExamCTA.jsx'

export default function ManagedExamRequest({ number, email }) {
  const destination = managedExamDestination({ number, email })
  const locale = useOptionalPublicLocale()
  const content = <section id="request-examination" className="madaar-request" aria-labelledby="request-title" data-public-reveal="">
    <div><p className="madaar-kicker">Planning an examination?</p><h2 id="request-title">Let Madaar handle the technology.</h2><p>Request a Managed Examination. Prepare your organisation name, examination date, candidate numbers, question format and reporting requirements.</p></div>
    <div className="madaar-request__action"><ManagedExamCTA className="madaar-button" number={number} email={email} /><p>{destination.kind === 'whatsapp' ? 'Opens WhatsApp in a new tab with a message ready for you to send.' : destination.kind === 'email' ? 'This opens your email app. Your request is sent only when you send the email.' : 'Visit Contact for enquiry options. No request has been submitted here.'}</p></div>
  </section>
  return locale ? <PublicLocaleTree>{content}</PublicLocaleTree> : content
}
