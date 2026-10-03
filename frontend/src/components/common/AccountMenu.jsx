import { useEffect, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { useLanguageMode } from '../../context/LanguageModeContext.jsx'
import Button from './Button.jsx'
import Icon from './Icon.jsx'
import './account-access.css'

export function SignOutButton() {
  const { signOut } = useAuth()
  const { clearSelection } = useWorkspace()
  const { label: t } = useLanguageMode()
  const navigate = useNavigate()
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(false)
  async function handleSignOut() {
    setLoading(true)
    setError(false)
    try {
      await signOut()
      clearSelection()
      navigate('/signin', { replace: true, state: null })
    } catch {
      setError(true)
      setLoading(false)
    }
  }
  return <div className="account-signout">
    <Button variant="outline" size="small" onClick={handleSignOut} loading={loading}><Icon name="logout" size={16} />{t('Sign out', 'تسجيل الخروج')}</Button>
    {error && <p role="alert">{t('We could not sign you out. Check your connection and try again.', 'تعذر تسجيل الخروج. تحقق من اتصالك وحاول مرة أخرى.')}</p>}
  </div>
}

export default function AccountMenu() {
  const { user } = useAuth()
  const { label: t, direction } = useLanguageMode()
  const details = useRef(null)
  useEffect(() => {
    const closeOutside = event => { if (!details.current?.contains(event.target)) details.current?.removeAttribute('open') }
    const closeOnEscape = event => {
      if (event.key === 'Escape' && details.current?.open) {
        details.current.removeAttribute('open')
        details.current.querySelector('summary')?.focus()
      }
    }
    document.addEventListener('pointerdown', closeOutside)
    document.addEventListener('keydown', closeOnEscape)
    return () => { document.removeEventListener('pointerdown', closeOutside); document.removeEventListener('keydown', closeOnEscape) }
  }, [])
  return <details ref={details} className="account-menu" dir={direction}>
    <summary className="account-button" aria-label={t('Account and sign out', 'الحساب وتسجيل الخروج')}>
      <span className="account-avatar"><Icon name="user" size={18} /></span><span className="account-button__label">{t('Account', 'الحساب')}</span><Icon name="chevron" size={16} />
    </summary>
    <div className="account-menu__panel">
      <strong><bdi>{[user?.first_name, user?.last_name].filter(Boolean).join(' ') || t('Your account', 'حسابك')}</bdi></strong>
      <p><bdi>{user?.email}</bdi></p>
      <SignOutButton />
    </div>
  </details>
}
