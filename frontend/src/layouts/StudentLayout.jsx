import { useState } from 'react'
import { NavLink, Outlet, useLocation, useNavigate } from 'react-router-dom'
import Drawer from '../components/common/Drawer.jsx'
import Icon from '../components/common/Icon.jsx'
import LogoWordmark from '../components/common/LogoWordmark.jsx'
import Button from '../components/common/Button.jsx'
import { useAuth } from '../context/AuthContext.jsx'
import { useLanguageMode } from '../context/LanguageModeContext.jsx'
import LanguageModeControl from '../components/common/LanguageModeControl.jsx'

const navigation = [
  ['/student', 'Dashboard', 'home', true],
  ['/student/exams', 'My Exams', 'clipboard'],
  ['/student/results', 'My Results', 'chart'],
]

function StudentNavigation({ onNavigate, mobile = false }) {
  const { label } = useLanguageMode()
  const arabicLabels = { Dashboard: 'لوحة التحكم', 'My Exams': 'اختباراتي', 'My Results': 'نتائجي' }
  return (
    <nav className={mobile ? 'student-mobile-nav' : 'student-nav'} aria-label="Student navigation">
      {navigation.map(([to, english, icon, end]) => <NavLink key={to} to={to} end={end} title={english} onClick={onNavigate} className={({ isActive }) => `student-nav__link${isActive ? ' is-active' : ''}`}><Icon name={icon} /><span>{label(english, arabicLabels[english] || english)}</span></NavLink>)}
    </nav>
  )
}

function StudentAccount() {
  return <button className="account-button student-account" type="button" aria-label="Student account menu"><span className="account-avatar"><Icon name="user" size={18} /></span><span className="account-button__label">My account</span><Icon name="chevron" size={16} /></button>
}

function StudentLogout({ onDone, className = '' }) {
  const { signOut } = useAuth()
  const navigate = useNavigate()
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)

  async function handleSignOut() {
    setError('')
    setLoading(true)
    try {
      await signOut()
      onDone?.()
      navigate('/signin', { replace: true })
    } catch {
      setError('We couldn’t sign you out. Check your connection and try again.')
    } finally {
      setLoading(false)
    }
  }

  return <div className={className}>
    <Button variant="outline" size="small" loading={loading} onClick={handleSignOut}><Icon name="logout" size={16} />Sign out</Button>
    {error && <p className="auth-error" role="alert">{error}</p>}
  </div>
}

export default function StudentLayout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const { pathname } = useLocation()
  const { direction } = useLanguageMode()
  const examMode = pathname === '/student/exam' || pathname.startsWith('/student/exam/')
  const closeMenu = () => setMenuOpen(false)

  return (
    <div className={`student-layout${examMode ? ' student-layout--exam' : ''}`} dir={direction}>
      {!examMode && <Drawer open={menuOpen} onClose={closeMenu} title="Student menu" className="student-mobile-drawer">
        <StudentNavigation mobile onNavigate={closeMenu} />
        <LanguageModeControl />
        <div className="student-drawer-account"><StudentAccount /><StudentLogout className="student-drawer-logout" onDone={closeMenu} /></div>
      </Drawer>}

      <div className="student-workspace">
        {!examMode && <header className="student-topbar">
          <LogoWordmark to="/student" />
          <StudentNavigation />
          <div className="student-topbar__actions">
            <LanguageModeControl />
            <StudentAccount />
            <StudentLogout className="student-topbar__logout" />
            <button className="icon-button student-menu-toggle" type="button" aria-label="Open student menu" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}><Icon name="menu" /></button>
          </div>
        </header>}
        <main className={`student-content${examMode ? ' student-content--exam' : ''}`}><Outlet /></main>
      </div>
    </div>
  )
}
