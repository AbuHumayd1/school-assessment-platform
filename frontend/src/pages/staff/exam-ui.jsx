import { useEffect, useState } from 'react'
import { useLanguageMode } from '../../context/LanguageModeContext.jsx'
import Button from '../../components/common/Button.jsx'
import { createOwnerScope } from '../../services/assessments.js'
import { examCopy } from './exam-copy.js'
import './exams.css'

export function useExamCopy() {
  const { label, direction } = useLanguageMode()
  return { t: text => {
    const count = text.match(/^(Question|questions) (\d+)$|^(\d+) questions$/)
    const arabic = count ? `${count[1] === 'Question' ? 'السؤال' : 'الأسئلة'} ${count[2] || count[3]}` : examCopy[text] || text
    const english = text.includes('_') ? text.replaceAll('_', ' ').replace(/^./, value => value.toUpperCase()) : text.replace(/^./, value => value.toUpperCase())
    const actions = { 'submit-review': 'Submit for Review', 'request-changes': 'Request Changes', approve: 'Approve', schedule: 'Schedule', reopen: 'Reopen', archive: 'Archive' }
    return label(actions[text] || english, arabic)
  }, direction }
}
export function useOwnerRead(key, load) {
  const [state, setState] = useState(null)
  const [revision, setRevision] = useState(0)
  useEffect(() => {
    const controller = new AbortController()
    const scope = createOwnerScope()
    setState(previous => ({ key, loading: true, data: previous?.key === key ? previous.data : undefined }))
    scope.run(() => load(controller.signal), data => setState({ key, data, loading: false }),
      error => setState({ key, error, loading: false }))
    return () => { scope.cancel(); controller.abort() }
    // The key describes every input to the loader; changes cancel the old request.
  }, [key, revision])
  const result = state?.key === key ? state : { loading: true }
  return { ...result, retry: () => setRevision(value => value + 1) }
}
export function ReadState({ state, t, children }) {
  if (state.loading && !state.data) return <p role="status">{t('Loading…')}</p>
  if (state.error) return <div role="alert"><p>{t('We could not load this information.')}</p><Button onClick={state.retry}>{t('Retry')}</Button></div>
  return children
}
export function ExamPagination({ page, count, onChange, t }) {
  return <nav className="exam-actions" aria-label={t('Pagination')}><Button variant="outline" disabled={page <= 1} onClick={() => onChange(page - 1)}>{t('Previous')}</Button><span aria-live="polite">{t('Page')} {page} / {Math.max(1, Math.ceil(count / 25))}</span><Button variant="outline" disabled={page * 25 >= count} onClick={() => onChange(page + 1)}>{t('Next')}</Button></nav>
}
export function Facts({ entries, t }) {
  return <dl className="exam-facts">{entries.map(([name, value]) => <div key={name}><dt>{t(name)}</dt><dd><bdi>{typeof value === 'boolean' ? t(value ? 'Yes' : 'No') : value ?? t('Not set')}</bdi></dd></div>)}</dl>
}
