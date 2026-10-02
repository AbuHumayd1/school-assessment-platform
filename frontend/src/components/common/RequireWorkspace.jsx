import { Link, Navigate, useLocation } from 'react-router-dom'
import LoadingState from './LoadingState.jsx'
import { useAuth } from '../../context/AuthContext.jsx'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { useLanguageMode } from '../../context/LanguageModeContext.jsx'
import './workspace-access.css'

const roleLabels = {
  platform_admin: 'Platform administrator',
  institution_admin: 'Workspace administrator',
  teacher: 'Teacher',
  examiner: 'Examiner',
}

export default function RequireWorkspace({ children }) {
  const { user, loading: authLoading } = useAuth()
  const workspace = useWorkspace()
  const { direction } = useLanguageMode()
  const location = useLocation()

  if (authLoading) return <LoadingState label="Checking your session" />
  if (!user) return <Navigate to="/signin" replace state={{ from: location }} />
  if (workspace.loading) return <LoadingState label="Checking your workspace access" />

  if (workspace.accessState === 'error') {
    return (
      <main className="workspace-access" dir={direction}>
        <section className="workspace-access__card" role="alert">
          <h1>Workspace access could not be checked</h1>
          <p>Check your connection, then try again.</p>
          <button className="button button--primary" type="button" onClick={workspace.retry}>Try again</button>
        </section>
      </main>
    )
  }

  if (workspace.accessState === 'no_workspace') {
    return (
      <main className="workspace-access" dir={direction}>
        <section className="workspace-access__card">
          <span className="workspace-access__mark" aria-hidden="true">SA</span>
          <h1>No workspace access</h1>
          <p>This account does not have an active administrator, teacher or examiner relationship with a workspace.</p>
          {user.is_candidate && <Link className="button button--secondary" to="/student">Open the Student Portal</Link>}
          <Link className="workspace-access__link" to="/">Return to the website</Link>
        </section>
      </main>
    )
  }

  if (workspace.accessState === 'select_workspace') {
    return (
      <main className="workspace-access" dir={direction}>
        <section className="workspace-access__card workspace-access__card--wide">
          <span className="workspace-access__mark" aria-hidden="true">SA</span>
          <p className="workspace-access__eyebrow">Choose a workspace</p>
          <h1>Select where you want to work</h1>
          <p>Your access and available tools depend on your relationship with each workspace.</p>
          <div className="workspace-choice-list">
            {workspace.workspaces.map(item => (
              <button key={item.institution.id} className="workspace-choice" type="button" onClick={() => workspace.selectWorkspace(item.institution.id)}>
                <span className="workspace-choice__identity"><strong>{item.institution.name}</strong><small>{item.institution.institution_type.replaceAll('_', ' ')}</small></span>
                <span className="workspace-choice__role">{roleLabels[item.role] || item.role}</span>
              </button>
            ))}
          </div>
        </section>
      </main>
    )
  }

  return children
}
