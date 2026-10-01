import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import Drawer from '../components/common/Drawer.jsx'
import Icon from '../components/common/Icon.jsx'
import LogoWordmark from '../components/common/LogoWordmark.jsx'

const navigation = [
  ['/student', 'Dashboard', 'home', true],
  ['/student/exams', 'My Exams', 'clipboard'],
  ['/student/results', 'My Results', 'chart'],
]

function StudentNavigation({ onNavigate, mobile = false }) {
  return (
    <nav className={mobile ? 'student-mobile-nav' : 'student-nav'} aria-label="Student navigation">
      {navigation.map(([to, label, icon, end]) => <NavLink key={to} to={to} end={end} title={label} onClick={onNavigate} className={({ isActive }) => `student-nav__link${isActive ? ' is-active' : ''}`}><Icon name={icon} /><span>{label}</span></NavLink>)}
    </nav>
  )
}

function StudentAccount() {
  return <button className="account-button student-account" type="button" aria-label="Student account menu"><span className="account-avatar"><Icon name="user" size={18} /></span><span className="account-button__label">My account</span><Icon name="chevron" size={16} /></button>
}

export default function StudentLayout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const closeMenu = () => setMenuOpen(false)

  return (
    <div className="student-layout">
      <aside className="student-sidebar">
        <LogoWordmark light to="/student" />
        <StudentNavigation />
        <div className="student-sidebar__footer"><Icon name="cap" size={18} /><span>Student space</span></div>
      </aside>

      <Drawer open={menuOpen} onClose={closeMenu} title="Student menu" className="student-mobile-drawer">
        <StudentNavigation mobile onNavigate={closeMenu} />
        <div className="student-drawer-account"><StudentAccount /></div>
      </Drawer>

      <div className="student-workspace">
        <header className="student-mobile-header">
          <button className="icon-button mobile-menu-button" type="button" aria-label="Open student menu" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}><Icon name="menu" /></button>
          <LogoWordmark light compact to="/student" />
          <StudentAccount />
        </header>
        <header className="student-topbar">
          <div className="student-topbar__welcome"><span className="student-topbar__icon"><Icon name="cap" /></span><span>Student portal</span></div>
          <StudentAccount />
        </header>
        <main className="student-content"><Outlet /></main>
      </div>
    </div>
  )
}
