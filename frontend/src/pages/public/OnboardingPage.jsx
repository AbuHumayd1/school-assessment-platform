import { useRef, useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { PublicLocaleTree, translatePublicText, usePublicLocale } from '../../context/PublicLocaleContext.jsx'
import { apiFetch } from '../../services/api.js'
import { createWorkspace } from '../../services/onboarding.js'
import Button from '../../components/common/Button.jsx'
import LogoWordmark from '../../components/common/LogoWordmark.jsx'
import LoadingState from '../../components/common/LoadingState.jsx'
import './onboarding.css'

const types = [
  ['school', 'School / College'], ['training', 'Course / Training Provider'],
  ['professional_exam', 'Professional / Certification Exams'], ['madrasah', 'Madrasah / Islamic Institute'],
  ['cbt', 'CBT / Tutorial Centre'], ['competition', 'Competition / Educational Programme'], ['other', 'Other'],
]
const fieldErrors = {
  first_name: 'Enter your first name.', last_name: 'Enter your last name.',
  email: 'Enter a valid email address.', password: 'Choose a stronger password: at least 8 characters, not common, numeric-only or similar to your details.',
  password_confirmation: 'Passwords must match.', name: 'Enter a workspace name (up to 200 characters).',
  institution_type: 'Choose a workspace type.', phone: 'Enter a phone number with no more than 32 characters.',
  timezone: 'Choose a valid time zone.',
}

function defaultTimezone() {
  try { return Intl.DateTimeFormat().resolvedOptions().timeZone || 'Africa/Lagos' } catch { return 'Africa/Lagos' }
}

function SetupField({ name, label, errors, children, hint }) {
  return <PublicLocaleTree><div className="form-field">
    <label className="form-label" htmlFor={`setup-${name}`}>{label}</label>
    {children}
    {hint && <small className="form-hint" id={`setup-${name}-hint`}>{hint}</small>}
    {errors[name] && <small className="onboarding-field-error" id={`setup-${name}-error`}>{errors[name]}</small>}
  </div></PublicLocaleTree>
}

export default function OnboardingPage() {
  const { user, loading, error: authError, register, refreshUser } = useAuth()
  const workspace = useWorkspace()
  const navigate = useNavigate()
  const { locale } = usePublicLocale()
  const [busy, setBusy] = useState(false)
  const [errors, setErrors] = useState({})
  const [message, setMessage] = useState('')
  const [expired, setExpired] = useState(false)
  const [created, setCreated] = useState(null)
  const inFlight = useRef(false)
  const accountId = useRef(user?.id)
  accountId.current = user?.id
  const timezone = useRef(defaultTimezone()).current
  const zones = [...new Set([timezone, 'Africa/Lagos', 'Africa/Cairo', 'Europe/London', 'Asia/Riyadh', 'America/New_York', 'UTC'])]
  const createdId = created && user && created.userId === user.id ? created.id : null
  const inputProps = (name, extra = {}) => ({
    id: `setup-${name}`, name, className: 'form-control',
    'aria-invalid': errors[name] ? true : undefined,
    'aria-describedby': [errors[name] && `setup-${name}-error`, extra.hint && `setup-${name}-hint`].filter(Boolean).join(' ') || undefined,
    ...Object.fromEntries(Object.entries(extra).filter(([key]) => key !== 'hint')),
  })

  async function submit(event) {
    event.preventDefault()
    if (inFlight.current) return
    const form = event.currentTarget
    if (!form.reportValidity()) return
    const fields = Object.fromEntries(new FormData(form))
    if (!user && fields.password !== fields.password_confirmation) {
      setErrors({ password_confirmation: fieldErrors.password_confirmation })
      setMessage('Please check the highlighted fields.')
      form.elements.password_confirmation.focus()
      return
    }
    inFlight.current = true
    setBusy(true); setErrors({}); setMessage('')
    const userId = user?.id
    let confirmedId = createdId
    let invalidField = null
    try {
      if (!user) {
        await register(fields)
        form.reset()
      } else {
        if (!confirmedId) {
          confirmedId = await createWorkspace(apiFetch, fields)
          if (accountId.current !== userId) return
          setCreated({ userId, id: confirmedId })
        }
        await workspace.refreshAndSelect(confirmedId)
        if (accountId.current === userId) navigate('/app', { replace: true })
      }
    } catch (error) {
      if (userId && accountId.current !== userId) return
      if (userId && [401, 403].includes(error.status)) {
        // A CSRF failure with a live session must not be treated as a logout.
        try { await apiFetch('auth/me/') } catch (sessionError) {
          if (sessionError.status === 401) { setExpired(true); await refreshUser() }
        }
      }
      if (error.status === 400 && error.data && !confirmedId) {
        const next = {}
        for (const key of Object.keys(error.data)) if (fieldErrors[key]) next[key] = fieldErrors[key]
        if (!user && error.data.email?.some?.(value => String(value).includes('already exists'))) next.email = 'This email is already registered. Sign in with your existing account.'
        setErrors(next)
        setMessage('Please check the highlighted fields.')
        invalidField = Object.keys(next)[0]
      } else if (error.status === 429) setMessage('Too many requests. Please wait and try again.')
      else setMessage(confirmedId ? 'Your workspace was created, but access could not be refreshed. Try opening it again.' : 'We could not complete this request. Check your connection and try again.')
    } finally {
      inFlight.current = false
      setBusy(false)
      if (invalidField) requestAnimationFrame(() => form.elements[invalidField]?.focus())
    }
  }

  if (loading && !busy) return <PublicLocaleTree><LoadingState label={locale === 'ar' ? translatePublicText('Checking your account') : 'Checking your account'} /></PublicLocaleTree>
  if (authError) return <PublicLocaleTree><section className="account-access-panel">
    <h1>Account access could not be checked</h1>
    <p role="alert">We could not complete this request. Check your connection and try again.</p>
    <Button onClick={refreshUser}>Try again</Button>
    <Button as={Link} to="/" variant="outline">Back to website</Button>
  </section></PublicLocaleTree>
  return <PublicLocaleTree><div className="public-page public-setup onboarding">
    <aside className="setup-aside">
      <div className="setup-aside__top"><LogoWordmark light ariaLabel={locale === 'ar' ? translatePublicText('School Assessment Platform home') : 'School Assessment Platform home'} /><span>{user ? 'Step 2 of 2' : 'Step 1 of 2'}</span></div>
      <div className="setup-aside__main"><h1>Set up your workspace</h1><p>A place to organise your assessments and manage results.</p>
        <ol className="onboarding-steps"><li aria-current={!user ? 'step' : undefined}>Create your account</li><li aria-current={user ? 'step' : undefined}>Create your workspace</li></ol>
        <p>Start on your own or with an organisation. You can add candidates and assessments later.</p>
      </div>
      <div className="setup-aside__footer"><Link to="/">Back to website</Link></div>
    </aside>
    <section className="setup-content"><div className="setup-form-wrap">
      {expired ? <><h2>Sign in to continue</h2><p role="alert">Your session has expired. Sign in again to set up your workspace.</p><Button as={Link} to="/signin" state={{ from: { pathname: '/setup' } }}>Sign In</Button></> : <>
        <header className="setup-form-heading"><h2>{user ? 'Create your workspace' : 'Create your account'}</h2><p>{user ? 'You will be the administrator of this workspace.' : 'Create an account, then set up your workspace.'}</p>
          {user && <p className="onboarding-identity"><bdi>{user.email}</bdi> · <Link to="/signin">Account access</Link></p>}
        </header>
        <form className="public-form setup-form" onSubmit={submit} key={user?.id ?? 'registration'}>
          <fieldset disabled={busy || Boolean(createdId)} className="onboarding-fields">
            {!user ? <>
              <div className="onboarding-name-grid">
                <SetupField name="first_name" label="First name" errors={errors}><input {...inputProps('first_name', { autoComplete: 'given-name', maxLength: 150, required: true })} /></SetupField>
                <SetupField name="last_name" label="Last name" errors={errors}><input {...inputProps('last_name', { autoComplete: 'family-name', maxLength: 150, required: true })} /></SetupField>
              </div>
              <SetupField name="email" label="Email address" errors={errors}><input {...inputProps('email', { type: 'email', dir: 'ltr', autoComplete: 'email', maxLength: 254, required: true })} /></SetupField>
              <SetupField name="password" label="Password" errors={errors} hint="Use at least 8 characters. Avoid common passwords and personal details."><input {...inputProps('password', { type: 'password', autoComplete: 'new-password', maxLength: 128, required: true, hint: true })} /></SetupField>
              <SetupField name="password_confirmation" label="Confirm password" errors={errors}><input {...inputProps('password_confirmation', { type: 'password', autoComplete: 'new-password', maxLength: 128, required: true })} /></SetupField>
            </> : <>
              <SetupField name="name" label="Workspace name" errors={errors}><input {...inputProps('name', { maxLength: 200, required: true, autoComplete: 'organization' })} /></SetupField>
              <SetupField name="institution_type" label="Workspace type" errors={errors}><select {...inputProps('institution_type', { required: true, defaultValue: '' })}><option value="" disabled>Choose a workspace type</option>{types.map(([value, label]) => <option value={value} key={value}>{label}</option>)}</select></SetupField>
              <SetupField name="email" label="Contact email (optional)" errors={errors}><input {...inputProps('email', { type: 'email', dir: 'ltr', autoComplete: 'email', maxLength: 254 })} /></SetupField>
              <SetupField name="phone" label="Phone number (optional)" errors={errors}><input {...inputProps('phone', { type: 'tel', dir: 'ltr', autoComplete: 'tel', maxLength: 32 })} /></SetupField>
              <SetupField name="timezone" label="Time zone" errors={errors}><select {...inputProps('timezone', { defaultValue: timezone, dir: 'ltr' })}>{zones.map(zone => <option key={zone} value={zone}>{zone}</option>)}</select></SetupField>
            </>}
          </fieldset>
          {message && <p className="auth-error" role="alert" aria-live="polite">{message}</p>}
          <Button type="submit" className="setup-submit" loading={busy}>{busy ? (user ? 'Opening your workspace…' : 'Creating your account…') : user ? createdId ? 'Open workspace' : 'Create workspace' : 'Create account'}</Button>
        </form>
        {!user && <p className="setup-help">Already have an account? <Link to="/signin" state={{ from: { pathname: '/setup' } }}>Sign In</Link></p>}
        {user && <p className="setup-help"><Link to="/signin">Return to account access</Link></p>}
      </>}
      <p className="setup-help"><Link to="/">Back to website</Link></p>
    </div></section>
  </div></PublicLocaleTree>
}
