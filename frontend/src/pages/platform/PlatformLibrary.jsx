import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import QuestionMedia from '../../components/common/QuestionMedia.jsx'
import { libraryAction, libraryChoices, libraryList, librarySave } from '../../services/platformLibrary.js'
import './platform-library.css'

export const questionStatuses = { draft: 'Draft', review: 'In review', approved: 'Approved', archived: 'Archived' }
export const questionTypes = { multiple_choice: 'Multiple choice', multiple_select: 'Multiple select', true_false: 'True / False' }
export function libraryError(error) {
  const flatten = value => typeof value === 'string' ? [value] : value && typeof value === 'object' ? Object.values(value).flatMap(flatten) : []
  return flatten(error.data).join(' ') || 'The request could not be completed. Please retry.'
}
export function editableQuestion(question) { return !question.content_locked && ['draft', 'review'].includes(question.status) }
export function blankQuestion(subject) {
  return { subject: String(subject || ''), topic: '', question_type: 'multiple_choice', difficulty: 'medium', text: '', explanation: '', marks: '1.00', source: '', options: [{ text: '', is_correct: true }, { text: '', is_correct: false }] }
}
export function questionPayload(form) {
  return { ...form, subject: Number(form.subject), topic: form.topic ? Number(form.topic) : null,
    options: form.options.map((option, index) => ({ text: option.text, is_correct: option.is_correct, order: index + 1 })) }
}

export function LibraryQuestionForm({ initial, subjects, topics, busy, onSave, onCancel }) {
  const [form, setForm] = useState(initial)
  const change = (key, value) => setForm(old => ({ ...old, [key]: value }))
  return <form className="platform-form library-editor" onSubmit={event => { event.preventDefault(); onSave(questionPayload(form)) }}>
    <h2>{initial.id ? 'Edit question' : 'Create question'}</h2>
    <label>Subject<select required value={form.subject} onChange={event => setForm(old => ({ ...old, subject: event.target.value, topic: '' }))}><option value="">Select a subject</option>{subjects.map(subject => <option key={subject.id} value={subject.id}>{subject.name} · {subject.code}</option>)}</select></label>
    <label>Topic<select value={form.topic || ''} onChange={event => change('topic', event.target.value)}><option value="">No topic</option>{topics.filter(topic => String(topic.subject) === String(form.subject)).map(topic => <option key={topic.id} value={topic.id}>{topic.name}</option>)}</select></label>
    <label>Question type<select value={form.question_type} onChange={event => change('question_type', event.target.value)}>{Object.entries(questionTypes).map(([value, label]) => <option key={value} value={value}>{label}</option>)}</select></label>
    <label>Difficulty<select value={form.difficulty} onChange={event => change('difficulty', event.target.value)}>{['easy', 'medium', 'hard'].map(value => <option key={value} value={value}>{value[0].toUpperCase() + value.slice(1)}</option>)}</select></label>
    <label>Marks<input type="number" required min="0.01" step="0.01" value={form.marks} onChange={event => change('marks', event.target.value)} /></label>
    <label>Question text<textarea required value={form.text} onChange={event => change('text', event.target.value)} /></label>
    <label>Explanation<textarea value={form.explanation} onChange={event => change('explanation', event.target.value)} /></label>
    <label>Source<input value={form.source} onChange={event => change('source', event.target.value)} /></label>
    <fieldset><legend>Options</legend>{form.options.map((option, index) => <div className="library-option" key={index}><label>Option {index + 1}<input required value={option.text} onChange={event => change('options', form.options.map((item, i) => i === index ? { ...item, text: event.target.value } : item))} /></label><label><input type="checkbox" checked={option.is_correct} onChange={event => change('options', form.options.map((item, i) => i === index ? { ...item, is_correct: event.target.checked } : item))} />Correct answer</label><button type="button" disabled={busy || form.options.length <= 2} onClick={() => change('options', form.options.filter((_, i) => i !== index))}>Remove option</button></div>)}<button type="button" onClick={() => change('options', [...form.options, { text: '', is_correct: false }])}>Add option</button></fieldset>
    <div className="library-actions"><button disabled={busy} type="submit">Save question</button><button type="button" disabled={busy} onClick={onCancel}>Cancel</button></div>
  </form>
}

export function LibraryQuestionCard({ question, busy, onEdit, onAction }) {
  return <article className="library-question"><h3>{question.text}</h3><p>{questionTypes[question.question_type]} · {questionStatuses[question.status]} · Revision {question.revision_number}</p>
    {question.content_locked && <p>Content locked. Create a new revision to make changes.</p>}
    {!question.available_for_new_assessments && <p>Unavailable for new exam selections. Existing references remain valid.</p>}
    <QuestionMedia media={question.media || []} /><ol>{question.options.map(option => <li key={option.id}>{option.text}{option.is_correct && ' · Correct answer'}</li>)}</ol>
    {question.explanation && <p>{question.explanation}</p>}<details><summary>Revision identity</summary><p>Question {question.id} · Revision family {question.revision_family}</p></details>
    <div className="library-actions"><button disabled={busy || !editableQuestion(question)} onClick={() => onEdit(question)}>Edit</button>
      {question.status === 'draft' && <button disabled={busy} onClick={() => onAction(question, 'submit-for-review')}>Submit for review</button>}
      {question.status === 'review' && <><button disabled={busy} onClick={() => onAction(question, 'request-changes')}>Request changes</button><button disabled={busy} onClick={() => onAction(question, 'approve')}>Approve</button></>}
      {question.status === 'approved' && <button disabled={busy} onClick={() => onAction(question, 'archive')}>Archive</button>}
      {question.content_locked && <button disabled={busy} onClick={() => onAction(question, 'new-revision')}>Create new revision</button>}
    </div></article>
}

export default function PlatformLibrary() {
  const [subjects, setSubjects] = useState([]), [topics, setTopics] = useState([]), [data, setData] = useState({ results: [], count: 0 })
  const [filters, setFilters] = useState({ subject: '', topic: '', status: '', question_type: '', difficulty: '', search: '', page: 1 })
  const [refresh, setRefresh] = useState(0), [busy, setBusy] = useState(false), [loading, setLoading] = useState(true), [error, setError] = useState(''), [notice, setNotice] = useState('')
  const [editor, setEditor] = useState(null), [subjectForm, setSubjectForm] = useState({ name: '', code: '' }), [topicName, setTopicName] = useState('')
  useEffect(() => {
    const controller = new AbortController(); setLoading(true); setError('')
    Promise.all([libraryChoices('subjects', {}, { signal: controller.signal }), libraryChoices('topics', {}, { signal: controller.signal }), libraryList('questions', filters, { signal: controller.signal })])
      .then(([s, t, q]) => { setSubjects(s); setTopics(t); setData(q) })
      .catch(failure => { if (!controller.signal.aborted) setError(libraryError(failure)) })
      .finally(() => { if (!controller.signal.aborted) setLoading(false) })
    return () => controller.abort()
  }, [filters, refresh])
  async function mutate(work) {
    setBusy(true); setError(''); setNotice('')
    try { await work(); setRefresh(old => old + 1) }
    catch (failure) { setError(libraryError(failure)) }
    finally { setBusy(false) }
  }
  function edit(question) {
    setEditor({ ...blankQuestion(question.subject), ...Object.fromEntries(['id', 'subject', 'topic', 'question_type', 'difficulty', 'text', 'explanation', 'marks', 'source', 'options'].map(key => [key, question[key]])) })
  }
  function filter(key, value) { setFilters(old => ({ ...old, [key]: value, page: 1, ...(key === 'subject' ? { topic: '' } : {}) })) }
  return <section className="platform-library"><h1>Platform Library</h1><p>Reusable questions prepared centrally. Client question banks remain separate.</p><Link to="/platform/institution-banks">Institution Banks</Link>
    {error && <p role="alert">{error}</p>}{notice && <p role="status">{notice}</p>}
    <details><summary>Create a platform subject</summary><form className="platform-form" onSubmit={event => { event.preventDefault(); mutate(async () => { const subject = await librarySave('subjects', subjectForm); setSubjectForm({ name: '', code: '' }); filter('subject', String(subject.id)); setNotice('Subject created.') }) }}><label>Subject name<input required maxLength={160} value={subjectForm.name} onChange={event => setSubjectForm(old => ({ ...old, name: event.target.value }))} /></label><label>Subject code<input required maxLength={64} value={subjectForm.code} onChange={event => setSubjectForm(old => ({ ...old, code: event.target.value }))} /></label><button disabled={busy}>Create subject</button></form></details>
    <div className="library-filters"><label>Subject<select value={filters.subject} onChange={event => filter('subject', event.target.value)}><option value="">All subjects</option>{subjects.map(subject => <option key={subject.id} value={subject.id}>{subject.name} · {subject.code}{!subject.is_active ? ' · Inactive' : ''}</option>)}</select></label>
      {filters.subject && <><label>Topic<select value={filters.topic} onChange={event => filter('topic', event.target.value)}><option value="">All topics</option>{topics.filter(topic => String(topic.subject) === filters.subject).map(topic => <option key={topic.id} value={topic.id}>{topic.name}</option>)}</select></label><form onSubmit={event => { event.preventDefault(); mutate(async () => { await librarySave('topics', { subject: Number(filters.subject), name: topicName }); setTopicName(''); setNotice('Topic created.') }) }}><label>New topic<input required maxLength={160} value={topicName} onChange={event => setTopicName(event.target.value)} /></label><button disabled={busy}>Create topic</button></form></>}
      {[['status', 'Status', questionStatuses], ['question_type', 'Question type', questionTypes], ['difficulty', 'Difficulty', { easy: 'Easy', medium: 'Medium', hard: 'Hard' }]].map(([key, label, values]) => <label key={key}>{label}<select value={filters[key]} onChange={event => filter(key, event.target.value)}><option value="">All</option>{Object.entries(values).map(([value, text]) => <option key={value} value={value}>{text}</option>)}</select></label>)}
      <label>Search questions<input type="search" maxLength={200} value={filters.search} onChange={event => filter('search', event.target.value)} /></label></div>
    <button disabled={busy || loading || !subjects.length} onClick={() => setEditor(blankQuestion(filters.subject))}>Create question</button>
    {editor && <LibraryQuestionForm key={editor.id || 'new'} initial={editor} subjects={subjects} topics={topics} busy={busy} onCancel={() => setEditor(null)} onSave={payload => mutate(async () => { const { id, ...body } = payload; await librarySave('questions', body, editor.id); setEditor(null); setNotice('Question saved.') })} />}
    {loading ? <p role="status">Loading library…</p> : <><p>{data.count} questions</p>{!data.results.length && <p>No questions found.</p>}{data.results.map(question => <LibraryQuestionCard key={question.id} question={question} busy={busy} onEdit={edit} onAction={(q, action) => mutate(async () => { const result = await libraryAction(q.id, action); if (action === 'new-revision') { setFilters(old => ({ ...old, status: '', search: '', page: 1 })); edit(result) } setNotice(action === 'new-revision' ? `Revision ${result.revision_number} created. The previous revision is unchanged.` : 'Question workflow updated.') })} />)}<div className="library-actions"><button disabled={!data.previous || busy} onClick={() => setFilters(old => ({ ...old, page: old.page - 1 }))}>Previous</button><span>Page {filters.page}</span><button disabled={!data.next || busy} onClick={() => setFilters(old => ({ ...old, page: old.page + 1 }))}>Next</button></div></>}
  </section>
}

export function InstitutionBanks() {
  return <section><h1>Institution Banks</h1><p>Choose a client, enter its workspace, then open Questions. Each question bank contains only that client’s content.</p><Link to="/platform/clients">Choose a client</Link></section>
}
