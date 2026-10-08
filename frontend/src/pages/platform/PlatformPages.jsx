import { useEffect, useState } from 'react'
import { Link, NavLink, Navigate, Outlet, useNavigate, useParams } from 'react-router-dom'
import { useAuth } from '../../context/AuthContext.jsx'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { apiFetch, staffApiFetch } from '../../services/api.js'
import AccountMenu from '../../components/common/AccountMenu.jsx'
import LanguageModeControl from '../../components/common/LanguageModeControl.jsx'
import LogoWordmark from '../../components/common/LogoWordmark.jsx'
import ThemeSwitch from '../../components/common/ThemeSwitch.jsx'
import Button from '../../components/common/Button.jsx'
import { useOwnerRead, ReadState, ExamPagination } from '../staff/exam-ui.jsx'
import { usePlatformCopy } from './platform-copy.js'
import './platform.css'

export function platformAccessState(user, authLoading, workspace) {
  if (authLoading) return 'loading'
  if (!user) return 'signin'
  // Keep the already authorized console mounted while Manage refreshes selection.
  // A different account or authorization reload must wait for its own response.
  if (workspace.loading && (!workspace.isPlatformAdmin || workspace.resolvedUserId !== user.id)) return 'loading'
  if (workspace.error) return 'error'
  return workspace.isPlatformAdmin ? 'ready' : 'denied'
}

export function RequirePlatform({ children }) {
  const { user, loading: authLoading } = useAuth()
  const workspace = useWorkspace()
  const { t } = usePlatformCopy()
  const state = platformAccessState(user, authLoading, workspace)
  if (state === 'loading') return <p role="status">{t('Examination operations')}</p>
  if (state === 'signin') return <Navigate to="/signin" replace />
  if (state === 'error') return <p role="alert">{t('Something went wrong. Please try again.')} <Button onClick={workspace.retry}>{t('Try again')}</Button></p>
  return workspace.isPlatformAdmin ? children : <Navigate to="/app" replace />
}

export const platformNavigation = [['/platform', 'Overview'], ['/platform/clients', 'Clients'], ['/platform/exams', 'Exams'], ['/platform/reports', 'Reports'], ['/platform/library', 'Platform Library'], ['/platform/institution-banks', 'Institution Banks']]
export function PlatformNavigation({ t }) {
  return <nav className="platform-nav" aria-label={t('Platform Administrator')}>{platformNavigation.map(([to, label]) => <NavLink key={to} to={to} end={to === '/platform'}>{t(label)}</NavLink>)}</nav>
}

export function PlatformLayout() {
  const { t, direction } = usePlatformCopy()
  const { clearSelection } = useWorkspace()
  useEffect(() => { clearSelection() }, [clearSelection])
  return <div className="platform-board" dir={direction}><header className="platform-header"><LogoWordmark to="/platform" /><span>{t('Platform Administrator')}</span><div className="platform-header-actions"><ThemeSwitch /><LanguageModeControl /><AccountMenu /></div></header><PlatformNavigation t={t} /><main className="platform-content"><Outlet /></main></div>
}

export function CompactSummary({ data, t, fields }) {
  return <dl className="platform-summary">{fields.map(([key, label]) => <div key={key}><dt>{t(label)}</dt><dd>{data[key] ?? '—'}</dd></div>)}</dl>
}

export function PlatformOverview() {
  const { t } = usePlatformCopy()
  const state = useOwnerRead('platform-overview', signal => apiFetch('platform/overview/', { signal }))
  return <section><h1>{t('Overview')}</h1><ReadState state={state} t={t}>{state.data && <CompactSummary data={state.data} t={t} fields={[["clients", "Clients"], ["active_exams", "Scheduled Exams"], ["candidates", "Candidates"], ["submissions", "Submissions"]]} />}</ReadState><Link to="/platform/clients">{t('Clients')}</Link></section>
}

export function ClientTable({ rows, t, reports = false }) {
  if (!rows.length) return <p>{t('No clients found')}</p>
  return <div className="exam-table-scroll" tabIndex={0} role="region" aria-label={t('Clients')}><table className="exam-table"><thead><tr>{['Client', 'Workspace', 'Status'].map(label => <th key={label}>{t(label)}</th>)}</tr></thead><tbody>{rows.map(client => <tr key={client.id}><td><Link to={`/platform/clients/${client.id}`}><bdi>{client.name}</bdi></Link>{reports && <small>{t('Open client reports')}</small>}</td><td>{t(client.workspace_mode === 'managed_exam' ? 'Managed Exam' : 'Full Workspace')}</td><td>{t(client.is_active ? 'Active' : 'Inactive')}</td></tr>)}</tbody></table></div>
}

export function ClientsPage({ reports = false }) {
  const { t } = usePlatformCopy()
  const [search, setSearch] = useState(''), [query, setQuery] = useState(''), [page, setPage] = useState(1)
  const state = useOwnerRead(`platform-clients:${query}:${page}`, signal => apiFetch(`platform/clients/?${new URLSearchParams({ search: query, page })}`, { signal }))
  return <section><header className="platform-heading"><h1>{t(reports ? 'Reports' : 'Clients')}</h1>{!reports && <Button as={Link} to="/platform/clients/new">{t('Create Client')}</Button>}</header>{reports && <p>{t('Choose a client to view and download examination reports.')}</p>}<form className="platform-search" onSubmit={event => { event.preventDefault(); setQuery(search); setPage(1) }}><label>{t('Search clients')}<input type="search" value={search} onChange={event => setSearch(event.target.value)} /></label><Button type="submit">{t('Search')}</Button></form><ReadState state={state} t={t}>{state.data && <><ClientTable rows={state.data.results} t={t} reports={reports} /><ExamPagination page={page} count={state.data.count} onChange={setPage} t={t} /></>}</ReadState></section>
}

function failureMessage(error, t) {
  if (error.data && typeof error.data === 'object') {
    const messages = Object.entries(error.data).map(([key, value]) => `${t({ name: 'Name', email: 'Email', initial_password: 'Initial Password', slug: 'Slug', timezone: 'Timezone' }[key] || key)}: ${Array.isArray(value) ? value.join(' ') : value}`).join(' ')
    if (messages) return messages
  }
  return t('Something went wrong. Please try again.')
}

export function CreateClientPage() {
  const { t } = usePlatformCopy()
  const navigate = useNavigate()
  const [form, setForm] = useState({ name: '', slug: '', institution_type: 'training_provider', timezone: 'Africa/Lagos', workspace_mode: 'managed_exam' })
  const [busy, setBusy] = useState(false), [error, setError] = useState('')
  async function submit(event) {
    event.preventDefault(); setBusy(true); setError('')
    try { const created = await apiFetch('platform/clients/', { method: 'POST', body: form }); navigate(`/platform/clients/${created.id}`) }
    catch (failure) { setError(failureMessage(failure, t)) }
    finally { setBusy(false) }
  }
  return <section><Link to="/platform/clients">{t('Back to Clients')}</Link><h1>{t('Create Client')}</h1><form className="platform-form" onSubmit={submit}>{[['name', 'Name', 200], ['slug', 'Slug', 220], ['timezone', 'Timezone', 64]].map(([key, label, limit]) => <label key={key}>{t(label)}<input required maxLength={limit} value={form[key]} onChange={event => setForm({ ...form, [key]: event.target.value })} /></label>)}<label>{t('Institution Type')}<select value={form.institution_type} onChange={event => setForm({ ...form, institution_type: event.target.value })}>{[['school', 'School'], ['training_provider', 'Training Provider'], ['other', 'Other']].map(([value, label]) => <option key={value} value={value}>{t(label)}</option>)}</select></label><label>{t('Workspace')}<select value={form.workspace_mode} onChange={event => setForm({ ...form, workspace_mode: event.target.value })}><option value="full_workspace">{t('Full Workspace')}</option><option value="managed_exam">{t('Managed Exam')}</option></select></label>{error && <p role="alert">{error}</p>}<Button type="submit" loading={busy}>{t('Create Client')}</Button></form></section>
}

export function AdministratorForm({ t, onSubmit, busy, error }) {
  const [form, setForm] = useState({ name: '', email: '', initial_password: '' })
  return <form className="platform-form" onSubmit={async event => { event.preventDefault(); if (await onSubmit(form)) setForm({ name: '', email: '', initial_password: '' }) }}>{[['name', 'Name', 'text'], ['email', 'Email', 'email'], ['initial_password', 'Initial Password', 'password']].map(([key, label, type]) => <label key={key}>{t(label)}<input type={type} required={key !== 'initial_password'} maxLength={key === 'email' ? 254 : 300} autoComplete={key === 'initial_password' ? 'new-password' : 'off'} value={form[key]} onChange={event => setForm({ ...form, [key]: event.target.value })} /></label>)}<p>{t('Required for new accounts only. Existing accounts keep their password.')}</p>{error && <p role="alert">{error}</p>}<Button type="submit" loading={busy}>{t('Add Administrator')}</Button></form>
}

export function ReleasePermission({ client, t, busy, onChange }) {
  return <label className="platform-permission"><input type="checkbox" checked={client.can_release_candidate_results} disabled={busy} onChange={event => onChange(event.target.checked)} /><span>{t('Allow client administrators to release results to candidates')} · {t(client.can_release_candidate_results ? 'On' : 'Off')}</span></label>
}

export function ClientDetailPage() {
  const { clientId } = useParams()
  const { t } = usePlatformCopy()
  const navigate = useNavigate()
  const { refreshAndSelect } = useWorkspace()
  const state = useOwnerRead(`client:${clientId}`, signal => apiFetch(`platform/clients/${clientId}/`, { signal }))
  const admins = useOwnerRead(`client-admins:${clientId}`, signal => apiFetch(`platform/clients/${clientId}/administrators/`, { signal }))
  const [busy, setBusy] = useState(false), [error, setError] = useState(''), [success, setSuccess] = useState('')
  async function mutate(path, body) {
    setBusy(true); setError(''); setSuccess('')
    try { await apiFetch(`platform/clients/${clientId}/${path}/`, { method: 'POST', body }); state.retry(); admins.retry(); setSuccess(t('Saved')); return true }
    catch (failure) { setError(failureMessage(failure, t)); return false }
    finally { setBusy(false) }
  }
  async function manage(path = '/app') {
    setBusy(true); setError('')
    try { await refreshAndSelect(Number(clientId)); navigate(path) }
    catch (failure) { setError(failureMessage(failure, t)); setBusy(false) }
  }
  return <section><Link to="/platform/clients">{t('Back to Clients')}</Link><ReadState state={state} t={t}>{state.data && <><header className="platform-heading"><h1><bdi>{state.data.name}</bdi></h1><Button disabled={busy || !state.data.is_active} onClick={() => manage()}>{t('Manage Client')}</Button></header><p>{t(state.data.workspace_mode === 'managed_exam' ? 'Managed Exam' : 'Full Workspace')} · <bdi>{state.data.timezone}</bdi></p>{state.data.is_active && <Button variant="outline" disabled={busy} onClick={() => manage('/app/reports')}>{t('Open client reports')}</Button>}<ReleasePermission client={state.data} t={t} busy={busy || state.loading} onChange={enabled => mutate('release-permission', { enabled })} /><h2>{t('Administrators')}</h2><ReadState state={admins} t={t}>{admins.data && (admins.data.length ? <ul className="platform-admins">{admins.data.map(admin => <li key={admin.id}><bdi>{admin.name}</bdi> · <bdi>{admin.email}</bdi> · {t(admin.is_active ? 'Active' : 'Inactive')}</li>)}</ul> : <p>{t('No administrators yet')}</p>)}</ReadState><AdministratorForm t={t} busy={busy} error={error} onSubmit={form => mutate('administrators', form)} /></>}</ReadState>{error && <p role="alert">{error}</p>}{success && <p role="status">{success}</p>}</section>
}

export function PlatformExamsPage() {
  const { t } = usePlatformCopy()
  const navigate = useNavigate()
  const { refreshAndSelect } = useWorkspace()
  const [page, setPage] = useState(1), [busy, setBusy] = useState(false), [error, setError] = useState('')
  const state = useOwnerRead(`platform-exams:${page}`, signal => apiFetch(`platform/exams/?page=${page}`, { signal }))
  async function open(exam) {
    setBusy(true); setError('')
    try { await refreshAndSelect(exam.institution); navigate(`/app/exams/${exam.id}`) }
    catch (failure) { setError(failureMessage(failure, t)); setBusy(false) }
  }
  return <section><h1>{t('Exams')}</h1><ReadState state={state} t={t}>{state.data && <><div className="exam-table-scroll"><table className="exam-table"><thead><tr>{['Client', 'Exams', 'Status'].map(label => <th key={label}>{t(label)}</th>)}</tr></thead><tbody>{state.data.results.map(exam => <tr key={exam.id}><td><bdi>{exam.client}</bdi></td><td><button type="button" className="platform-link" disabled={busy} onClick={() => open(exam)}><bdi>{exam.title}</bdi></button></td><td>{t(exam.status)}</td></tr>)}</tbody></table></div>{!state.data.results.length && <p>{t('No exams found')}</p>}<ExamPagination page={page} count={state.data.count} onChange={setPage} t={t} /></>}</ReadState>{error && <p role="alert">{error}</p>}</section>
}

export function ManagedOverview() {
  const { currentWorkspace, currentRole } = useWorkspace()
  const { t } = usePlatformCopy()
  const state = useOwnerRead(`managed-overview:${currentWorkspace.institution.id}`, signal => staffApiFetch('institution/dashboard/', { signal }))
  return <section className="managed-board"><h1>{t('Overview')}</h1><ReadState state={state} t={t}>{state.data && <CompactSummary data={state.data.counts} t={t} fields={[["active_candidates", "Candidates"], ["assessments", "Exams"], ["submitted_attempts", "Submissions"], ["results", "Results"]]} />}</ReadState><div className="exam-actions">{['exams', 'submissions', 'results', 'reports'].map(path => <Link key={path} to={`/app/${path}`}>{t({ exams: 'Exams', submissions: 'Submissions', results: 'Results', reports: 'Reports' }[path])}</Link>)}{currentRole === 'platform_admin' && <Link to="/app/questions">{t('Questions')}</Link>}</div></section>
}
