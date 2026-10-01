import { useState } from 'react'
import { Link, NavLink, Outlet } from 'react-router-dom'
import Button from '../components/common/Button.jsx'
import Drawer from '../components/common/Drawer.jsx'
import Icon from '../components/common/Icon.jsx'
import LogoWordmark from '../components/common/LogoWordmark.jsx'

const links = [
  ['/features', 'Features'],
  ['/how-it-works', 'How it works'],
  ['/pricing', 'Pricing'],
  ['/about', 'About'],
  ['/contact', 'Contact'],
  ['/signin', 'Sign In'],
]

function PublicNavigation({ onNavigate }) {
  return (
    <nav className="public-nav" aria-label="Main navigation">
      {links.map(([to, label]) => <NavLink key={to} to={to} onClick={onNavigate}>{label}</NavLink>)}
    </nav>
  )
}

export default function PublicLayout() {
  const [menuOpen, setMenuOpen] = useState(false)
  const closeMenu = () => setMenuOpen(false)

  return (
    <div className="public-layout">
      <header className="public-header">
        <LogoWordmark />
        <PublicNavigation />
        <div className="public-header__actions">
          <Button as={Link} to="/signin">Sign In</Button>
          <Button as={Link} to="/setup" variant="outline" className="public-header__cta">Setup Preview</Button>
        </div>
        <button className="icon-button public-menu-toggle" type="button" aria-label="Open navigation" aria-expanded={menuOpen} onClick={() => setMenuOpen(true)}>
          <Icon name="menu" />
        </button>
      </header>

      <Drawer open={menuOpen} onClose={closeMenu} title="Menu" className="public-mobile-drawer">
        <PublicNavigation onNavigate={closeMenu} />
        <div className="public-mobile-drawer__actions">
          <Button as={Link} to="/signin" onClick={closeMenu}>Sign In</Button>
          <Button as={Link} to="/setup" variant="outline" onClick={closeMenu}>Setup Preview</Button>
        </div>
      </Drawer>

      <main className="public-main"><Outlet /></main>

      <footer className="public-footer">
        <div className="public-footer__brand">
          <LogoWordmark />
          <p>Create questions, conduct examinations and manage results from one place.</p>
        </div>
        <nav aria-label="Footer navigation">
          <Link to="/features">Features</Link>
          <Link to="/how-it-works">How It Works</Link>
          <Link to="/pricing">Pricing</Link>
          <Link to="/about">About</Link>
          <Link to="/contact">Contact</Link>
          <Link to="/signin">Sign In</Link>
        </nav>
        <p className="public-footer__copyright">Copyright {new Date().getFullYear()} School Assessment Platform</p>
      </footer>
    </div>
  )
}
