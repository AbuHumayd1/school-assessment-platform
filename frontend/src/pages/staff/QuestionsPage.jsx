import { useEffect, useReducer, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { useLanguageMode } from '../../context/LanguageModeContext.jsx'
import { staffApiFetch } from '../../services/api.js'
import QuestionMedia from '../../components/common/QuestionMedia.jsx'
import './question-import.css'

const copy = {
  '+ Create new subject': '+ إنشاء مادة جديدة', 'Create new subject': 'إنشاء مادة جديدة',
  'Subject name': 'اسم المادة', 'Subject code': 'رمز المادة', 'Create & Select': 'إنشاء واختيار',
  'New imports can be resumed for 7 days. Save each review change.': 'يمكن استئناف عمليات الاستيراد الجديدة لمدة 7 أيام. احفظ كل تعديل للمراجعة.',
  'Saved changes can be resumed until the review session expires.': 'يمكن استئناف التعديلات المحفوظة حتى انتهاء صلاحية جلسة المراجعة.',
  'Subject created, but selection could not be saved. Select it from the Subject list.': 'تم إنشاء المادة، لكن تعذر حفظ اختيارها. اخترها من قائمة المواد.',
  'A subject with this code already exists in this institution.': 'توجد مادة بهذا الرمز في هذه المؤسسة بالفعل.',
  'Select or create a subject before importing.': 'اختر مادة أو أنشئ مادة قبل الاستيراد.',
  'Resume Imports': 'استئناف الاستيراد', 'Resume Import': 'استئناف الاستيراد',
  'Return to Question Bank': 'العودة إلى بنك الأسئلة', 'Import completed': 'اكتمل الاستيراد',
  'Ready to import': 'جاهز للاستيراد', 'Unresolved': 'غير محلول',
  'Review included errors': 'مراجعة الأخطاء المضمنة', 'Review included warnings': 'مراجعة العناصر المضمنة التي تحتاج إلى مراجعة',
  'Save a subject before confirmation.': 'احفظ المادة قبل تأكيد الاستيراد.',
  'Review document issues before confirmation.': 'راجع مشكلات المستند قبل تأكيد الاستيراد.',
  'No included questions.': 'لا توجد أسئلة مضمنة.',
  'This import session is unavailable. It may have expired.': 'جلسة الاستيراد غير متاحة. ربما انتهت صلاحيتها.',
  'Required': 'مطلوب', 'Eligible': 'مؤهل', 'Blocked': 'محظور', 'Confirmation status': 'حالة التأكيد',
  'Selected subject is unavailable.': 'المادة المحددة غير متاحة.',
  'Import metadata requires correction.': 'تحتاج بيانات الاستيراد إلى تصحيح.',
  'Question validation requires correction.': 'تحتاج بيانات السؤال إلى تصحيح.',
  'All sections': 'جميع الأقسام', 'Status': 'الحالة', 'Search questions': 'البحث في الأسئلة',
  'Page': 'الصفحة', 'of': 'من', 'Included questions': 'الأسئلة المضمنة', 'Excluded': 'مستبعد',
  'Questions': 'الأسئلة', 'Import Questions': 'استيراد الأسئلة', 'CSV': 'CSV', 'Word document': 'مستند Word',
  'Upload': 'رفع الملف', 'Processing…': 'جارٍ المعالجة…', 'Import Review': 'مراجعة الاستيراد',
  'Questions detected': 'الأسئلة المكتشفة', 'Ready': 'جاهز', 'Needs review': 'يحتاج إلى مراجعة', 'Errors': 'أخطاء',
  'Answers matched': 'الإجابات المطابقة', 'Missing answers': 'الإجابات المفقودة', 'Images': 'الصور', 'Equations': 'المعادلات',
  'All': 'الكل', 'Subject': 'المادة', 'Select a subject': 'اختر مادة', 'Confirm Import': 'تأكيد الاستيراد',
  'View Question Bank': 'عرض بنك الأسئلة', 'Include question': 'تضمين السؤال', 'Correct answer': 'الإجابة الصحيحة',
  'Question text': 'نص السؤال', 'Options': 'الخيارات', 'Save review': 'حفظ المراجعة',
  'I reviewed this question against the original document': 'راجعت هذا السؤال وفق المستند الأصلي',
  'Modified': 'تم التعديل', 'Source preview': 'معاينة المصدر', 'Section title': 'عنوان القسم',
  'Save section title': 'حفظ عنوان القسم', 'Question type': 'نوع السؤال', 'Multiple choice': 'اختيار من متعدد',
  'True / False': 'صواب / خطأ', 'Retry': 'إعادة المحاولة', 'Cancel': 'إلغاء', 'Loading…': 'جارٍ التحميل…',
  'Complete equation replacement': 'النص الكامل البديل للمعادلة', 'Original equation source': 'مصدر المعادلة الأصلي',
  'Equation content requires manual review.': 'محتوى المعادلة يتطلب مراجعة يدوية.',
  'Document issues': 'مشكلات المستند', 'I reviewed all document-level issues against the original': 'راجعت جميع مشكلات المستند وفق المصدر الأصلي',
  'We could not complete this request. Please retry.': 'تعذر إكمال الطلب. يرجى إعادة المحاولة.',
  'Imported as drafts': 'تم الاستيراد كمسودات', 'Save metadata': 'حفظ بيانات الاستيراد', 'Difficulty': 'الصعوبة',
  'Default marks': 'الدرجة الافتراضية', 'Easy': 'سهل', 'Medium': 'متوسط', 'Hard': 'صعب',
  'Remove option': 'حذف الخيار', 'Add option': 'إضافة خيار', 'No questions found': 'لا توجد أسئلة',
  'Relabel options A–E': 'إعادة ترقيم الخيارات من A إلى E',
  'Previous': 'السابق', 'Next': 'التالي', 'Inspection': 'عرض السؤال',
  'Question text is required.': 'نص السؤال مطلوب.',
  'Question text exceeds the limit.': 'نص السؤال يتجاوز الحد المسموح.',
  'Use two to five options.': 'استخدم خيارين إلى خمسة خيارات.',
  'Every option requires bounded, non-empty text.': 'يجب أن يحتوي كل خيار على نص ضمن الحد المسموح.',
  'Option markers are missing, repeated or out of order.': 'علامات الخيارات مفقودة أو مكررة أو غير مرتبة.',
  'A valid correct answer is required.': 'يجب تحديد إجابة صحيحة صالحة.',
  'Choose a supported objective question type.': 'اختر نوع سؤال موضوعي مدعومًا.',
  'True/false requires True and False options.': 'يتطلب سؤال الصواب والخطأ خياري True وFalse.',
  'Duplicate source question number; verify the answer manually.': 'رقم السؤال مكرر في المصدر؛ تحقق من الإجابة يدويًا.',
  'Answer key refers to an unavailable option.': 'يشير مفتاح الإجابة إلى خيار غير موجود.',
  'Duplicate answer-key entry; choose the correct answer manually.': 'إدخال مفتاح الإجابة مكرر؛ اختر الإجابة الصحيحة يدويًا.',
  'Unsupported Word object detected near this question. Review the original document before importing.': 'تم اكتشاف عنصر Word غير مدعوم قرب هذا السؤال. راجع المستند الأصلي قبل الاستيراد.',
  'Media association is ambiguous; verify against the source document.': 'ارتباط الصورة بالسؤال غير واضح؛ تحقق وفق المستند الأصلي.',
  'Unnumbered continuation after an option; verify its association.': 'يوجد نص غير مرقم بعد أحد الخيارات؛ تحقق من ارتباطه.',
  'Multiple options share a paragraph; verify the detected boundaries.': 'تشترك خيارات متعددة في فقرة واحدة؛ تحقق من الحدود المكتشفة.',
  'An image between questions has ambiguous association; review both neighboring questions.': 'ارتباط الصورة بين سؤالين غير واضح؛ راجع السؤالين المجاورين.',
  'Image occurs on an option-numbered paragraph; verify its association against the original.': 'توجد الصورة في فقرة مرقمة كخيار؛ تحقق من ارتباطها وفق المصدر الأصلي.',
  'Equation content requires manual review. Supply a complete replacement or exclude this question.': 'تتطلب المعادلة مراجعة يدوية. أدخل نصًا بديلًا كاملًا أو استبعد السؤال.',
  'Replace every unresolved option equation with complete mathematical content.': 'استبدل كل معادلة غير مكتملة في الخيارات بالمحتوى الرياضي الكامل.',
  'An image could not be converted. Exclude this question; its image must not be omitted.': 'تعذر تحويل صورة. استبعد السؤال؛ لا يجوز حذف صورته.',
  'Answer key has no preceding section.': 'لا يوجد قسم سابق لمفتاح الإجابة.',
  'Malformed or unassociated answer-key entry.': 'إدخال مفتاح الإجابة غير صالح أو غير مرتبط بقسم.',
  'Content outside a recognized question requires source review.': 'يوجد محتوى خارج الأسئلة المكتشفة يتطلب مراجعة المصدر.',
  'Unassociated media requires source review.': 'توجد صورة غير مرتبطة بسؤال وتتطلب مراجعة المصدر.',
  'Answer references a nonexistent question.': 'تشير الإجابة إلى سؤال غير موجود.',
  'This import session has expired. Upload the document again.': 'انتهت صلاحية جلسة الاستيراد. ارفع المستند مجددًا.',
  'This import session has already been confirmed.': 'تم تأكيد جلسة الاستيراد هذه بالفعل.',
  'The preview changed. Reload before saving.': 'تغيرت المعاينة. أعد تحميلها قبل الحفظ.',
  'Select a subject before confirmation.': 'اختر مادة قبل التأكيد.',
  'Correct, review or exclude every unresolved included question.': 'صحح أو راجع أو استبعد كل سؤال مضمن لم تُحل مشكلاته.',
  'Review the document-level source issues before confirmation.': 'راجع مشكلات مصدر المستند قبل التأكيد.',
  'Confirm the current server preview revision.': 'أكد النسخة الحالية من معاينة الخادم.',
  'Review session expires': 'تنتهي صلاحية جلسة المراجعة',
  'This file is not a supported, valid DOCX within the import limits.': 'الملف ليس مستند DOCX صالحًا ومدعومًا ضمن حدود الاستيراد.',
}
export function importError(error, t) {
  if (error.status !== 400 || !error.data || typeof error.data !== 'object') return t('We could not complete this request. Please retry.')
  return validationMessages(error.data.detail || error.data).map(t).join(' ') || t('We could not complete this request. Please retry.')
}
export function validationMessages(value) {
  return typeof value === 'string' ? [value] : Array.isArray(value) ? value.flatMap(validationMessages) : value && typeof value === 'object' ? Object.values(value).flatMap(validationMessages) : []
}
export const readinessLabel = value => ({ ready: 'Ready', needs_review: 'Needs review', error: 'Errors' }[value])
export function canConfirmImport(preview, busy = false) {
  return !busy && preview.confirmation?.eligible === true
}
export const initialReviewNavigation = { filter: 'all', sectionId: 'all', search: '', page: 0 }
export function reviewNavigationReducer(state, action) {
  if (action.type === 'attention') return { ...initialReviewNavigation, filter: action.filter, includedOnly: true }
  if (action.type === 'page') return { ...state, page: Math.max(0, action.page) }
  if (action.type === 'resetPage') return { ...state, page: 0 }
  if (['filter', 'sectionId', 'search', 'includedOnly'].includes(action.type)) return { ...state, [action.type]: action.value, page: 0 }
  return state
}
export function filterImportQuestions(source, filter = 'all', sectionId = 'all', search = '', includedOnly = false) {
  const query = search.trim().toLocaleLowerCase()
  return (source.sections || [source])
    .filter(section => sectionId === 'all' || section.id === sectionId)
    .flatMap(section => section.questions.filter(question =>
      (!includedOnly || question.included) && (filter === 'all' || question.readiness === filter) &&
      (!query || [question.text, question.source_number, ...question.options.map(option => option.text)].join(' ').toLocaleLowerCase().includes(query))))
}
export function importReviewPage(preview, navigation = initialReviewNavigation) {
  // Filter the complete session before pagination, including error and excluded items.
  const questions = filterImportQuestions(preview, navigation.filter, navigation.sectionId, navigation.search, navigation.includedOnly)
  const pageCount = Math.ceil(questions.length / 10)
  const page = Math.min(navigation.page, Math.max(0, pageCount - 1))
  return { questions, page, pageCount, total: questions.length,
    start: questions.length ? page * 10 + 1 : 0, end: Math.min((page + 1) * 10, questions.length),
    visible: questions.slice(page * 10, page * 10 + 10) }
}
function useCopy() {
  const { label, direction } = useLanguageMode()
  return { t: text => label(text, copy[text] || text), direction, label }
}

export function ImportSummary({ preview, t }) {
  return <dl className="import-summary">{[['Questions detected','questions_detected'],['Ready','ready_count'],['Needs review','review_count'],['Errors','error_count'],['Answers matched','answers_matched'],['Missing answers','answers_missing'],['Images','media_detected'],['Equations','equations_detected']].map(([name,key]) => <div key={key}><dt>{t(name)}</dt><dd>{preview.summary[key]}</dd></div>)}</dl>
}

export function importConfirmationCounts(preview) {
  return preview.confirmation
}
export function ImportConfirmation({ preview, t, busy, onConfirm, onAttention }) {
  const counts = importConfirmationCounts(preview)
  return <section className="import-confirmation import-upload" aria-label={t('Confirm Import')}>
    <h3>{t('Confirm Import')}</h3><p>{counts.ready} {t('Ready to import')} / {counts.excluded} {t('Excluded')} / {counts.unresolved} {t('Unresolved')}</p>
    <p>{t('Subject')}: <bdi>{counts.subject_name || t(counts.subject_id == null ? 'Required' : 'Selected subject is unavailable.')}</bdi></p>
    <p>{t('Confirmation status')}: {t(counts.eligible ? 'Eligible' : 'Blocked')}</p>
    {counts.blockers.map((blocker,index) => <div key={index}><p>{t(blocker.message)}{blocker.count ? ` (${blocker.count})` : ''}</p>{blocker.details && <ul>{validationMessages(blocker.details).map((message,i) => <li key={i}>{t(message)}</li>)}</ul>}</div>)}
    {!!counts.errors && <button onClick={() => onAttention('error')}>{t('Review included errors')} ({counts.errors})</button>}
    {!!counts.review && <button onClick={() => onAttention('needs_review')}>{t('Review included warnings')} ({counts.review})</button>}
    <button disabled={!canConfirmImport(preview,busy)} onClick={onConfirm}>{t('Confirm Import')}</button>
  </section>
}

export function SubjectSelector({ preview, subjects, t, busy, onChange }) {
  const subjectId = preview.subject_id ?? null
  const listed = subjects.some(subject => String(subject.id) === String(subjectId))
  return <label>{t('Subject')}<select value={subjectId === null ? '' : String(subjectId)} disabled={busy}
    onChange={event => onChange({metadata:{...preview.metadata, subject:event.target.value === '' ? null : Number(event.target.value), topic:null}})}>
    <option value="">{t('Select a subject')}</option>
    {subjectId !== null && !listed && <option value={String(subjectId)}>{preview.subject_name || t('Selected subject is unavailable.')}</option>}
    {subjects.map(subject => <option key={subject.id} value={String(subject.id)}>{subject.name}</option>)}
  </select></label>
}

export async function createImportSubject({ preview, institutionId, fields, signal, onCreated, fetch = staffApiFetch }) {
  const checkActive = () => { if (signal?.aborted) throw new DOMException('Request aborted', 'AbortError') }
  checkActive()
  const subject = await fetch('subjects/', {method:'POST', body:{institution:institutionId,name:fields.name,code:fields.code},signal})
  checkActive()
  onCreated?.(subject)
  try {
    const updated = await fetch(`questions/import/docx/${preview.import_session_id}/`, {method:'PATCH',
      body:{revision:preview.revision,metadata:{...preview.metadata,subject:subject.id,topic:null}},signal})
    checkActive()
    return {subject,preview:updated}
  } catch (error) {
    error.createdSubject = subject
    throw error
  }
}

export function subjectCreationError(failure, t) {
  return `${failure.createdSubject ? t('Subject created, but selection could not be saved. Select it from the Subject list.') + ' ' : ''}${importError(failure,t)}`
}

export function CreateSubjectForm({ t, busy, onCreate, onCancel }) {
  const [fields,setFields] = useState({name:'',code:''})
  const [error,setError] = useState(''), [created,setCreated] = useState(false)
  async function submit(event) {
    event.preventDefault();setError('')
    try { if (await onCreate(fields)) onCancel() }
    catch (failure) {
      setCreated(!!failure.createdSubject)
      setError(subjectCreationError(failure,t))
    }
  }
  return <form className="import-upload import-subject-create" aria-label={t('Create new subject')} onSubmit={submit}>
    <h3>{t('Create new subject')}</h3>{error && <p role="alert">{error}</p>}
    <fieldset disabled={busy || created}><label>{t('Subject name')}<input required maxLength={160} dir="auto" value={fields.name} onChange={e => setFields({...fields,name:e.target.value})} /></label>
      <label>{t('Subject code')}<input required maxLength={64} dir="auto" value={fields.code} onChange={e => setFields({...fields,code:e.target.value})} /></label></fieldset>
    <div className="import-actions"><button disabled={busy || created}>{t('Create & Select')}</button><button type="button" disabled={busy} onClick={onCancel}>{t('Cancel')}</button></div>
  </form>
}

export function ReviewQuestion({ question, t, busy, onSave }) {
  const [edit, setEdit] = useState(() => ({ text:question.text, options:question.options, correct_answer:question.correct_answer || '', question_type:question.question_type, included:question.included, reviewed:question.reviewed, equation_replacement:question.equation_replacement || '' }))
  function update(key, value) { setEdit(previous => ({ ...previous, [key]: value })) }
  return <article className="import-question"><header><strong>{question.source_number}</strong> <span className={`import-readiness import-readiness--${question.readiness}`}>{t(readinessLabel(question.readiness))}</span>{question.modified && <span>{t('Modified')}</span>}{!question.included && <span>{t('Excluded')}</span>}</header>
    <QuestionMedia media={question.media} />
    {question.equations.map((e,i) => <div className="import-equation" key={i}><bdi>{e.representation || t('Equation content requires manual review.')}</bdi>{e.status !== 'converted' && <details><summary>{t('Original equation source')}</summary><pre>{e.source_xml}</pre></details>}</div>)}
    {!!question.errors.length && <ul role="alert">{question.errors.map(e => <li key={e}>{t(e)}</li>)}</ul>}
    {!!question.warnings.length && <ul>{question.warnings.map(e => <li key={e}>{t(e)}</li>)}</ul>}
    <form onSubmit={event => { event.preventDefault(); onSave(question.id, edit.included ? edit : { included:false }) }}>
      <label><input type="checkbox" checked={edit.included} onChange={e => update('included',e.target.checked)} />{t('Include question')}</label>
      <label>{t('Question text')}<textarea dir="auto" value={edit.text} onChange={e => update('text',e.target.value)} /></label>
      <fieldset><legend>{t('Options')}</legend>{edit.options.map((option,i) => <div className="import-option" key={i}><label>{option.label}<textarea dir="auto" value={option.text} onChange={e => update('options', edit.options.map((o,j) => j===i ? {...o,text:e.target.value} : o))} /></label><button type="button" disabled={edit.options.length<=2} onClick={() => update('options',edit.options.filter((_,j) => i!==j).map((o,j) => ({...o,label:String.fromCharCode(65+j)})))}>{t('Remove option')}</button></div>)}<button type="button" disabled={edit.options.length>=5} onClick={() => update('options',[...edit.options,{label:String.fromCharCode(65+edit.options.length),text:''}])}>{t('Add option')}</button></fieldset>
      <button type="button" onClick={() => update('options',edit.options.map((o,i) => ({...o,label:String.fromCharCode(65+i)})))}>{t('Relabel options A–E')}</button>
      <label>{t('Correct answer')}<select value={edit.correct_answer} onChange={e => update('correct_answer',e.target.value)}><option value="">—</option>{edit.options.map((o,i) => <option key={`${o.label}:${i}`} value={o.label}>{o.label}</option>)}</select></label>
      <label>{t('Question type')}<select value={edit.question_type} onChange={e => update('question_type',e.target.value)}><option value="multiple_choice">{t('Multiple choice')}</option><option value="true_false">{t('True / False')}</option></select></label>
      {question.equations.some(e => e.status!=='converted') && <label>{t('Complete equation replacement')}<textarea dir="auto" value={edit.equation_replacement} onChange={e => update('equation_replacement',e.target.value)} /></label>}
      <label><input type="checkbox" checked={edit.reviewed} onChange={e => update('reviewed',e.target.checked)} />{t('I reviewed this question against the original document')}</label>
      <button disabled={busy}>{t('Save review')}</button>
    </form><details><summary>{t('Source preview')}</summary><pre dir="auto">{JSON.stringify(question.original,null,2)}</pre></details>
  </article>
}

export function ImportReview(props) {
  const [navigation, navigate] = useReducer(reviewNavigationReducer, initialReviewNavigation)
  const currentPage = importReviewPage(props.preview, navigation).page
  // Keep neighboring edits mounted; only clamp a page made invalid by a saved edit.
  useEffect(() => {
    if (navigation.page !== currentPage) navigate({ type: 'page', page: currentPage })
  }, [navigation.page, currentPage])
  return <ImportReviewContent {...props} navigation={navigation} navigate={navigate} />
}
export function ImportReviewContent({ preview, t, busy, onChange, onConfirm, onCancel, onCreateSubject, subjects, navigation = initialReviewNavigation, navigate = () => {} }) {
  const [creatingSubject,setCreatingSubject] = useState(false)
  const [metadata, setMetadata] = useState({difficulty:preview.metadata.difficulty || 'medium', default_marks:preview.metadata.default_marks || '1.00'})
  useEffect(() => {setMetadata({difficulty:preview.metadata.difficulty || 'medium', default_marks:preview.metadata.default_marks || '1.00'})},[preview.import_session_id,preview.metadata.difficulty,preview.metadata.default_marks])
  const section = preview.sections.find(s => s.id === navigation.sectionId)
  const [title, setTitle] = useState(section?.source_title || '')
  useEffect(() => { setTitle(section?.source_title || '') }, [section?.id, section?.source_title])
  const collection = importReviewPage(preview, navigation)
  const includedCount = preview.sections.flatMap(s => s.questions).filter(q => q.included).length
  return <section className="import-review"><h2>{t('Import Review')}</h2><ImportSummary preview={preview} t={t} /><ImportConfirmation preview={preview} t={t} busy={busy} onConfirm={onConfirm} onAttention={filter => navigate({ type:"attention", filter })} />
    {preview.expires_at && <p>{t('Saved changes can be resumed until the review session expires.')} {t('Review session expires')}: <bdi>{new Date(preview.expires_at).toLocaleString()}</bdi></p>}
    <form className="import-metadata" onSubmit={e => {e.preventDefault();onChange({metadata:{...preview.metadata,...metadata,subject:preview.subject_id ?? null}})}}><SubjectSelector preview={preview} subjects={subjects} t={t} busy={busy} onChange={onChange} /><label>{t('Difficulty')}<select value={metadata.difficulty || 'medium'} onChange={e => setMetadata({...metadata,difficulty:e.target.value})}>{['easy','medium','hard'].map(v => <option key={v} value={v}>{t(v[0].toUpperCase()+v.slice(1))}</option>)}</select></label><label>{t('Default marks')}<input type="number" min="0.01" step="0.01" value={metadata.default_marks || '1.00'} onChange={e => setMetadata({...metadata,default_marks:e.target.value})} /></label><button disabled={busy}>{t('Save metadata')}</button></form>
    {onCreateSubject && (creatingSubject ? <CreateSubjectForm t={t} busy={busy} onCreate={onCreateSubject} onCancel={() => setCreatingSubject(false)} /> : <button type="button" disabled={busy} onClick={() => setCreatingSubject(true)}>{t('+ Create new subject')}</button>)}
    <nav className="import-section-nav" aria-label={t('Section title')}><button aria-current={navigation.sectionId === 'all' ? 'page' : undefined} onClick={() => navigate({ type:'sectionId', value:'all' })}>{t('All sections')} ({preview.summary.questions_detected})</button>{preview.sections.map(s => <button key={s.id} aria-current={s.id === navigation.sectionId ? 'page' : undefined} onClick={() => navigate({ type:'sectionId', value:s.id })}><bdi>{s.source_title}</bdi> ({s.questions.length})</button>)}</nav>
    <div className="import-actions"><label>{t('Status')}<select value={navigation.filter} onChange={e => navigate({ type:'filter', value:e.target.value })}>{[['all','All'],['ready','Ready'],['needs_review','Needs review'],['error','Errors']].map(([v,l]) => <option key={v} value={v}>{t(l)}</option>)}</select></label><label>{t('Search questions')}<input type="search" value={navigation.search} onChange={e => navigate({ type:'search', value:e.target.value })} /></label><label><input type="checkbox" checked={!!navigation.includedOnly} onChange={e => navigate({ type:'includedOnly', value:e.target.checked })} />{t('Included questions')}</label>{onCancel && <button disabled={busy} onClick={onCancel}>{t('Cancel')}</button>}</div>
    <p>{t('Included questions')}: {includedCount} / {preview.summary.questions_detected}</p>
    {!!preview.key_errors.length && <details><summary>{t('Document issues')} ({preview.key_errors.length})</summary><ul>{preview.key_errors.map((e,i) => <li key={i}>{e.source_order}: {t(e.message)}</li>)}</ul><label><input type="checkbox" disabled={busy} checked={!!preview.source_reviewed} onChange={e => onChange({source_reviewed:e.target.checked})} />{t('I reviewed all document-level issues against the original')}</label></details>}
    {section && <form onSubmit={e => {e.preventDefault();onChange({section_id:section.id,section_title:title})}}><label>{t('Section title')}<input dir="auto" value={title} onChange={e => setTitle(e.target.value)} /></label><button disabled={busy}>{t('Save section title')}</button></form>}
    <p role="status">{t('Questions')}: {collection.start}–{collection.end} {t('of')} {collection.total}</p>
    {preview.sections.map(s => {
      const items = collection.visible.filter(q => s.questions.includes(q))
      return items.length > 0 && <section key={s.id}><h3><bdi>{s.source_title}</bdi></h3>{items.map(q => <ReviewQuestion key={`${q.id}:${q.review_revision || 0}`} question={q} t={t} busy={busy} onSave={(question_id,changes) => onChange({question_id,changes})} />)}</section>
    })}
    {!collection.total && <p>{t('No questions found')}</p>}
    {collection.total > 0 && <div className="import-actions"><button disabled={collection.page === 0} onClick={() => navigate({ type:'page', page:collection.page - 1 })}>{t('Previous')}</button><span>{t('Page')} {collection.page + 1} {t('of')} {collection.pageCount}</span><button disabled={collection.page + 1 >= collection.pageCount} onClick={() => navigate({ type:'page', page:collection.page + 1 })}>{t('Next')}</button></div>}
  </section>
}

export default function QuestionsPage() {
  const { sessionId } = useParams(), navigate = useNavigate()
  const { currentWorkspace } = useWorkspace()
  const { t, direction, label } = useCopy()
  const institutionId = currentWorkspace.institution.id
  const subjectRequest = useRef(null)
  useEffect(() => () => subjectRequest.current?.abort(),[institutionId,sessionId])
  const [kind, setKind] = useState(null), [preview, setPreview] = useState(null), [busy,setBusy] = useState(false)
  const [error,setError] = useState(''), [success,setSuccess] = useState(null), [questions,setQuestions] = useState(null), [subjects,setSubjects] = useState([]), [page,setPage] = useState(0), [revision,setRevision] = useState(0), [recent,setRecent] = useState([]), [loadingSession,setLoadingSession] = useState(!!sessionId)
  useEffect(() => {
    const controller = new AbortController()
    setSubjects([]);setRecent([])
    Promise.all([staffApiFetch(`questions/?institution=${institutionId}`,{signal:controller.signal}),staffApiFetch(`questions/import/docx/preview/?institution=${institutionId}`,{signal:controller.signal})]).then(([q,s]) => {setQuestions(q.results || q);setSubjects(s.subjects);setRecent(s.recent_imports || [])}).catch(e => {if(e.name!=='AbortError')setError(t('We could not complete this request. Please retry.'))})
    return () => controller.abort()
  },[institutionId,revision])
  useEffect(() => {
    const controller = new AbortController()
    setPreview(null);setError('');setLoadingSession(!!sessionId)
    if (sessionId) setSuccess(null)
    if (sessionId) staffApiFetch(`questions/import/docx/${sessionId}/`,{signal:controller.signal})
      .then(data => {if(controller.signal.aborted)return;if (data.status === 'completed') setSuccess(data.imported_count ?? 'completed');else setPreview(data)})
      .catch(e => {if(e.name !== 'AbortError') setError(e.status===404 ? t('This import session is unavailable. It may have expired.') : importError(e,t))})
      .finally(() => {if(!controller.signal.aborted)setLoadingSession(false)})
    return () => controller.abort()
  },[sessionId,institutionId,revision])
  function returnToBank() { navigate('/app/questions');setKind(null);setPreview(null);setSuccess(null);setRevision(v=>v+1) }
  async function run(action) {
    setBusy(true);setError('')
    try {await action()} catch(e) {setError(importError(e,t))} finally {setBusy(false)}
  }
  async function upload(e) {
    e.preventDefault();const data = new FormData(e.currentTarget)
    await run(async () => {
      const result = await staffApiFetch(kind==='docx' ? 'questions/import/docx/preview/' : 'questions/import/',{method:'POST',body:data})
      if(kind==='docx')navigate(`/app/questions/import/word/${result.import_session_id}`);else{setSuccess(result.imported_rows);setRevision(v=>v+1)}
    })
  }
  function review(changes) {return run(async () => setPreview(await staffApiFetch(`questions/import/docx/${preview.import_session_id}/`,{method:'PATCH',body:{revision:preview.revision,...changes}})))}
  async function createSubject(fields) {
    const controller = new AbortController();subjectRequest.current = controller
    setBusy(true);setError('')
    try {
      const result = await createImportSubject({preview,institutionId,fields,signal:controller.signal,
        onCreated:subject => setSubjects(existing => [...existing.filter(item => item.id !== subject.id),subject].sort((a,b) => a.name.localeCompare(b.name)))})
      if (controller.signal.aborted) return false
      setPreview(result.preview)
      return true
    } catch (error) {
      if (error.name === 'AbortError') return false
      throw error
    } finally {setBusy(false)}
  }
  function confirm() {return run(async () => {const r = await staffApiFetch(`questions/import/docx/${preview.import_session_id}/confirm/`,{method:'POST',body:{revision:preview.revision}});setSuccess(r.imported_count);setPreview(null)})}
  return <div className="question-bank" dir={direction}><h1>{t('Questions')}</h1>{error && <div role="alert">{error}<button onClick={() => setRevision(v=>v+1)}>{t('Retry')}</button></div>}
    {sessionId && <button onClick={returnToBank}>{t('Return to Question Bank')}</button>}
    {loadingSession ? <p role="status">{t('Loading…')}</p> : sessionId && !preview && success===null && error ? <p>{t('Retry')}</p> : success!==null ? <section role="status"><h2>{success === 'completed' ? t('Import completed') : label(`${success} questions imported as drafts.`, `تم استيراد ${success} سؤالًا كمسودات.`)}</h2><button onClick={returnToBank}>{t('View Question Bank')}</button></section> : preview ? <ImportReview key={`${institutionId}:${preview.import_session_id}`} preview={preview} t={t} busy={busy} subjects={subjects} onCreateSubject={createSubject} onChange={review} onConfirm={confirm} onCancel={returnToBank} /> : <>
      <div className="import-actions"><strong>{t('Import Questions')}</strong><button onClick={() => setKind('csv')}>{t('CSV')}</button><button onClick={() => setKind('docx')}>{t('Word document')}</button></div>
      {kind === 'docx' && <p>{t('New imports can be resumed for 7 days. Save each review change.')}</p>}
      {kind === 'docx' && recent.length > 0 && <section><h2>{t('Resume Imports')}</h2>{recent.map(item => <p key={item.import_session_id}><button onClick={() => navigate(`/app/questions/import/word/${item.import_session_id}`)}>{t('Resume Import')} / {item.questions_detected} / <bdi>{new Date(item.created_at).toLocaleString()}</bdi></button></p>)}</section>}
      {kind && <form className="import-upload" onSubmit={upload}><label>{t(kind==='docx'?'Word document':'CSV')}<input required name="file" type="file" accept={kind==='docx'?'.docx':'.csv'} disabled={busy} /></label><button disabled={busy}>{t(busy?'Processing…':'Upload')}</button><button type="button" disabled={busy} onClick={() => setKind(null)}>{t('Cancel')}</button></form>}
      {questions===null ? <p>{t('Loading…')}</p> : !questions.length ? <p>{t('No questions found')}</p> : questions.slice(page*25,page*25+25).map(q => <details className="import-question" key={q.id}><summary><bdi>{q.text.slice(0,120)}</bdi> · {q.status}</summary><p dir="auto">{q.source_metadata?.section_title}</p><p dir="auto" style={{whiteSpace:'pre-wrap'}}>{q.text}</p><QuestionMedia media={q.media} /><ol>{q.options.map(o => <li key={o.id}><bdi>{o.text}</bdi>{o.is_correct && <> · {t('Correct answer')}</>}</li>)}</ol></details>)}
      {questions?.length>25 && <div className="import-actions"><button disabled={page===0} onClick={()=>setPage(page-1)}>{t('Previous')}</button><button disabled={(page+1)*25>=questions.length} onClick={()=>setPage(page+1)}>{t('Next')}</button></div>}
    </>}{busy && preview && <p role="status">{t('Processing…')}</p>}</div>
}
