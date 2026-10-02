import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import Drawer from '../components/common/Drawer.jsx'
import Icon from '../components/common/Icon.jsx'
import LogoWordmark from '../components/common/LogoWordmark.jsx'
import LanguageModeControl from '../components/common/LanguageModeControl.jsx'
import { useLanguageMode } from '../context/LanguageModeContext.jsx'

const navigation = [
  ['/app', 'Dashboard', 'home', true],
  ['/app/students', 'Students', 'users'],
  ['/app/staff', 'Teachers & Staff', 'staff'],
  ['/app/classes', 'Classes / Cohorts', 'layers'],
  ['/app/subjects', 'Subjects', 'book'],
  ['/app/questions', 'Questions', 'file'],
  ['/app/exams', 'Exams', 'clipboard'],
  ['/app/submissions', 'Submissions', 'inbox'],
  ['/app/results', 'Results', 'chart'],
  ['/app/reports', 'Reports', 'chart'],
  ['/app/settings', 'Settings', 'settings'],
]

function StaffNavigation({ onNavigate }) {
  const { label: localizedLabel } = useLanguageMode()
  const arabicLabels = { Students: 'الطلاب', Subjects: 'المواد', Exams: 'الاختبارات', Results: 'النتائج' }
  return (
    <nav className="app-navigation" aria-label="Institution navigation">
      {navigation.map(([to, label, icon, end]) => (
        <NavLink key={to} to={to} end={end} title={label} onClick={onNavigate} className={({ isActive }) => `app-navigation__link${isActive ? ' is-active' : ''}`}>
          <Icon name={icon} />
          <span>{localizedLabel(label, arabicLabels[label] || label)}</span>
        </NavLink>
      ))}
    </nav>
  )
}

function AccountButton() {
  return <button className="account-button" type="button" aria-label="Account menu"><span className="account-avatar"><Icon name="user" size={18} /></span><span className="account-button__label">Account</span><Icon name="chevron" size={16} /></button>
}

export default function StaffLayout() {
  const { direction } = useLanguageMode()
  const [menuOpen, setMenuOpen] = useState(false)
  const closeMenu = () => setMenuOpen(false)

  return (
    <div className="staff-layout" dir={direction}>
      <aside className="staff-sidebar">
        <LogoWordmark light to="/app" />
        <StaffNavigation />
        <div className="staff-sidebar__footer"><span className="sidebar-context-dot" />Institution account</div>
      </aside>

      <Drawer open={menuOpen} onClose={closeMenu} title="Navigation" className="staff-mobile-drawer">
        <StaffNavigation onNavigate={closeMenu} />
        <LanguageModeControl />
      </Drawer>

      <div className="staff-workspace">
        <header className="staff-mobile-header">
          <button className="icon-button mobile-menu-button" type="button" aria-label="Open navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}><Icon name="menu" /></button>
          <LogoWordmark light compact to="/app" />
          <LanguageModeControl />
          <AccountButton />
        </header>

        <header className="staff-topbar">
          <div className="institution-context"><span className="institution-context__label">Current institution</span><strong>Institution</strong></div>
          <div className="staff-topbar__actions">
            <LanguageModeControl />
            <button className="icon-button notification-button" type="button" aria-label="Notifications"><Icon name="bell" /><span className="notification-dot" /></button>
            <AccountButton />
          </div>
        </header>

        <main className="staff-content"><Outlet /></main>
      </div>
    </div>
  )
}
