import { useEffect, useRef, useState } from 'react'
import { Link } from 'react-router-dom'
import Button from '../../components/common/Button.jsx'
import Modal from '../../components/common/Modal.jsx'
import QuestionMedia from '../../components/common/QuestionMedia.jsx'
import { examRequest, examError } from '../../services/assessments.js'
import { resultAvailabilityLabel } from '../../services/resultAvailability.js'
import { useOwnerRead, ReadState, ExamPagination } from './exam-ui.jsx'

function useSetupScope() {
  const alive = useRef(true)
  useEffect(() => { alive.current = true; return () => { alive.current = false } }, [])
  return alive
}

export function SelectableItems({ rows, selected, onSelect, t, kind }) {
  return <div className="exam-selectable">{rows.map(row => <label key={row.id} className="exam-selectable-item"><input type="checkbox" disabled={row.attached || row.assigned} checked={selected.includes(row.id)} onChange={() => onSelect(row.id)} /><span><bdi>{kind === 'questions' ? row.text : `${row.candidate_id} — ${row.name}`}</bdi><small>{kind === 'questions' ? <>{t(row.question_type)} &middot; {row.marks || '1.00'} {t('marks')}{row.topic_name && <> · <bdi>{row.topic_name}</bdi></>}</> : row.email && <bdi>{row.email}</bdi>}</small>{(row.attached || row.assigned) && <small>{t(kind === 'questions' ? 'Already attached' : 'Already assigned')}</small>}</span></label>)}</div>
}

export function AddItems({ institutionId, exam, kind, t, direction, onAdded, onClose }) {
  const alive = useSetupScope()
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState([])
  const [allSelection, setAllSelection] = useState(null)
  const pending = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const questions = kind === 'questions'
  const state = useOwnerRead(`${institutionId}:${exam.id}:${kind}:${page}:${query}`, signal => examRequest(institutionId, questions ? 'question-options/' : `${exam.id}/candidate-assignments/`, { signal }, { page: String(page), search: query, ...(questions ? { subject: String(exam.subject), assessment: String(exam.id) } : { status: 'active' }) }))
  const selectionCount = allSelection ? allSelection.count : selected.length
  async function add() {
    if (pending.current || !selectionCount) return
    pending.current = true
    setBusy(true); setError('')
    const body = allSelection ? { select_all: true, search: allSelection.query, expected_count: allSelection.count, ...(!questions ? { status: 'active' } : {}) } : { [questions ? 'questions' : 'candidates']: selected }
    try { await examRequest(institutionId, `${exam.id}/${questions ? 'questions/add/' : 'candidate-assignments/'}`, { method: 'POST', body }); if (alive.current) { onAdded(); onClose() } }
    catch (failure) { if (alive.current) setError(examError(failure)) }
    finally { pending.current = false; if (alive.current) setBusy(false) }
  }
  return <Modal open title={t(questions ? 'Add Questions' : 'Add Candidates')} closeLabel={t('Close dialog')} onClose={onClose} canClose={!busy} dir={direction}>
    <form className="exam-actions" onSubmit={event => { event.preventDefault(); if (busy) return; setQuery(search.trim()); setPage(1); setAllSelection(null); setSelected([]) }}><label>{t(questions ? 'Search questions' : 'Search by Candidate ID or name')}<input className="form-control" maxLength={200} disabled={busy} value={search} onChange={event => setSearch(event.target.value)} /></label><Button type="submit" disabled={busy}>{t('Search')}</Button></form>
    {!questions && <p>{t('Active candidates only')}</p>}
    <ReadState state={state} t={t}>{state.data && <>
      <div className="exam-actions"><Button variant="outline" disabled={busy || !Number.isInteger(state.data.available_count) || state.data.available_count < 1 || state.data.available_count > 1000} onClick={() => { setSelected([]); setAllSelection({ query, count: state.data.available_count }) }}>{t('Select all')}</Button><Button variant="outline" disabled={busy || !selectionCount} onClick={() => { setSelected([]); setAllSelection(null) }}>{t('Clear selection')}</Button></div>
      {!state.data.count ? <div><p>{t(query ? 'No matching items found. Clear the search to see all available items.' : questions ? 'No approved questions are available for this subject.' : 'No candidates found.')}</p>{questions && <><p>{t('Questions must be approved before they can be added to an exam.')}</p><Link to="/app/questions">{t('Go to Question Bank')}</Link></>}</div> : <><fieldset disabled={busy || Boolean(allSelection)}><SelectableItems rows={state.data.results} selected={allSelection ? state.data.results.filter(row => !row.attached && !row.assigned).map(row => row.id) : selected} onSelect={id => setSelected(previous => previous.includes(id) ? previous.filter(value => value !== id) : [...previous, id])} kind={kind} t={t} /></fieldset><ExamPagination page={page} count={state.data.count} onChange={value => { if (!busy) setPage(value) }} t={t} /></>}
    </>}</ReadState>
    <p role="status">{selectionCount} {t(questions ? 'questions selected' : 'candidates selected')}{allSelection && <> · {t(questions ? 'All matching available questions across all pages are selected. Clear selection to choose individual questions.' : 'All matching available candidates across all pages are selected. Clear selection to choose individual candidates.')}</>}</p>
    {error && <p role="alert" className="exam-error">{t(error)}</p>}<div className="exam-actions">{allSelection ? <Button disabled={!selectionCount || busy} loading={busy} onClick={add}>{t(questions ? 'Add' : 'Assign')} {selectionCount} {t(questions ? 'questions' : 'candidates')}</Button> : <Button disabled={!selectionCount || busy} loading={busy} onClick={add}>{t(questions ? 'Add selected questions' : 'Assign selected candidates')} ({selectionCount})</Button>}<Button variant="outline" disabled={busy} onClick={onClose}>{t('Cancel')}</Button></div>
  </Modal>
}

export function AttachedQuestionEditor({ row, editable, busy, t, onSave, onRemove, selected, onSelect, selectionDisabled }) {
  const [order, setOrder] = useState(row.order)
  const [marks, setMarks] = useState(row.marks)
  const [inspect, setInspect] = useState(false)
  return <article className="exam-question"><h3>{editable && onSelect && <input type="checkbox" aria-label={`${t('Select question')} ${row.order}`} checked={selected} disabled={busy || selectionDisabled} onChange={() => onSelect(row.id)} />} {t('Question')} {row.order} · {row.marks} {t('marks')}</h3><p><bdi>{row.question.text}</bdi></p><p>{t(row.question.question_type)} · {t(row.question.status)}</p><Button variant="outline" onClick={() => setInspect(value => !value)}>{t('View question')}</Button>{inspect && <><QuestionMedia media={row.question.media} /><ol>{row.question.options.map(option => <li key={option.id}><bdi>{option.text}</bdi>{option.is_correct && <> · {t('Correct answer')}</>}</li>)}</ol><p><bdi>{row.question.explanation}</bdi></p></>}{editable && <form className="exam-actions" onSubmit={event => { event.preventDefault(); onSave(row.id, { order: Number(order), marks }) }}><label>{t('Order')}<input className="form-control" type="number" min="1" required value={order} onChange={event => setOrder(event.target.value)} /></label><label>{t('Marks')}<input className="form-control" type="number" min=".01" step=".01" required value={marks} onChange={event => setMarks(event.target.value)} /></label><Button type="submit" disabled={busy}>{t('Update question')}</Button><Button variant="outline" disabled={busy} onClick={() => onRemove(row.id)}>{t('Remove question')}</Button></form>}</article>
}

export function QuestionsSetup({ institutionId, exam, editable, t, direction, onUpdate }) {
  const alive = useSetupScope()
  const [revision, setRevision] = useState(0)
  const [open, setOpen] = useState(false)
  const [page, setPage] = useState(1)
  const [search, setSearch] = useState('')
  const [query, setQuery] = useState('')
  const [selected, setSelected] = useState([])
  const [allSelection, setAllSelection] = useState(null)
  const [confirmation, setConfirmation] = useState(null)
  const pending = useRef(false)
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const state = useOwnerRead(`${institutionId}:${exam.id}:questions:${revision}:${page}:${query}`, signal => examRequest(institutionId, `${exam.id}/questions/remove/`, { signal }, { page: String(page), search: query }))
  const selectionCount = allSelection ? allSelection.count : selected.length
  const clear = () => { setSelected([]); setAllSelection(null) }
  const refresh = () => { clear(); setPage(1); setRevision(value => value + 1); onUpdate() }
  async function mutate(id, method, body) {
    if (pending.current || !editable) return
    if (method === 'DELETE' && !window.confirm(t('Remove this question from this exam only? It will remain in the Question Bank.'))) return
    pending.current = true; setBusy(true); setError('')
    try { await examRequest(institutionId, `${exam.id}/questions/${id}/`, { method, body }); if (alive.current) refresh() }
    catch (failure) { if (alive.current) setError(examError(failure)) }
    finally { pending.current = false; if (alive.current) setBusy(false) }
  }
  async function removeSelected() {
    if (pending.current || !editable || !confirmation) return
    pending.current = true; setBusy(true); setError('')
    try {
      await examRequest(institutionId, `${exam.id}/questions/remove/`, { method: 'POST', body: confirmation.body })
      if (alive.current) { setConfirmation(null); refresh() }
    } catch (failure) { if (alive.current) setError(examError(failure)) }
    finally { pending.current = false; if (alive.current) setBusy(false) }
  }
  const blocked = busy || Boolean(confirmation)
  return <section className="exam-panel"><h2>{t('Questions')}</h2><p>{exam.question_count} {t('questions')} &middot; {exam.total_marks} {t('marks')}</p>
    {editable && <Button disabled={blocked} onClick={() => setOpen(true)}>{t('Add Questions')}</Button>}
    {exam.question_count > 0 && <form className="exam-actions" onSubmit={event => { event.preventDefault(); if (blocked) return; setQuery(search.trim()); setPage(1); clear(); setError('') }}><label>{t('Search attached questions')}<input className="form-control" maxLength={200} disabled={blocked} value={search} onChange={event => setSearch(event.target.value)} /></label><Button type="submit" disabled={blocked}>{t('Search')}</Button></form>}
    {error && !confirmation && <p role="alert" className="exam-error">{t(error)}</p>}
    <ReadState state={state} t={t}>{state.data && <>
      {editable && state.data.count > 0 && <div className="exam-actions"><Button variant="outline" disabled={blocked || state.loading || state.data.count > 1000} onClick={() => { setSelected([]); setAllSelection({ query, count: state.data.count }) }}>{t('Select all matching')}</Button></div>}
      {editable && <div className="exam-actions"><p role="status">{selectionCount} {t('questions selected')}{allSelection && <> &middot; {t('All matching attached questions across all pages are selected.')}</>}</p>{selectionCount > 0 && <><Button variant="outline" disabled={blocked} onClick={clear}>{t('Clear selection')}</Button><Button disabled={blocked} onClick={() => { setError(''); setConfirmation({ count: selectionCount, body: allSelection ? { select_all: true, search: allSelection.query, expected_count: allSelection.count } : { attachments: [...selected] } }) }}>{t('Remove selected questions')}</Button></>}</div>}
      {!state.data.count && <p>{t(query ? 'No matching attached questions. Clear the search to see all attached questions.' : 'No questions attached')}</p>}
      {state.data.results.map(row => <AttachedQuestionEditor key={`${row.id}:${revision}`} row={row} editable={editable} busy={blocked} t={t} selected={Boolean(allSelection) || selected.includes(row.id)} selectionDisabled={Boolean(allSelection)} onSelect={id => setSelected(previous => previous.includes(id) ? previous.filter(value => value !== id) : [...previous, id])} onSave={(id, body) => mutate(id, 'PATCH', body)} onRemove={id => mutate(id, 'DELETE')} />)}
      {state.data.count > 0 && <ExamPagination page={page} count={state.data.count} onChange={value => { if (!blocked) setPage(value) }} t={t} />}
    </>}</ReadState>
    {open && <AddItems institutionId={institutionId} exam={exam} kind="questions" t={t} direction={direction} onAdded={refresh} onClose={() => setOpen(false)} />}
    {confirmation && <Modal open title={t('Remove selected questions')} closeLabel={t('Close dialog')} canClose={!busy} dir={direction} onClose={() => { if (!busy) setConfirmation(null) }}>
      <p><strong><bdi>{exam.title}</bdi></strong></p><p>{confirmation.count} {t('questions selected')}</p>
      <p>{t('Remove these questions from this exam only? They will remain in the Question Bank.')}</p>
      {error && <p role="alert" className="exam-error">{t(error)}</p>}
      <div className="exam-actions"><Button disabled={busy} loading={busy} onClick={removeSelected}>{t('Confirm removal')}</Button><Button variant="outline" disabled={busy} onClick={() => setConfirmation(null)}>{t('Cancel')}</Button></div>
    </Modal>}
  </section>
}

export function CandidateRows({ rows, editable, specific, busy, t, onRemove }) {
  return <div className="exam-selectable">{rows.map(row => <article className="exam-selectable-item" key={row.id}><div><strong><bdi>{row.candidate_id}</bdi></strong><p><bdi>{row.name}</bdi></p>{row.email && <p><bdi>{row.email}</bdi></p>}<p>{t(row.status)}</p>{row.has_participated && <p>{t('This candidate has participated and cannot be removed from the exam.')}</p>}</div>{editable && specific && <Button variant="outline" disabled={busy || row.has_participated} onClick={() => onRemove(row.id)}>{t('Remove candidate')}</Button>}</article>)}</div>
}

export function CandidatesSetup({ institutionId, exam, editable, t, direction, onUpdate }) {
  const alive = useSetupScope()
  const [page, setPage] = useState(1)
  const [revision, setRevision] = useState(0)
  const [open, setOpen] = useState(false)
  const [strategy, setStrategy] = useState(exam.candidate_access === 'access_code' ? 'specific_candidates' : exam.candidate_access)
  const [group, setGroup] = useState(exam.group || '')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')
  const state = useOwnerRead(`${institutionId}:${exam.id}:candidates:${page}:${revision}:${exam.candidate_access}:${exam.group}`, signal => examRequest(institutionId, `${exam.id}/eligibility/`, { signal }, { page: String(page) }))
  const options = useOwnerRead(`${institutionId}:setup-options`, signal => examRequest(institutionId, 'form-options/', { signal }))
  const refresh = () => { setRevision(value => value + 1); onUpdate() }
  async function mutate(path, method, body) {
    setBusy(true); setError('')
    try { await examRequest(institutionId, `${exam.id}/${path}`, { method, body }); if (alive.current) refresh() }
    catch (failure) { if (alive.current) setError(examError(failure)) }
    finally { if (alive.current) setBusy(false) }
  }
  const specific = ['specific_candidates', 'access_code'].includes(exam.candidate_access)
  return <section className="exam-panel"><h2>{t('Candidates')}</h2><p>{t('Who should take this exam?')}</p>{<><p>{t(specific ? 'Specific Candidates' : 'Group / Cohort')}{!specific && <>: <bdi>{exam.group_name || t('No group assigned')}</bdi></>}</p>{editable && <ReadState state={options} t={t}>{options.data && <form className="exam-form" onSubmit={event => { event.preventDefault(); mutate('', 'PATCH', { candidate_access: exam.candidate_access === 'access_code' && strategy === 'specific_candidates' ? 'access_code' : strategy, group: strategy === 'assigned_group' ? Number(group) : null }) }}><label>{t('Candidate eligibility')}<select className="form-control" value={strategy} onChange={event => setStrategy(event.target.value)}><option value="specific_candidates">{t('Specific Candidates')}</option><option value="assigned_group" disabled={exam.quick_access_configured || exam.candidate_access === 'access_code'}>{t('Group / Cohort')}</option></select></label>{strategy === 'assigned_group' && <label>{t('Group / Cohort')}<select className="form-control" required value={group} onChange={event => setGroup(event.target.value)}><option value="">{t('Select group')}</option>{options.data.groups.map(row => <option key={row.id} value={row.id}>{row.name}</option>)}</select></label>}<Button type="submit" loading={busy}>{t('Save eligibility')}</Button></form>}</ReadState>}{specific && editable && <Button onClick={() => setOpen(true)}>{t('Add Candidates')}</Button>}<p>{t(specific ? 'Only directly assigned active candidates are eligible.' : 'Active candidates with effective group membership are shown.')}</p></>}{error && <p role="alert" className="exam-error">{t(error)}</p>}<ReadState state={state} t={t}>{state.data && <><p>{state.data.count} {t('candidates')}</p>{!state.data.count && <p>{t('No candidates assigned')}</p>}<CandidateRows rows={state.data.results} editable={editable} specific={specific} busy={busy} t={t} onRemove={id => { if (window.confirm(t('Remove this candidate from the exam?'))) mutate(`candidate-assignments/${id}/`, 'DELETE') }} /><ExamPagination page={page} count={state.data.count} onChange={setPage} t={t} /></>}</ReadState>{open && <AddItems institutionId={institutionId} exam={exam} kind="candidates" t={t} direction={direction} onAdded={refresh} onClose={() => setOpen(false)} />}</section>
}

export function SetupReadiness({ institutionId, exam, administrator, t }) {
  const state = useOwnerRead(`${institutionId}:${exam.id}:readiness:${exam.updated_at}`, signal => examRequest(institutionId, `${exam.id}/eligibility/`, { signal }))
  const eligibleCount = state.data?.eligible_count ?? state.data?.count
  const access = exam.candidate_access === 'access_code' ? exam.quick_access_configured : ['assigned_group', 'specific_candidates'].includes(exam.candidate_access)
  return <section className="exam-panel"><h2>{t('Exam setup')}</h2><ul><li>{exam.title && exam.subject ? '✓' : '!'} {t('Configuration')}</li><li>{exam.question_count ? '✓' : '!'} {exam.question_count} {t('questions')}{!exam.question_count && <> · {t('No questions added')}</>}</li><li>{state.data ? (eligibleCount ? '✓' : '!') : '…'} {state.data ? `${eligibleCount} ${t('candidates')}` : t('Loading…')}{eligibleCount === 0 && <> · {t('No candidates assigned')}</>}</li><li>{access ? '✓' : '!'} {t(access ? 'Candidate access configured' : 'No access method configured')}</li>{exam.candidate_access === 'assigned_group' && !exam.group && <li>! {t('Assign a group before scheduling this exam.')}</li>}<li>{exam.start_at && exam.end_at ? '✓' : '!'} {t(exam.start_at && exam.end_at ? 'Schedule configured' : 'No schedule')}</li><li>✓ {t('Result availability')}: {t(resultAvailabilityLabel(exam))}</li></ul>{state.error && <p role="alert">{t('Candidate readiness could not be loaded.')} <Button onClick={state.retry}>{t('Retry')}</Button></p>}<div className="exam-actions"><Link to="?section=questions">{t('Manage Questions')}</Link><Link to="?section=candidates">{t('Manage Candidates')}</Link>{administrator && <Link to="?section=access">{t('Review Access')}</Link>}</div></section>
}
