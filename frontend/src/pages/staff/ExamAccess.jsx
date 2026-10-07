import { useEffect, useRef, useState, useReducer } from 'react'
import { Link, useLocation } from 'react-router-dom'
import Button from '../../components/common/Button.jsx'
import Modal from '../../components/common/Modal.jsx'
import { examRequest, examError, credentialState, pinDisclosureReducer, localDateValue } from '../../services/assessments.js'
import { useOwnerRead, ReadState, ExamPagination } from './exam-ui.jsx'

export function PinDisclosure({ disclosure, t, onDismiss }) {
  if (!disclosure) return null
  return <div className="exam-pin" role="status"><strong>{t('One-time PIN')}</strong><p>{t('Communicate this PIN securely before closing. It cannot be viewed again.')}</p><p><bdi>{disclosure.credential.candidate_name} &middot; {disclosure.credential.candidate_identifier}</bdi></p><label>{t('PIN')}<input className="form-control" readOnly value={disclosure.initial_pin} dir="ltr" autoComplete="off" /></label><Button variant="outline" onClick={onDismiss}>{t('Dismiss PIN')}</Button></div>
}
export function CredentialConfirmation({ action, credential, t, onConfirm, onCancel, busy, expires_at = '', onExpiryChange }) {
  return <><p><bdi>{credential.candidate_name} &middot; {credential.candidate_identifier}</bdi></p><p>{t(action === 'reset' ? 'Reset invalidates the previous PIN and active sessions.' : 'Revoke prevents access and invalidates active sessions.')}</p>{action === 'reset' && <label>{t('Expiry (local time)')}<input className="form-control" type="datetime-local" value={expires_at} onChange={event => onExpiryChange?.(event.target.value)} /><small>{t('Leave blank for no expiry.')}</small></label>}<div className="exam-actions"><Button loading={busy} onClick={onConfirm}>{t(action === 'reset' ? 'Reset PIN' : 'Revoke credential')}</Button><Button variant="outline" disabled={busy} onClick={onCancel}>{t('Cancel')}</Button></div></>
}

export function downloadCredentialSheet(blob) {
  const url = URL.createObjectURL(blob)
  try {
    const link = document.createElement('a')
    link.href = url; link.download = 'quick-exam-credentials.csv'
    document.body.appendChild(link)
    try { link.click() } finally { link.remove() }
  } finally { setTimeout(() => URL.revokeObjectURL(url), 1000) }
}
export default function ExamAccess({ institutionId, exam, t, direction, onUpdate }) {
  const [revision, setRevision] = useState(0)
  const [page, setPage] = useState(1)
  const [code, setCode] = useState('')
  const [enabled, setEnabled] = useState(true)
  const quick = exam.delivery_mode === 'quick_exam' || exam.candidate_access === 'access_code' || exam.quick_access_configured
  const [sheet, setSheet] = useState(null)
  const [disclosure, dispatchDisclosure] = useReducer(pinDisclosureReducer, null)
  const [confirmation, setConfirmation] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(false)
  const alive = useRef(true)
  const location = useLocation()
  const scopeKey = `${institutionId}:${exam.id}:${location.key}`
  const navigation = useRef(scopeKey)
  navigation.current = scopeKey
  useEffect(() => {
    alive.current = true; pending.current = false; setBusy(false); dispatchDisclosure({ type: 'navigation' }); setSheet(null); setConfirmation(null); setError('')
    return () => { alive.current = false }
  }, [scopeKey])
  const editable = exam.status === 'draft' && !exam.has_attempt_history
  const specific = ['specific_candidates', 'access_code'].includes(exam.candidate_access)
  const configuration = useOwnerRead(`${institutionId}:${exam.id}:config:${exam.quick_access_configured}:${revision}`, signal => exam.quick_access_configured ? examRequest(institutionId, `${exam.id}/quick-access/`, { signal }) : Promise.resolve(null))
  useEffect(() => { setCode(configuration.data?.exam_code || ''); setEnabled(configuration.data?.enabled ?? true) }, [configuration.data])
  const credentials = useOwnerRead(`${institutionId}:${exam.id}:credentials:${exam.quick_access_configured}:${revision}:${page}`, signal => exam.quick_access_configured ? examRequest(institutionId, `${exam.id}/quick-access/credentials/`, { signal }, { page: String(page) }) : Promise.resolve({ results: [], count: 0 }))
  const eligibility = useOwnerRead(`${institutionId}:${exam.id}:access-eligibility:${revision}`, signal => examRequest(institutionId, `${exam.id}/eligibility/`, { signal }))
  const assigned = credentials.data?.assigned_count ?? eligibility.data?.eligible_count ?? eligibility.data?.count ?? 0
  const missing = credentials.data?.generatable_count ?? 0
  const currentSheet = sheet?.key === scopeKey ? sheet.blob : null
  async function mutate(path, body, method = 'POST', reveal = false) {
    if (pending.current) return
    const key = scopeKey
    pending.current = key; setBusy(true); setError(''); dispatchDisclosure({ type: 'dismiss' })
    try {
      const result = await examRequest(institutionId, `${exam.id}/quick-access/${path}`, { method, body })
      if (!alive.current || navigation.current !== key) return
      if (reveal) dispatchDisclosure({ type: 'issued', disclosure: result })
      setConfirmation(null); setRevision(value => value + 1); onUpdate()
    } catch (failure) { if (alive.current && navigation.current === key) setError(examError(failure)) }
    finally { if (pending.current === key) pending.current = false; if (alive.current && navigation.current === key) setBusy(false) }
  }
  async function generate() {
    if (pending.current || !missing || currentSheet) return
    const key = scopeKey
    pending.current = key; setBusy(true); setError(''); dispatchDisclosure({ type: 'dismiss' })
    try {
      const blob = await examRequest(institutionId, `${exam.id}/quick-access/credentials/generate-sheet/`, { method: 'POST', body: { expected_count: missing }, responseType: 'blob' })
      if (!alive.current || navigation.current !== key) return
      setSheet({ key, blob }); setRevision(value => value + 1); onUpdate()
      try { downloadCredentialSheet(blob) } catch { setError('Download did not start. Use Download credential sheet to save the generated PINs.') }
    } catch (failure) { if (alive.current && navigation.current === key) setError(examError(failure)) }
    finally { if (pending.current === key) pending.current = false; if (alive.current && navigation.current === key) setBusy(false) }
  }
  return <div className="exam-page">
    <section className="exam-panel"><h2>{t('Access')}</h2>
      <h3>{t(quick ? 'Quick Exam' : 'Through their account')}</h3>
      <p>{t(quick ? 'Candidates use Exam Code + Candidate ID + PIN.' : 'Candidates sign in using their platform account.')}</p>
      {quick && <p>{t('Quick Exam candidates do not need platform accounts.')}</p>}
      <p>{t('Delivery method is fixed when the exam is created.')}</p>
      <ReadState state={eligibility} t={t}>{eligibility.data && <p>{t('Candidate eligibility')}: {assigned} {t(specific ? 'specific candidates assigned' : 'group candidates eligible')}</p>}</ReadState>
      <Link to="?section=candidates">{t('Manage Candidates')}</Link>
    </section>
    {quick && specific && <section className="exam-panel"><h2>{t('Quick Exam access')}</h2>
      {!exam.quick_access_configured && <p>{t('Save the Exam Code before generating credentials.')}</p>}
      <ReadState state={configuration} t={t}>
        {configuration.data && <p>{t('Exam Code')}: <bdi>{configuration.data.exam_code}</bdi></p>}
        <form className="exam-form" onSubmit={event => { event.preventDefault(); mutate('', { exam_code: code, enabled }, 'PUT') }}>
          <label>{t('Exam code')}<input required maxLength={32} disabled={busy || !editable} className="form-control" value={code} onChange={event => setCode(event.target.value)} /></label>
          <label className="exam-checkbox"><input type="checkbox" disabled={busy} checked={enabled} onChange={event => setEnabled(event.target.checked)} />{t('Enabled')}</label>
          <Button type="submit" loading={busy} disabled={busy || (!editable && !exam.quick_access_configured)}>{t('Save configuration')}</Button>
        </form>
      </ReadState>
      <p>{t('Credential validity is separate from the exam workflow and availability window.')}</p>
    </section>}
    {error && <p role="alert" className="exam-error">{t(error)}</p>}
    <PinDisclosure disclosure={disclosure} t={t} onDismiss={() => dispatchDisclosure({ type: 'dismiss' })} />
    {currentSheet && <section className="exam-pin" role="status"><p>{t('Save this sheet now. PINs cannot be downloaded again after leaving this page.')}</p>
      <Button onClick={() => downloadCredentialSheet(currentSheet)}>{t('Download credential sheet')}</Button>
      <Button variant="outline" onClick={() => setSheet(null)}>{t('Dismiss credential sheet')}</Button>
    </section>}
    {quick && <ReadState state={credentials} t={t}>{credentials.data && <>
      <section className="exam-panel"><h2>{t('Generate credentials')}</h2>
        <p>{assigned} {t('candidates assigned')}</p><p>{credentials.data.generated_count ?? 0} {t('credentials generated')}</p>
        <p>{credentials.data.needed_count ?? assigned} {t('candidates need credentials')}</p>
        {credentials.data.reset_needed_count > 0 && <p>{credentials.data.reset_needed_count} {t('existing credentials need an explicit Reset PIN.')}</p>}
        <Button loading={busy} disabled={busy || !editable || !exam.quick_access_configured || !configuration.data?.enabled || !missing || Boolean(currentSheet)} onClick={generate}>{t('Generate credentials for')} {missing} {t('candidates')}</Button>
      </section>
      <section className="exam-panel"><h2>{t('Credentials')}</h2>{!credentials.data.results.length && <p>{t('No credentials issued')}</p>}
        <div className="exam-table-scroll"><table className="exam-table"><thead><tr>{['Candidate', 'Credential status', 'Candidate status', 'Expiry', 'Generated', 'Revoked', 'Actions'].map(text => <th key={text}>{t(text)}</th>)}</tr></thead><tbody>{credentials.data.results.map(row => <tr key={row.id}><td><bdi>{row.candidate_name}</bdi><small><bdi>{row.candidate_identifier}</bdi></small></td><td>{t(credentialState(row))}</td><td>{t(row.candidate_status)}</td><td>{row.expires_at ? new Date(row.expires_at).toLocaleString() : t('Not set')}</td><td>{row.generated_at ? new Date(row.generated_at).toLocaleString() : t('Not set')}</td><td>{row.revoked_at ? new Date(row.revoked_at).toLocaleString() : t('Not set')}</td><td><div className="exam-actions"><Button size="small" disabled={busy} variant="outline" onClick={() => { dispatchDisclosure({ type: 'dismiss' }); setError(''); setConfirmation({ action: 'reset', credential: row, expires_at: localDateValue(row.expires_at) }) }}>{t('Reset PIN')}</Button><Button size="small" disabled={busy} variant="outline" onClick={() => { dispatchDisclosure({ type: 'dismiss' }); setError(''); setConfirmation({ action: 'revoke', credential: row }) }}>{t('Revoke')}</Button></div></td></tr>)}</tbody></table></div>
        <ExamPagination page={page} count={credentials.data.count} onChange={setPage} t={t} />
      </section>
    </>}</ReadState>}
    <Modal open={Boolean(confirmation)} title={t('Confirm action')} closeLabel={t('Close dialog')} canClose={!busy} dir={direction} onClose={() => setConfirmation(null)}>{confirmation && <CredentialConfirmation {...confirmation} t={t} busy={busy} onExpiryChange={value => setConfirmation(previous => ({ ...previous, expires_at: value }))} onCancel={() => setConfirmation(null)} onConfirm={() => mutate(`credentials/${confirmation.credential.candidate}/${confirmation.action}/`, confirmation.action === 'reset' ? { expires_at: confirmation.expires_at ? new Date(confirmation.expires_at).toISOString() : null } : {}, 'POST', confirmation.action === 'reset')} />}{error && <p role="alert" className="exam-error">{t(error)}</p>}</Modal>
  </div>
}
