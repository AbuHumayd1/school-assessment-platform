import { useState } from 'react'
import { Link, NavLink, useLocation, useOutlet } from 'react-router-dom'
import Button from '../components/common/Button.jsx'
import Drawer from '../components/common/Drawer.jsx'
import Icon from '../components/common/Icon.jsx'
import LogoWordmark from '../components/common/LogoWordmark.jsx'
import { PublicLanguageSwitcher, PublicLocaleProvider, PublicLocaleTree, translatePublicText, usePublicLocale } from '../context/PublicLocaleContext.jsx'

const links = [
  ['/features', 'Features'],
  ['/how-it-works', 'How it works'],
  ['/pricing', 'Pricing'],
  ['/about', 'About & Contact'],
]

function PublicNavigation({ onNavigate }) {
  const { locale } = usePublicLocale()
  return (
    <nav className="public-nav" aria-label={locale === 'ar' ? translatePublicText('Main navigation') : 'Main navigation'}>
      {links.map(([to, label]) => <NavLink key={to} to={to} onClick={onNavigate}>{locale === 'ar' ? translatePublicText(label) : label}</NavLink>)}
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
  const standaloneRoute = pathname === '/signin' || pathname === '/setup'
  const closeMenu = () => setMenuOpen(false)

  return (
    <PublicLocaleTree><div className={`public-layout${standaloneRoute ? ' public-layout--standalone' : ''}`}>
      {!standaloneRoute && <header className="public-header">
        <LogoWordmark ariaLabel={locale === 'ar' ? translatePublicText('School Assessment Platform home') : 'School Assessment Platform home'} />
        <PublicNavigation />
        <div className="public-header__actions">
          <PublicLanguageSwitcher />
          <Button as={Link} to="/signin">Sign In</Button>
          <Button as={Link} to="/setup" variant="outline" className="public-header__cta">Get Started</Button>
        </div>
        <button className="icon-button public-menu-toggle" type="button" aria-label={locale === 'ar' ? translatePublicText('Open navigation') : 'Open navigation'} aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}>
          <Icon name="menu" />
        </button>
      </header>}

      {!standaloneRoute && <Drawer open={menuOpen} onClose={closeMenu} title={locale === 'ar' ? translatePublicText('Menu') : 'Menu'} closeLabel={locale === 'ar' ? translatePublicText('Close menu') : 'Close menu'} className="public-mobile-drawer">
        <PublicNavigation onNavigate={closeMenu} />
        <PublicLanguageSwitcher />
        <div className="public-mobile-drawer__actions">
          <Button as={Link} to="/signin" onClick={closeMenu}>Sign In</Button>
          <Button as={Link} to="/setup" variant="outline" onClick={closeMenu}>Get Started</Button>
        </div>
      </Drawer>}

      {standaloneRoute && <div className="public-standalone-locale"><PublicLanguageSwitcher /></div>}
      <main className="public-main">{outlet}</main>

      {!standaloneRoute && <footer className="public-footer">
        <div className="public-footer__content">
          <div className="public-footer__brand">
            <LogoWordmark ariaLabel={locale === 'ar' ? translatePublicText('School Assessment Platform home') : 'School Assessment Platform home'} />
            <p>Create questions, conduct examinations and manage results from one place.</p>
          </div>
          <nav className="public-footer__column" aria-label="Product links">
            <h2>Product</h2>
            <Link to="/features">Features</Link>
            <Link to="/how-it-works">How It Works</Link>
          </nav>
          <nav className="public-footer__column" aria-label="Platform links">
            <h2>Platform</h2>
            <Link to="/pricing">Pricing</Link>
            <Link to="/setup">Get Started</Link>
          </nav>
          <nav className="public-footer__column" aria-label="Organisation links">
            <h2>Organisation</h2>
            <Link to="/about">About</Link>
            <Link to="/contact">Contact</Link>
            <Link to="/signin">Sign In</Link>
          </nav>
        </div>
        <div className="public-footer__bottom">
          <p className="public-footer__copyright">Copyright {new Date().getFullYear()} School Assessment Platform</p>
          <p>For education, training and examination organisations.</p>
        </div>
      </footer>}
    </div></PublicLocaleTree>
  )
}
