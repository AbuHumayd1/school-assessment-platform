import { useEffect, useRef, useState } from 'react'
import { staffApiFetch } from '../../services/api.js'
import Button from '../../components/common/Button.jsx'
import Modal from '../../components/common/Modal.jsx'

export const candidateTemplate = 'first_name,last_name,candidate_id,email\r\nAmina,Example,,\r\n'

export function CandidateImportPreview({ preview }) {
  return <>
    <p>{preview.count} candidates. No records have been created.</p>
    {preview.errors.length > 0 && <div role="alert"><p>Correct these rows and upload again:</p><ul>{preview.errors.map(row =>
      <li key={row.row}>Row {row.row}: {Object.entries(row.errors).map(([field, messages]) => `${field}: ${[].concat(messages).join(' ')}`).join('; ')}</li>)}</ul></div>}
    <div style={{ overflow: 'auto', maxHeight: '320px' }}><table><thead><tr><th>Row</th><th>Name</th><th>Candidate ID</th><th>Email</th></tr></thead>
      <tbody>{preview.rows.map(row => <tr key={row.row}><td>{row.row}</td><td>{row.first_name} {row.last_name}</td><td>{row.candidate_id}</td><td>{row.email || 'Not provided'}</td></tr>)}</tbody></table></div>
  </>
}

export default function CandidateImport({ institutionId, onClose, onImported }) {
  const [preview, setPreview] = useState(null)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const pending = useRef(false)
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  async function upload(event) {
    event.preventDefault()
    if (pending.current) return
    const body = new FormData(event.currentTarget)
    pending.current = true; setBusy(true); setError(''); setPreview(null)
    try {
      const result = await staffApiFetch(`candidates/import-preview/?institution=${institutionId}`, { method: 'POST', body })
      if (alive.current) setPreview(result)
    } catch (failure) {
      if (alive.current) setError([].concat(failure.data?.file || failure.data?.detail || 'Upload failed. Try again.').join(' '))
    } finally { pending.current = false; if (alive.current) setBusy(false) }
  }
  async function confirm() {
    if (pending.current || !preview?.token) return
    pending.current = true; setBusy(true); setError('')
    try {
      const result = await staffApiFetch(`candidates/import-confirm/?institution=${institutionId}`, { method: 'POST', body: { token: preview.token } })
      if (alive.current) onImported(result.created_count)
    } catch (failure) {
      if (alive.current) {
        setError([].concat(failure.data?.detail || failure.data?.token || 'Import failed. No candidates created. Upload again.').join(' '))
        if (failure.data?.errors) setPreview(value => ({ ...value, errors: failure.data.errors, token: null }))
      }
    } finally { pending.current = false; if (alive.current) setBusy(false) }
  }
  return <Modal open title="Upload Candidates" canClose={!busy} onClose={onClose}>
    <p>CSV (UTF-8) or XLSX with one worksheet, up to 1000 rows / 2 MB. Use first_name and last_name, or full_name. Candidate ID and email are optional. Keep IDs as text to preserve leading zeros.</p>
    <p>Missing IDs are generated during preview. Import creates candidate records; accounts and exam credentials are created separately.</p>
    <a className="button button--outline" download="candidate-template.csv" href={`data:text/csv;charset=utf-8,${encodeURIComponent(candidateTemplate)}`}>Download CSV template</a>
    <form onSubmit={upload}><label>Candidate file<input className="form-control" name="file" type="file" accept=".csv,.xlsx" required disabled={busy} /></label>
      <Button type="submit" loading={busy}>Parse and preview</Button></form>
    {error && <p role="alert">{error}</p>}
    {preview && <CandidateImportPreview preview={preview} />}
    <div className="cm-form-actions">{preview?.token && <Button loading={busy} onClick={confirm}>Confirm import</Button>}<Button variant="outline" disabled={busy} onClick={onClose}>Cancel</Button></div>
  </Modal>
}
