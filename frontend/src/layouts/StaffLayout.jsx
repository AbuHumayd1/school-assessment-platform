import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import Drawer from '../components/common/Drawer.jsx'
import Icon from '../components/common/Icon.jsx'
import LogoWordmark from '../components/common/LogoWordmark.jsx'
import LanguageModeControl from '../components/common/LanguageModeControl.jsx'
import AccountMenu from '../components/common/AccountMenu.jsx'
import { useLanguageMode } from '../context/LanguageModeContext.jsx'
import { useWorkspace } from '../context/WorkspaceContext.jsx'
import { canAccessWorkspaceCapability } from '../utils/staffCapabilities.js'

const navigation = [
  ['/app', 'Dashboard', 'home', true, 'dashboard'],
  ['/app/students', 'Candidates', 'users', false, 'candidates'],
  ['/app/staff', 'Teachers & Staff', 'staff', false, 'memberships'],
  ['/app/classes', 'Classes / Cohorts', 'layers', false, 'groups'],
  ['/app/subjects', 'Subjects', 'book', false, 'subjects'],
  ['/app/questions', 'Questions', 'file', false, 'questions'],
  ['/app/exams', 'Exams', 'clipboard', false, 'assessments'],
  ['/app/submissions', 'Submissions', 'inbox', false, 'submissions'],
  ['/app/results', 'Results', 'chart', false, 'results'],
  ['/app/reports', 'Reports', 'chart', false, 'reports'],
  ['/app/settings', 'Settings', 'settings', false, 'institution_settings'],
]

function StaffNavigation({ onNavigate }) {
  const { label: localizedLabel } = useLanguageMode()
  const { currentRole, currentWorkspace } = useWorkspace()
  const arabicTranslations = {
    Candidates: 'المرشحون',
    Dashboard: '\u0644\u0648\u062d\u0629 \u0627\u0644\u062a\u062d\u0643\u0645', Students: '\u0627\u0644\u0637\u0644\u0627\u0628',
    'Teachers & Staff': '\u0627\u0644\u0645\u0639\u0644\u0645\u0648\u0646 \u0648\u0627\u0644\u0645\u0648\u0638\u0641\u0648\u0646',
    'Classes / Cohorts': '\u0627\u0644\u0641\u0635\u0648\u0644 \u0648\u0627\u0644\u0645\u062c\u0645\u0648\u0639\u0627\u062a',
    Subjects: '\u0627\u0644\u0645\u0648\u0627\u062f', Questions: '\u0627\u0644\u0623\u0633\u0626\u0644\u0629',
    Exams: '\u0627\u0644\u0627\u062e\u062a\u0628\u0627\u0631\u0627\u062a', Submissions: '\u0627\u0644\u062a\u0633\u0644\u064a\u0645\u0627\u062a',
    Results: '\u0627\u0644\u0646\u062a\u0627\u0626\u062c', Reports: '\u0627\u0644\u062a\u0642\u0627\u0631\u064a\u0631',
    Settings: '\u0627\u0644\u0625\u0639\u062f\u0627\u062f\u0627\u062a',
  }
  return (
    <nav className="app-navigation" aria-label="Institution navigation">
      {navigation.filter(([, , , , capability]) => canAccessWorkspaceCapability(currentRole, capability, currentWorkspace?.institution.workspace_mode)).map(([to, label, icon, end]) => (
        <NavLink key={to} to={to} end={end} title={label} onClick={onNavigate} className={({ isActive }) => `app-navigation__link${isActive ? ' is-active' : ''}`}>
          <Icon name={icon} />
          <span>{localizedLabel(label === 'Dashboard' && currentWorkspace?.institution.workspace_mode === 'managed_exam' ? 'Overview' : label, label === 'Dashboard' && currentWorkspace?.institution.workspace_mode === 'managed_exam' ? '\u0646\u0638\u0631\u0629 \u0639\u0627\u0645\u0629' : arabicTranslations[label] || label)}</span>
        </NavLink>
      ))}
    </nav>
  )
}

export default function StaffLayout() {
  const { direction } = useLanguageMode()
  const { label: localizedLabel } = useLanguageMode()
  const { currentWorkspace, currentRole, workspaces, selectWorkspace, clearSelection } = useWorkspace()
  const [menuOpen, setMenuOpen] = useState(false)
  const closeMenu = () => setMenuOpen(false)
  const roleLabels = { platform_admin: 'Platform administrator', institution_admin: 'Workspace administrator', teacher: 'Teacher', examiner: 'Examiner' }
  const roleArabicTranslations = {
    platform_admin: '\u0645\u062f\u064a\u0631 \u0627\u0644\u0645\u0646\u0635\u0629',
    institution_admin: '\u0645\u062f\u064a\u0631 \u0645\u0633\u0627\u062d\u0629 \u0627\u0644\u0639\u0645\u0644',
    teacher: '\u0645\u0639\u0644\u0645', examiner: '\u0645\u0645\u062a\u062d\u0646',
  }

  return (
    <div className={`staff-layout${currentWorkspace?.institution.workspace_mode === 'managed_exam' ? ' staff-layout--managed' : ''}`} dir={direction}>
      <aside className="staff-sidebar">
        <LogoWordmark light to="/app" />
        <StaffNavigation />
        <div className="staff-sidebar__footer"><span className="sidebar-context-dot" /><span>{currentWorkspace?.institution.name}</span></div>
      </aside>

      <Drawer open={menuOpen} onClose={closeMenu} title="Navigation" side={direction === 'rtl' ? 'right' : 'left'} className="staff-mobile-drawer">
        <StaffNavigation onNavigate={closeMenu} />
        <LanguageModeControl />
      </Drawer>

      <div className="staff-workspace">
        <header className="staff-mobile-header">
          <button className="icon-button mobile-menu-button" type="button" aria-label="Open navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}><Icon name="menu" /></button>
          <LogoWordmark light compact to="/app" />
          <div className="staff-mobile-workspace">
            <span className="institution-context__label">{localizedLabel(currentRole === 'platform_admin' ? 'Managing' : 'Current workspace', currentRole === 'platform_admin' ? '\u0625\u062f\u0627\u0631\u0629' : 'مساحة العمل الحالية')}</span>
            {workspaces.length > 1 ? (
              <select aria-label="Select workspace" value={currentWorkspace?.institution.id || ''} onChange={event => selectWorkspace(event.target.value)}>
                {workspaces.map(item => <option key={item.institution.id} value={item.institution.id}>{item.institution.name}</option>)}
              </select>
            ) : <strong>{currentWorkspace?.institution.name}</strong>}
            <span className="workspace-role-label">{localizedLabel(roleLabels[currentRole] || currentRole, roleArabicTranslations[currentRole] || currentRole)}</span>
            {currentRole === 'platform_admin' && <Link className="managed-context" to="/platform" onClick={clearSelection}>{localizedLabel('Return to Platform', '\u0627\u0644\u0639\u0648\u062f\u0629 \u0625\u0644\u0649 \u0627\u0644\u0645\u0646\u0635\u0629')}</Link>}
          </div>
          <LanguageModeControl />
          <AccountMenu />
        </header>

        <header className="staff-topbar">
          <div className="institution-context">
            <span className="institution-context__label">{localizedLabel(currentRole === 'platform_admin' ? 'Managing' : 'Current workspace', currentRole === 'platform_admin' ? '\u0625\u062f\u0627\u0631\u0629' : '\u0645\u0633\u0627\u062d\u0629 \u0627\u0644\u0639\u0645\u0644 \u0627\u0644\u062d\u0627\u0644\u064a\u0629')}</span>
            {workspaces.length > 1 ? (
              <select className="form-control workspace-switcher" aria-label="Select workspace" value={currentWorkspace?.institution.id || ''} onChange={event => selectWorkspace(event.target.value)}>
                {workspaces.map(item => <option key={item.institution.id} value={item.institution.id}>{item.institution.name} · {localizedLabel(roleLabels[item.role] || item.role, roleArabicTranslations[item.role] || item.role)}</option>)}
              </select>
            ) : <strong>{currentWorkspace?.institution.name}</strong>}
            <span className="workspace-role-label">{localizedLabel(roleLabels[currentRole] || currentRole, roleArabicTranslations[currentRole] || currentRole)}</span>
            {currentRole === 'platform_admin' && <Link className="managed-context" to="/platform" onClick={clearSelection}>{localizedLabel('Return to Platform', '\u0627\u0644\u0639\u0648\u062f\u0629 \u0625\u0644\u0649 \u0627\u0644\u0645\u0646\u0635\u0629')}</Link>}
          </div>
          <div className="staff-topbar__actions">
            <LanguageModeControl />
            <button className="icon-button notification-button" type="button" aria-label="Notifications"><Icon name="bell" /><span className="notification-dot" /></button>
            <AccountMenu />
          </div>
        </header>

        <main className="staff-content"><Outlet key={currentWorkspace?.institution.id} /></main>
      </div>
    </div>
  )
}
