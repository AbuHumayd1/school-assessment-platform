import { Link } from 'react-router-dom'
import { useOptionalPublicLocale, translatePublicText } from '../../context/PublicLocaleContext.jsx'

export const managedExamMessage = "Hello, I'm interested in running a Managed Examination with Madaar. I'd like to discuss the requirements and pricing."

export function publicWhatsAppNumber(value = import.meta.env.VITE_PUBLIC_WHATSAPP_NUMBER) {
  // International digits only. Reject placeholders, '+' prefixes and spaces.
  return typeof value === 'string' && /^[1-9][0-9]{6,14}$/.test(value) ? value : null
}

export function publicContactEmail(value = import.meta.env.VITE_PUBLIC_CONTACT_EMAIL) {
  const email = String(value || '').trim()
  return /^[a-z0-9.!#$%&'*+/=?^_{}|~-]+@[a-z0-9-]+(?:\.[a-z0-9-]+)+$/i.test(email) ? email : null
}

export function managedExamDestination({ number = publicWhatsAppNumber(), email = publicContactEmail() } = {}) {
  const validNumber = publicWhatsAppNumber(number)
  if (validNumber) return { kind: 'whatsapp', href: `https://wa.me/${validNumber}?text=${encodeURIComponent(managedExamMessage)}` }
  const validEmail = publicContactEmail(email)
  if (validEmail) return { kind: 'email', href: `mailto:${validEmail}?subject=Request%20a%20Managed%20Examination&body=${encodeURIComponent(managedExamMessage)}` }
  return { kind: 'contact', href: '/contact' }
}

export default function ManagedExamCTA({ children = 'Request a Managed Examination', number, email, ...props }) {
  const locale = useOptionalPublicLocale()?.locale
  const label = locale === 'ar' && typeof children === 'string' ? translatePublicText(children) : children
  const destination = managedExamDestination({ number, email })
  if (destination.kind === 'contact') return <Link {...props} to="/contact">{label}</Link>
  return <a {...props} href={destination.href} target={destination.kind === 'whatsapp' ? '_blank' : undefined} rel={destination.kind === 'whatsapp' ? 'noopener noreferrer' : undefined}>{label}</a>
}
