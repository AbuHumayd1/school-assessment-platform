import { useState } from 'react'
import { Link, NavLink, useLocation, useOutlet } from 'react-router-dom'
import PublicMarketingMotion from '../components/common/PublicMarketingMotion.jsx'
import Button from '../components/common/Button.jsx'
import ManagedExamCTA from '../components/common/ManagedExamCTA.jsx'
import ThemeSwitch from '../components/common/ThemeSwitch.jsx'
import Drawer from '../components/common/Drawer.jsx'
import Icon from '../components/common/Icon.jsx'
import LogoWordmark from '../components/common/LogoWordmark.jsx'
import { PublicLanguageSwitcher, PublicLocaleProvider, PublicLocaleTree, translatePublicText, usePublicLocale } from '../context/PublicLocaleContext.jsx'

const links = [
  ['/#managed-examinations', 'Managed Examinations'],
  ['/#institution-workspace', 'Institution Workspace'],
  ['/pricing', 'Pricing'],
  ['/contact', 'Contact'],
]

export function PublicNavigation({ onNavigate }) {
  const { locale } = usePublicLocale()
  return (
    <nav className="public-nav" aria-label={locale === 'ar' ? translatePublicText('Main navigation') : 'Main navigation'}>
      {links.map(([to, label]) => {
        const NavigationLink = to.includes('#') ? Link : NavLink
        return <NavigationLink key={to} to={to} onClick={onNavigate}>{locale === 'ar' ? translatePublicText(label) : label}</NavigationLink>
      })}
    </nav>
  )
}

export default function PublicLayout() {
  return <PublicLocaleProvider><PublicLayoutContent /></PublicLocaleProvider>
}

function PublicLayoutContent() {
  const [menuOpen, setMenuOpen] = useState(false)
  const { locale } = usePublicLocale()
  const { pathname } = useLocation()
  const outlet = useOutlet()
  const examRoute = /^\/take-exam\/attempt\//.test(pathname)
  const standaloneRoute = pathname === '/signin' || pathname === '/setup' || examRoute
  const marketingRoute = ['/', '/features', '/how-it-works', '/pricing', '/about', '/contact'].includes(pathname)
  const closeMenu = () => setMenuOpen(false)

  return (
    <PublicLocaleTree><div className={`public-layout${standaloneRoute ? ' public-layout--standalone' : ''}${examRoute ? ' public-layout--exam' : ''}${marketingRoute ? ' public-layout--marketing' : ''}`}>
      {!standaloneRoute && <header className="public-header">
        <LogoWordmark ariaLabel={locale === 'ar' ? translatePublicText('Madaar home') : 'Madaar home'} />
        <PublicNavigation />
        <div className="public-header__actions">
          <ThemeSwitch locale={locale} />
          <PublicLanguageSwitcher />
          <Button as={Link} to="/take-exam" variant="outline" className="public-exam-cta">Take an Exam</Button>
          <Button as={Link} to="/signin" variant="ghost">Sign In</Button>
          <Button as={ManagedExamCTA} className="public-header__cta">Request an Examination</Button>
        </div>
        <button className="icon-button public-menu-toggle" type="button" aria-label={locale === 'ar' ? translatePublicText('Open navigation') : 'Open navigation'} aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}>
          <Icon name="menu" />
        </button>
      </header>}

      {!standaloneRoute && <Drawer open={menuOpen} onClose={closeMenu} title={locale === 'ar' ? translatePublicText('Menu') : 'Menu'} closeLabel={locale === 'ar' ? translatePublicText('Close menu') : 'Close menu'} className="public-mobile-drawer">
        <div className="public-mobile-drawer__actions">
          <Button as={Link} to="/take-exam" variant="outline" className="public-exam-cta" onClick={closeMenu}>Take an Exam</Button>
          <Button as={Link} to="/signin" variant="ghost" onClick={closeMenu}>Sign In</Button>
          <Button as={ManagedExamCTA} onClick={closeMenu}>Request an Examination</Button>
        </div>
        <PublicLanguageSwitcher />
        <ThemeSwitch locale={locale} />
        <PublicNavigation onNavigate={closeMenu} />
      </Drawer>}

      {standaloneRoute && !examRoute && <div className="public-standalone-locale"><ThemeSwitch locale={locale} /><PublicLanguageSwitcher /></div>}
      <main className="public-main"><PublicMarketingMotion enabled={marketingRoute} routeKey={pathname}>{outlet}</PublicMarketingMotion></main>

      {!standaloneRoute && <footer className="public-footer">
        <div className="public-footer__content">
          <div className="public-footer__brand">
            <LogoWordmark ariaLabel={locale === 'ar' ? translatePublicText('Madaar home') : 'Madaar home'} />
            <p>Create. Assess. Mark. Analyse. Improve.</p>
          </div>
          <nav className="public-footer__column" aria-label="Product links">
            <h2>Product</h2>
            <Link to="/#managed-examinations">Managed Examinations</Link>
            <Link to="/#how-it-works">How It Works</Link>
          </nav>
          <nav className="public-footer__column" aria-label="Platform links">
            <h2>Platform</h2>
            <Link to="/#institution-workspace">Institution Workspace</Link>
            <ManagedExamCTA>Request an Examination</ManagedExamCTA>
          </nav>
          <nav className="public-footer__column" aria-label="Organisation links">
            <h2>Organisation</h2>
            <Link to="/about">About</Link>
            <Link to="/contact">Contact</Link>
            <Link to="/signin">Sign In</Link>
          </nav>
        </div>
        <div className="public-footer__bottom">
          <p className="public-footer__copyright">Copyright {new Date().getFullYear()} Madaar</p>
          <p>For education, training and examination organisations.</p>
        </div>
      </footer>}
    </div></PublicLocaleTree>
  )
}
