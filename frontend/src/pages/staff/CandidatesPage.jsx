import { useEffect, useRef, useState } from 'react'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { useLanguageMode } from '../../context/LanguageModeContext.jsx'
import { staffApiFetch } from '../../services/api.js'
import { candidateStatuses, candidateDeletionError, deleteCandidate, getCandidate, listCandidates, portalAccessState, provisionCandidate, saveCandidate } from '../../services/candidates.js'
import Button from '../../components/common/Button.jsx'
import Modal from '../../components/common/Modal.jsx'
import { candidateCopy } from './candidate-copy.js'
import './candidates.css'
import CandidateImport from './CandidateImport.jsx'

const accessLabels = { not_enabled: 'Portal access not enabled', enabled: 'Portal access enabled', account_inactive: 'Account inactive', candidate_inactive: 'Candidate inactive' }
const statusLabel = value => value[0].toUpperCase() + value.slice(1)

export function CandidateRoster({ rows, t, onSelect, onAdd, filtered = false, busy = false }) {
  if (!rows.length) return <div className="cm-empty"><h2>{t(filtered ? 'No matching candidates' : 'No candidates yet')}</h2>
    <p>{t(filtered ? 'Try another search or status.' : 'Add your first candidate. An email, account or group is not required.')}</p>
    {!filtered && <Button disabled={busy} onClick={onAdd}>{t('Add candidate')}</Button>}</div>
  return <div className="cm-roster">
    <div className="cm-roster-heading" aria-hidden="true"><span>{t('Name')}</span><span>{t('Candidate ID')}</span><span>{t('Status')}</span><span>{t('Portal access')}</span></div>
    <ul>{rows.map(row => <li key={row.id}><button type="button" disabled={busy} onClick={() => onSelect(row.id)} className="cm-row">
      <span className="cm-person"><span className="cm-avatar" aria-hidden="true">{row.first_name[0]}{row.last_name[0]}</span><span><strong><bdi>{row.first_name} {row.last_name}</bdi></strong><small><bdi>{row.email || t('Not provided')}</bdi></small></span></span>
      <span><small className="cm-mobile-label">{t('Candidate ID')}</small><bdi>{row.candidate_id}</bdi></span>
      <span className={`cm-status cm-status--${row.status}`}>{t(statusLabel(row.status))}</span>
      <span className="cm-access">{t(accessLabels[portalAccessState(row)])}</span>
    </button></li>)}</ul>
  </div>
}

export function InitialCredentials({ credentials, t }) {
  if (!credentials) return null
  return <div className="cm-credentials"><p>{t('These credentials are shown only now. Communicate them securely to the candidate before closing. They cannot be displayed again.')}</p>
    <label>{t('Email address')}<input className="form-control" readOnly dir="ltr" value={credentials.account.email} autoComplete="off" /></label>
    <label>{t('Initial password')}<input className="form-control" readOnly dir="ltr" value={credentials.initial_password} autoComplete="off" /></label>
    <p>{t('Sign-in page')}: <bdi>/signin</bdi></p>
    <p>{t('First-login password change is not enforced in this phase. No email has been sent.')}</p>
  </div>
}

export function CandidateDeleteAction({ administrator, busy, onClick, t }) {
  return administrator ? <Button variant="outline" className="cm-delete" disabled={busy} onClick={onClick}>{t('Delete candidate')}</Button> : null
}

export function CandidateDeleteConfirmation({ candidate, busy, error, onConfirm, onCancel, t }) {
  return <div className="cm-delete-confirmation">
    <p>{t('You are about to permanently delete:')}</p>
    <p><strong><bdi>{candidate.first_name} {candidate.last_name}</bdi></strong><br />{t('Candidate ID')}: <bdi>{candidate.candidate_id}</bdi></p>
    <p>{t('This action cannot be undone.')}</p>
    {candidate.portal_account && <p>{t('The linked user account will remain.')}</p>}
    {error && <p role="alert" className="cm-error">{t(error)}</p>}
    <div className="cm-form-actions"><Button variant="outline" autoFocus disabled={busy} onClick={onCancel}>{t('Cancel')}</Button>
      <Button variant="outline" className="cm-delete" loading={busy} onClick={onConfirm}>{t(busy ? 'Deleting…' : 'Delete candidate')}</Button></div>
  </div>
}

export default function CandidatesPage() {
  const { currentWorkspace, currentRole } = useWorkspace()
  const { label, direction } = useLanguageMode()
  const t = text => label(text, candidateCopy[text] || text)
  const institutionId = currentWorkspace.institution.id
  const administrator = ['institution_admin', 'platform_admin'].includes(currentRole)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [status, setStatus] = useState('')
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [listing, setListing] = useState(null)
  const [selected, setSelected] = useState(null)
  const [detail, setDetail] = useState(null)
  const [formRecord, setFormRecord] = useState(null)
  const [errors, setErrors] = useState({})
  const [notice, setNotice] = useState('')
  const [busy, setBusy] = useState(false)
  const [credentials, setCredentials] = useState(null)
  const [deleteRecord, setDeleteRecord] = useState(null)
  const [deleteError, setDeleteError] = useState('')
  const [importOpen, setImportOpen] = useState(false)
  const alive = useRef(true)
  const actionPending = useRef(false)
  const detailHeading = useRef(null)
  const listKey = `${institutionId}:${query}:${status}:${page}:${revision}`
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  useEffect(() => {
    const controller = new AbortController()
    let cancelled = false
    listCandidates(staffApiFetch, institutionId, { search: query, status, page, signal: controller.signal })
      .then(data => { if (!cancelled) setListing({ key: listKey, data }) })
      .catch(error => { if (!cancelled) setListing({ key: listKey, error }) })
    return () => { cancelled = true; controller.abort() }
  }, [institutionId, query, status, page, revision, listKey])
  useEffect(() => {
    if (selected == null) return
    const controller = new AbortController()
    let cancelled = false
    setDetail(null)
    getCandidate(staffApiFetch, institutionId, selected, { signal: controller.signal })
      .then(data => { if (!cancelled) setDetail({ id: selected, data }) })
      .catch(error => { if (!cancelled) setDetail({ id: selected, error }) })
    return () => { cancelled = true; controller.abort() }
  }, [selected, revision, institutionId])
  useEffect(() => { if (detail?.data) detailHeading.current?.focus() }, [detail])
  const visible = listing?.key === listKey ? listing : null
  const candidate = detail?.id === selected ? detail?.data : null
  const totalPages = visible?.data ? Math.max(1, Math.ceil(visible.data.count / 25)) : 1
  const choose = id => { if (actionPending.current) return; setSelected(id); setCredentials(null); setNotice('') }
  const startForm = record => { if (actionPending.current) return; setFormRecord(record || {}); setErrors({}); setNotice(''); setCredentials(null) }
  const closeForm = () => { if (!actionPending.current) { setFormRecord(null); setErrors({}); setNotice('') } }
  async function submit(event) {
    event.preventDefault()
    if (actionPending.current) return
    const form = event.currentTarget
    if (!form.reportValidity()) return
    actionPending.current = true; setBusy(true); setErrors({}); setNotice('')
    let invalidField
    try {
      const saved = await saveCandidate(staffApiFetch, institutionId, formRecord.id, Object.fromEntries(new FormData(form)), { profileOnly: !administrator })
      if (!alive.current) return
      setFormRecord(null); setSelected(saved.id); setDetail(null); setPage(1); setRevision(value => value + 1)
    } catch (error) {
      if (!alive.current) return
      if (error.status === 400 && error.data) {
        const fields = ['first_name', 'last_name', 'candidate_id', 'email', 'phone', 'date_of_birth', 'status']
        const next = Object.fromEntries(fields.filter(field => error.data[field]).map(field => [field, true]))
        setErrors(next); setNotice('Please check the highlighted fields.'); invalidField = Object.keys(next)[0]
      } else setNotice('We could not complete this request. Please try again.')
    } finally {
      actionPending.current = false
      if (alive.current) { setBusy(false); if (invalidField) requestAnimationFrame(() => form.elements[invalidField]?.focus()) }
    }
  }
  async function enableAccess() {
    if (actionPending.current) return
    actionPending.current = true; setBusy(true); setNotice('')
    try {
      const issued = await provisionCandidate(staffApiFetch, institutionId, candidate.id)
      if (!alive.current) return
      setCredentials(issued); setRevision(value => value + 1)
    } catch (error) {
      if (!alive.current) return
      const messages = {
        email_exists: 'An account with this email already exists. Linking requires a separate controlled process.',
        already_linked: 'This account is already linked. Credentials cannot be issued again.',
        email_required: 'Email-based portal access requires a saved email and an active candidate.',
        candidate_inactive: 'Email-based portal access requires a saved email and an active candidate.',
        identity_locked: 'Account linkage cannot change after an examination attempt starts.',
      }
      setNotice(messages[error.data?.code] || 'We could not complete this request. Please try again.')
    } finally { actionPending.current = false; if (alive.current) setBusy(false) }
  }
  const closeDelete = () => { if (!actionPending.current) { setDeleteRecord(null); setDeleteError('') } }
  async function confirmDelete() {
    if (actionPending.current || !deleteRecord || !administrator) return
    actionPending.current = true; setBusy(true); setDeleteError('')
    try {
      await deleteCandidate(staffApiFetch, institutionId, deleteRecord.id)
      if (!alive.current) return
      setDeleteRecord(null); setSelected(null); setDetail(null); setCredentials(null); setNotice('')
      setPage(1); setRevision(value => value + 1)
    } catch (error) {
      if (alive.current) setDeleteError(candidateDeletionError(error))
    } finally { actionPending.current = false; if (alive.current) setBusy(false) }
  }
  const fields = [
    ['first_name', 'First name', 'text', 150], ['last_name', 'Last name', 'text', 150], ['candidate_id', 'Candidate ID', 'text', 64],
    ['email', 'Email address', 'email', 254], ['phone', 'Phone number', 'tel', 32], ['date_of_birth', 'Date of birth', 'date'],
  ]
  return <div className="candidate-management" dir={direction}>
    <header className="cm-header"><div><h1>{t('Candidates')}</h1><p>{t('Manage the people taking your assessments.')}</p></div><div className="cm-form-actions"><Button disabled={busy} onClick={() => setImportOpen(true)}>Upload Candidates</Button><Button variant="outline" disabled={busy} onClick={() => startForm()}>{t('Add candidate')}</Button></div></header>
    {importOpen && <CandidateImport institutionId={institutionId} onClose={() => setImportOpen(false)} onImported={count => { setImportOpen(false); setPage(1); setRevision(value => value + 1); setNotice(`${count} candidates imported.`) }} />}
    {notice.endsWith('candidates imported.') && <p role="status">{notice}</p>}
    <form className="cm-filters" onSubmit={event => { event.preventDefault(); setQuery(search.trim()); setPage(1) }}>
      <label><span className="sr-only">{t('Search by name, candidate ID or email')}</span><input className="form-control" type="search" maxLength={200} placeholder={t('Search by name, candidate ID or email')} value={search} onChange={event => setSearch(event.target.value)} /></label>
      <Button type="submit" variant="outline">{t('Search')}</Button>
      <label>{t('Status')}<select className="form-control" value={status} onChange={event => { setStatus(event.target.value); setPage(1) }}><option value="">{t('All statuses')}</option>{candidateStatuses.map(value => <option key={value} value={value}>{t(statusLabel(value))}</option>)}</select></label>
      {visible?.data && <span>{visible.data.count} {t('matching candidates')}</span>}
    </form>
    <div className={`cm-body${selected ? ' cm-body--detail' : ''}`}>
      <section className="cm-list" aria-label={t('Candidates')}>
        {!visible ? <p className="cm-state" role="status">{t('Loading candidates…')}</p> : visible.error ? <div className="cm-state" role="alert"><p>{t('We could not load candidates. Try again.')}</p><Button onClick={() => setRevision(value => value + 1)}>{t('Try again')}</Button></div> : <>
          <CandidateRoster rows={visible.data.results} t={t} onAdd={() => startForm()} onSelect={choose} filtered={Boolean(query || status)} busy={busy} />
          {visible.data.count > 0 && <nav className="cm-pagination" aria-label={t('Page')}><Button variant="outline" disabled={page <= 1} onClick={() => setPage(page - 1)}>{t('Previous')}</Button><span>{t('Page')} {page} {t('of')} {totalPages}</span><Button variant="outline" disabled={!visible.data.next} onClick={() => setPage(page + 1)}>{t('Next')}</Button></nav>}
        </>}
      </section>
      {selected && <section className="cm-detail" aria-label={t('Candidate details')}>
        <Button variant="outline" disabled={busy} onClick={() => choose(null)}>{t('Back to candidates')}</Button>
        {detail?.error ? <div role="alert"><p>{t('We could not complete this request. Please try again.')}</p><Button onClick={() => setRevision(value => value + 1)}>{t('Try again')}</Button></div> : !candidate ? <p role="status">{t('Loading candidates…')}</p> : <>
          <h2 tabIndex={-1} ref={detailHeading}><bdi>{candidate.first_name} {candidate.last_name}</bdi></h2><span className={`cm-status cm-status--${candidate.status}`}>{t(statusLabel(candidate.status))}</span>
          <dl>{[['Candidate ID', candidate.candidate_id], ['Email address', candidate.email], ['Phone number', candidate.phone], ['Date of birth', candidate.date_of_birth]].map(([name, value]) => <div key={name}><dt>{t(name)}</dt><dd><bdi>{value || t('Not provided')}</bdi></dd></div>)}</dl>
          <Button variant="outline" disabled={busy} onClick={() => startForm(candidate)}>{t('Edit candidate')}</Button>
          <section className="cm-portal"><h3>{t('Portal access')}</h3><p>{t(accessLabels[portalAccessState(candidate)])}</p>
            {candidate.portal_account ? <p><bdi>{candidate.portal_account.email}</bdi></p> : <>
              <p>{t('Email-based portal access requires a saved email and an active candidate.')}</p>
              {candidate.identity_locked && <p>{t('Account linkage cannot change after an examination attempt starts.')}</p>}
              {administrator ? <Button disabled={!candidate.email || candidate.status !== 'active' || candidate.identity_locked} loading={busy} onClick={enableAccess}>{t(busy ? 'Enabling portal access…' : 'Enable portal access')}</Button> : <p>{t('Only workspace administrators can enable portal access.')}</p>}
            </>}
          </section>
          <div className="cm-delete-section"><CandidateDeleteAction administrator={administrator} busy={busy} t={t} onClick={() => { setCredentials(null); setDeleteError(''); setDeleteRecord(candidate) }} /></div>
        </>}
        {notice && formRecord === null && <p className="cm-error" role="alert">{t(notice)}</p>}
      </section>}
    </div>
    {formRecord !== null && <Modal open canClose={!busy} onClose={closeForm} title={t(formRecord.id ? 'Edit candidate' : 'Add candidate')} closeLabel={t('Close dialog')} dir={direction}>
      <form className="cm-form" onSubmit={submit}>
        <fieldset disabled={busy}>{fields.map(([name, title, type, maxLength], index) => <label key={name} htmlFor={`candidate-${name}`}>
          <span>{t(title)}{index > 2 && <small> ({t('Optional')})</small>}</span>
          <input className="form-control" id={`candidate-${name}`} name={name} type={type} maxLength={maxLength} required={index < 3} autoFocus={index === 0} defaultValue={formRecord[name] || ''} readOnly={name === 'candidate_id' && (formRecord.identity_locked || (formRecord.id && !administrator))} aria-invalid={errors[name] || undefined} aria-describedby={errors[name] ? `candidate-${name}-error` : name === 'candidate_id' ? 'candidate-id-hint' : undefined} />
          {errors[name] && <small className="cm-error" id={`candidate-${name}-error`}>{t(name === 'candidate_id' ? 'Check this value. Candidate IDs must be unique within the workspace.' : 'Check this value.')}</small>}
          {name === 'candidate_id' && <small id="candidate-id-hint">{t(formRecord.identity_locked ? 'Identity is locked after an exam attempt starts.' : 'Use the identifier your organisation assigns. It must be unique within this workspace.')}</small>}
        </label>)}
          <label>{t('Status')}<select className="form-control" name="status" defaultValue={formRecord.status || 'active'} disabled={Boolean(formRecord.id && !administrator)} aria-invalid={errors.status || undefined} aria-describedby={errors.status ? 'candidate-status-error' : undefined}>{candidateStatuses.map(value => <option key={value} value={value}>{t(statusLabel(value))}</option>)}</select>{errors.status && <small id="candidate-status-error" className="cm-error">{t('Check this value.')}</small>}</label>
          {formRecord.id && !administrator && <input type="hidden" name="status" value={formRecord.status} />}
          <p className="cm-status-note">{t('Inactive and archived candidates cannot enter the Student Portal. Existing exam records are retained.')}</p>
        </fieldset>
        {notice && <p role="alert" className="cm-error">{t(notice)}</p>}
        <div className="cm-form-actions"><Button type="submit" loading={busy}>{t(busy ? 'Saving…' : formRecord.id ? 'Save changes' : 'Add candidate')}</Button><Button variant="outline" disabled={busy} onClick={closeForm}>{t('Cancel')}</Button></div>
      </form>
    </Modal>}
    {credentials && <Modal open onClose={() => setCredentials(null)} title={t('Initial access credentials')} closeLabel={t('Close dialog')} dir={direction}>
      <InitialCredentials credentials={credentials} t={t} />
      <Button onClick={() => setCredentials(null)}>{t('Dismiss credentials')}</Button>
    </Modal>}
    {deleteRecord && <Modal open canClose={!busy} onClose={closeDelete} title={t('Delete candidate?')} closeLabel={t('Close dialog')} dir={direction}>
      <CandidateDeleteConfirmation candidate={deleteRecord} busy={busy} error={deleteError} onConfirm={confirmDelete} onCancel={closeDelete} t={t} />
    </Modal>}
  </div>
}
