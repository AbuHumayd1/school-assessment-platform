import { useEffect, useRef, useState, useReducer } from 'react'
import { useLocation } from 'react-router-dom'
import Button from '../../components/common/Button.jsx'
import Modal from '../../components/common/Modal.jsx'
import { examRequest, examError, credentialState, pinDisclosureReducer, localDateValue } from '../../services/assessments.js'
import { staffApiFetch } from '../../services/api.js'
import { listCandidates } from '../../services/candidates.js'
import { useOwnerRead, ReadState, ExamPagination } from './exam-ui.jsx'

export function PinDisclosure({ disclosure, t, onDismiss }) {
  if (!disclosure) return null
  return <div className="exam-pin" role="status"><strong>{t('One-time PIN')}</strong><p>{t('Communicate this PIN securely before closing. It cannot be viewed again.')}</p><p><bdi>{disclosure.credential.candidate_name} &middot; {disclosure.credential.candidate_identifier}</bdi></p><label>{t('PIN')}<input className="form-control" readOnly value={disclosure.initial_pin} dir="ltr" autoComplete="off" /></label><Button variant="outline" onClick={onDismiss}>{t('Dismiss PIN')}</Button></div>
}
export function CredentialConfirmation({ action, credential, t, onConfirm, onCancel, busy, expires_at = '', onExpiryChange }) {
  return <><p><bdi>{credential.candidate_name} &middot; {credential.candidate_identifier}</bdi></p><p>{t(action === 'reset' ? 'Reset invalidates the previous PIN and active sessions.' : 'Revoke prevents access and invalidates active sessions.')}</p>{action === 'reset' && <label>{t('Expiry (local time)')}<input className="form-control" type="datetime-local" value={expires_at} onChange={event => onExpiryChange?.(event.target.value)} /><small>{t('Leave blank for no expiry.')}</small></label>}<div className="exam-actions"><Button loading={busy} onClick={onConfirm}>{t(action === 'reset' ? 'Reset PIN' : 'Revoke credential')}</Button><Button variant="outline" disabled={busy} onClick={onCancel}>{t('Cancel')}</Button></div></>
}
export default function ExamAccess({ institutionId, exam, t, direction, onUpdate }) {
  const [revision, setRevision] = useState(0)
  const [page, setPage] = useState(1)
  const [code, setCode] = useState('')
  const [enabled, setEnabled] = useState(false)
  const [search, setSearch] = useState('')
  const [candidateQuery, setCandidateQuery] = useState('')
  const [candidatePage, setCandidatePage] = useState(1)
  const [candidate, setCandidate] = useState('')
  const [expiry, setExpiry] = useState('')
  const [disclosure, dispatchDisclosure] = useReducer(pinDisclosureReducer, null)
  const location = useLocation()
  const navigation = useRef(location.key)
  navigation.current = location.key
  useEffect(() => { dispatchDisclosure({ type: 'navigation' }); setBusy(false); setConfirmation(null) }, [location.key])
  const [confirmation, setConfirmation] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  const configuration = useOwnerRead(`${institutionId}:${exam.id}:config:${exam.quick_access_configured}:${revision}`, signal => exam.quick_access_configured ? examRequest(institutionId, `${exam.id}/quick-access/`, { signal }) : Promise.resolve(null))
  useEffect(() => { setCode(configuration.data?.exam_code || ''); setEnabled(configuration.data?.enabled || false) }, [configuration.data])
  const credentials = useOwnerRead(`${institutionId}:${exam.id}:credentials:${exam.quick_access_configured}:${revision}:${page}`, signal => exam.quick_access_configured ? examRequest(institutionId, `${exam.id}/quick-access/credentials/`, { signal }, { page: String(page) }) : Promise.resolve({ results: [], count: 0 }))
  const candidates = useOwnerRead(`${institutionId}:${candidateQuery}:${candidatePage}`, signal => listCandidates(staffApiFetch, institutionId, { search: candidateQuery, status: 'active', page: candidatePage, signal }))
  async function mutate(path, body, method = 'POST', reveal = false) {
    const navigationKey = location.key
    setBusy(true); setError(''); dispatchDisclosure({ type: 'dismiss' })
    try {
      const result = await examRequest(institutionId, `${exam.id}/quick-access/${path}`, { method, body })
      if (!alive.current || navigation.current !== navigationKey) return
      if (reveal) dispatchDisclosure({ type: 'issued', disclosure: result })
      setConfirmation(null); setRevision(value => value + 1); onUpdate()
    } catch (failure) { if (alive.current && navigation.current === navigationKey) setError(examError(failure)) }
    finally { if (alive.current && navigation.current === navigationKey) setBusy(false) }
  }
  if (exam.candidate_access !== 'access_code') return <div className="exam-panel"><p>{t('Quick access requires access-code delivery.')}</p></div>
  return <div className="exam-page"><div className="exam-panel"><h2>{t('Quick Access')}</h2><p>{t('Credential validity is separate from the exam workflow and availability window.')}</p><ReadState state={configuration} t={t}><form className="exam-form" onSubmit={event => { event.preventDefault(); mutate('', { exam_code: code, enabled }, 'PUT') }}><label>{t('Exam code')}<input required maxLength={32} className="form-control" value={code} onChange={event => setCode(event.target.value)} /></label><label className="exam-checkbox"><input type="checkbox" checked={enabled} onChange={event => setEnabled(event.target.checked)} />{t('Enabled')}</label><Button type="submit" loading={busy}>{t('Save configuration')}</Button></form></ReadState></div>
    {error && <p role="alert" className="exam-error">{t(error)}</p>}
    <PinDisclosure disclosure={disclosure} t={t} onDismiss={() => dispatchDisclosure({ type: 'dismiss' })} />
    {exam.quick_access_configured && <><div className="exam-panel"><h2>{t('Generate credential')}</h2><form className="exam-actions" onSubmit={event => { event.preventDefault(); setCandidateQuery(search); setCandidatePage(1); setCandidate('') }}><label>{t('Find candidate')}<input className="form-control" value={search} onChange={event => setSearch(event.target.value)} /></label><Button type="submit" disabled={busy}>{t('Search')}</Button></form><ReadState state={candidates} t={t}>{candidates.data && <><form className="exam-form" onSubmit={event => { event.preventDefault(); mutate('credentials/', { candidate: Number(candidate), expires_at: expiry ? new Date(expiry).toISOString() : null }, 'POST', true) }}><label>{t('Candidate')}<select required className="form-control" value={candidate} onChange={event => setCandidate(event.target.value)}><option value="">{t('Select candidate')}</option>{candidates.data.results.map(row => <option key={row.id} value={row.id}>{row.first_name} {row.last_name} &middot; {row.candidate_id}</option>)}</select></label><label>{t('Expiry (local time)')}<input className="form-control" type="datetime-local" value={expiry} onChange={event => setExpiry(event.target.value)} /></label><Button type="submit" loading={busy}>{t('Generate credential')}</Button></form><ExamPagination page={candidatePage} count={candidates.data.count} onChange={value => { setCandidatePage(value); setCandidate('') }} t={t} /></>}</ReadState></div>
      <ReadState state={credentials} t={t}>{credentials.data && <div className="exam-panel"><h2>{t('Credentials')}</h2>{!credentials.data.results.length && <p>{t('No credentials issued')}</p>}<div className="exam-table-scroll"><table className="exam-table"><thead><tr>{['Candidate', 'Credential status', 'Candidate status', 'Expiry', 'Generated', 'Revoked', 'Actions'].map(text => <th key={text}>{t(text)}</th>)}</tr></thead><tbody>{credentials.data.results.map(row => <tr key={row.id}><td><bdi>{row.candidate_name}</bdi><small><bdi>{row.candidate_identifier}</bdi></small></td><td>{t(credentialState(row))}</td><td>{t(row.candidate_status)}</td><td>{row.expires_at ? new Date(row.expires_at).toLocaleString() : t('Not set')}</td><td>{row.generated_at ? new Date(row.generated_at).toLocaleString() : t('Not set')}</td><td>{row.revoked_at ? new Date(row.revoked_at).toLocaleString() : t('Not set')}</td><td><div className="exam-actions"><Button size="small" disabled={busy} variant="outline" onClick={() => { dispatchDisclosure({ type: 'dismiss' }); setError(''); setConfirmation({ action: 'reset', credential: row, expires_at: localDateValue(row.expires_at) }) }}>{t('Reset PIN')}</Button><Button size="small" disabled={busy} variant="outline" onClick={() => { dispatchDisclosure({ type: 'dismiss' }); setError(''); setConfirmation({ action: 'revoke', credential: row }) }}>{t('Revoke')}</Button></div></td></tr>)}</tbody></table></div><ExamPagination page={page} count={credentials.data.count} onChange={setPage} t={t} /></div>}</ReadState>
    </>}
    <Modal open={Boolean(confirmation)} title={t('Confirm action')} closeLabel={t('Close dialog')} canClose={!busy} dir={direction} onClose={() => setConfirmation(null)}>{confirmation && <CredentialConfirmation {...confirmation} t={t} busy={busy} onExpiryChange={value => setConfirmation(previous => ({ ...previous, expires_at: value }))} onCancel={() => setConfirmation(null)} onConfirm={() => mutate(`credentials/${confirmation.credential.candidate}/${confirmation.action}/`, confirmation.action === 'reset' ? { expires_at: confirmation.expires_at ? new Date(confirmation.expires_at).toISOString() : null } : {}, 'POST', confirmation.action === 'reset')} />}{error && <p role="alert" className="exam-error">{t(error)}</p>}</Modal>
  </div>
}
