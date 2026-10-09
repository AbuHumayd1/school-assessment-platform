import { useEffect, useReducer, useRef, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { useWorkspace } from '../../context/WorkspaceContext.jsx'
import { useLanguageMode } from '../../context/LanguageModeContext.jsx'
import { staffApiFetch } from '../../services/api.js'
import QuestionMedia from '../../components/common/QuestionMedia.jsx'
import { SubjectEmptyState } from './SubjectsPage.jsx'
import ImportBlocks, { classifyImportBlock, importMessage } from './ImportBlocks.jsx'
import AnswerKeyPanel, { answerKeyCopy, saveAnswerMatch, uploadAnswerKey, downloadAnswerTemplate } from './AnswerKeyPanel.jsx'
import { importWorkflowCopy, sessionMode, ImportModeChoice, ImportWorkflowHeading, ImportCards, manageImportAction } from './ImportWorkflow.jsx'
import './question-import.css'

const copy = {
  'No subjects have been created for this institution yet.': 'لم تُنشأ أي مواد لهذه المؤسسة بعد.',
  'Create a subject': 'إنشاء مادة',
  ...answerKeyCopy,
  ...importWorkflowCopy,
 'Source document':'\u0627\u0644\u0645\u0633\u062a\u0646\u062f \u0627\u0644\u0645\u0635\u062f\u0631','Import reference':'\u0645\u0631\u062c\u0639 \u0627\u0644\u0627\u0633\u062a\u064a\u0631\u0627\u062f','Document position':'\u0627\u0644\u0645\u0648\u0636\u0639 \u0641\u064a \u0627\u0644\u0645\u0633\u062a\u0646\u062f',
 'All subjects':'\u062c\u0645\u064a\u0639 \u0627\u0644\u0645\u0648\u0627\u062f','Other questions':'\u0623\u0633\u0626\u0644\u0629 \u0623\u062e\u0631\u0649','Imported':'\u0627\u0644\u0645\u0633\u062a\u0648\u0631\u062f\u0629','Draft':'\u0645\u0633\u0648\u062f\u0629','In review':'\u0642\u064a\u062f \u0627\u0644\u0645\u0631\u0627\u062c\u0639\u0629','Approved':'\u0645\u0639\u062a\u0645\u062f','Archived':'\u0645\u0624\u0631\u0634\u0641','Multiple select':'\u0627\u062e\u062a\u064a\u0627\u0631\u0627\u062a \u0645\u062a\u0639\u062f\u062f\u0629',
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
  return validationMessages(error.data.detail || error.data).map(message=>t(importMessage(message))).join(' ') || t('We could not complete this request. Please retry.')
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
  return <><p>{preview.summary.questions_detected} {t('Questions found')} · {preview.summary.answers_matched} {t('Answers matched')}</p><details><summary>{t('Import details')}</summary><dl className="import-summary">{[['Questions detected','questions_detected'],['Ready','ready_count'],['Needs review','review_count'],['Errors','error_count'],['Excluded','excluded_count'],['Answers matched','answers_matched'],['Missing answers','answers_missing'],['Images','media_detected'],['Equations','equations_detected']].map(([name,key]) => <div key={key}><dt>{t(name)}</dt><dd>{preview.summary[key]}</dd></div>)}</dl></details></>
}

export function importConfirmationCounts(preview) {
  return preview.confirmation
}
export function ImportConfirmation({ preview, t, busy, onConfirm, onAttention }) {
  const counts = importConfirmationCounts(preview)
  return <section className="import-confirmation import-upload" aria-label={t('Confirm Import')}>
    <h3>{t(counts.eligible?'Your import is ready':'Items needing attention')}{!counts.eligible && <>: {counts.attention_count ?? (counts.unresolved || 0)+counts.blockers.reduce((n,b)=>n+(b.code==='unresolved'?0:b.count||1),0)}</>}</h3><p>{counts.ready} {t('Ready to import')}{counts.unresolved>0 && <> · {counts.unresolved} {t('Unresolved')}</>}{counts.additional_issues>0 && <> · {counts.additional_issues} {t('Additional issues')}</>}{counts.excluded>0 && <> · {counts.excluded} {t('Excluded')}</>}</p>
    <p>{t('Subject')}: <bdi>{counts.subject_name || t(counts.subject_id == null ? 'Required' : 'Selected subject is unavailable.')}</bdi></p>
    {counts.eligible && <p>{t('No issues found')}</p>}
    {counts.blockers.map((blocker,index) => <div key={index}><p>{t(blocker.message)}{blocker.count ? ` (${blocker.count})` : ''}</p>{['classification_required','document_review'].includes(blocker.code) && <a href={blocker.code==='classification_required'?'#import-document-parts':'#import-document-check'}>{t('Review document section')}</a>}{blocker.details && <ul>{validationMessages(blocker.details).map((message,i) => <li key={i}>{t(message)}</li>)}</ul>}</div>)}
    {!!counts.errors && <button onClick={() => onAttention('error')}>{t('Review included errors')} ({counts.errors})</button>}
    {!!counts.review && <button onClick={() => onAttention('needs_review')}>{t('Review included warnings')} ({counts.review})</button>}
    <button disabled={!canConfirmImport(preview,busy)} onClick={onConfirm}>{t('Import Questions')} ({counts.included})</button>
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
      <label>{t('Correct answer')}<select multiple={edit.question_type==='multiple_select'} value={edit.question_type==='multiple_select'?(Array.isArray(edit.correct_answer)?edit.correct_answer:edit.correct_answer?[edit.correct_answer]:[]):Array.isArray(edit.correct_answer)?edit.correct_answer[0] || '':edit.correct_answer} onChange={e => update('correct_answer',edit.question_type==='multiple_select'?Array.from(e.target.selectedOptions,option=>option.value):e.target.value)}>{edit.question_type!=='multiple_select' && <option value="">—</option>}{edit.options.map((o,i) => <option key={`${o.label}:${i}`} value={o.label}>{o.label}</option>)}</select></label>
      <label>{t('Question type')}<select value={edit.question_type} onChange={e => {update('question_type',e.target.value);update('correct_answer',e.target.value==='multiple_select'?(Array.isArray(edit.correct_answer)?edit.correct_answer:edit.correct_answer?[edit.correct_answer]:[]):Array.isArray(edit.correct_answer)?edit.correct_answer[0] || '':edit.correct_answer)}}><option value="multiple_choice">{t('Multiple choice')}</option><option value="multiple_select">{t('Multiple select')}</option><option value="true_false">{t('True / False')}</option></select></label>
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
export function ImportReviewContent({ preview, t, busy, onChange, onConfirm, onCancel, onCreateSubject, onKeyUpload, onKeySave, onKeyRemove, onTemplate, onClassify, onDelete, subjects, navigation = initialReviewNavigation, navigate = () => {} }) {
  const [creatingSubject,setCreatingSubject] = useState(false)
  const [metadata, setMetadata] = useState({difficulty:preview.metadata.difficulty || 'medium', default_marks:preview.metadata.default_marks || '1.00'})
  useEffect(() => {setMetadata({difficulty:preview.metadata.difficulty || 'medium', default_marks:preview.metadata.default_marks || '1.00'})},[preview.import_session_id,preview.metadata.difficulty,preview.metadata.default_marks])
  const section = preview.sections.find(s => s.id === navigation.sectionId)
  const [title, setTitle] = useState(section?.source_title || '')
  useEffect(() => { setTitle(section?.source_title || '') }, [section?.id, section?.source_title])
  const collection = importReviewPage(preview, navigation)
  const documentIssues=preview.confirmation.document_issues ?? preview.key_errors.filter(e=>!e.reconciliation)
  const includedCount = preview.sections.flatMap(s => s.questions).filter(q => q.included).length
  return <section className="import-review"><h2>{t('Import Review')}</h2><ImportWorkflowHeading preview={preview} t={t}/><ImportSummary preview={preview} t={t} /><ImportConfirmation preview={preview} t={t} busy={busy} onConfirm={onConfirm} onAttention={filter => navigate({ type:"attention", filter })} />
    {preview.expires_at && <p>{t('Saved changes can be resumed until the review session expires.')} {t('Review session expires')}: <bdi>{new Date(preview.expires_at).toLocaleString()}</bdi></p>}
    {onDelete && <button disabled={busy} onClick={()=>onDelete(preview)}>{t('Delete Import')}</button>}
    <ImportBlocks preview={preview} t={t} busy={busy} onClassify={onClassify}/>
    {onKeySave && <AnswerKeyPanel preview={preview} t={t} busy={busy} onUpload={onKeyUpload} onSave={onKeySave} onRemove={onKeyRemove} onTemplate={onTemplate}/>}
    <form className="import-metadata" onSubmit={e => {e.preventDefault();onChange({metadata:{...preview.metadata,...metadata,subject:preview.subject_id ?? null}})}}><SubjectSelector preview={preview} subjects={subjects} t={t} busy={busy} onChange={onChange} /><label>{t('Difficulty')}<select value={metadata.difficulty || 'medium'} onChange={e => setMetadata({...metadata,difficulty:e.target.value})}>{['easy','medium','hard'].map(v => <option key={v} value={v}>{t(v[0].toUpperCase()+v.slice(1))}</option>)}</select></label><label>{t('Default marks')}<input type="number" min="0.01" step="0.01" value={metadata.default_marks || '1.00'} onChange={e => setMetadata({...metadata,default_marks:e.target.value})} /></label><button disabled={busy}>{t('Save metadata')}</button></form>
    {onCreateSubject && (creatingSubject ? <CreateSubjectForm t={t} busy={busy} onCreate={onCreateSubject} onCancel={() => setCreatingSubject(false)} /> : <button type="button" disabled={busy} onClick={() => setCreatingSubject(true)}>{t('+ Create new subject')}</button>)}
    <details open={!preview.confirmation.eligible || navigation.filter!=='all'}><summary>{t('Review Questions')}</summary><nav className="import-section-nav" aria-label={t('Section title')}><button aria-current={navigation.sectionId === 'all' ? 'page' : undefined} onClick={() => navigate({ type:'sectionId', value:'all' })}>{t('All sections')} ({preview.summary.questions_detected})</button>{preview.sections.map(s => <button key={s.id} aria-current={s.id === navigation.sectionId ? 'page' : undefined} onClick={() => navigate({ type:'sectionId', value:s.id })}><bdi>{s.source_title}</bdi> ({s.questions.length})</button>)}</nav>
    <div className="import-actions"><label>{t('Status')}<select value={navigation.filter} onChange={e => navigate({ type:'filter', value:e.target.value })}>{[['all','All'],['ready','Ready'],['needs_review','Needs review'],['error','Errors']].map(([v,l]) => <option key={v} value={v}>{t(l)}</option>)}</select></label><label>{t('Search questions')}<input type="search" value={navigation.search} onChange={e => navigate({ type:'search', value:e.target.value })} /></label><label><input type="checkbox" checked={!!navigation.includedOnly} onChange={e => navigate({ type:'includedOnly', value:e.target.checked })} />{t('Included questions')}</label>{onCancel && <button disabled={busy} onClick={onCancel}>{t('Cancel')}</button>}</div>
    <p>{t('Included questions')}: {includedCount} / {preview.summary.questions_detected}</p>
    {!!documentIssues.length && <details id="import-document-check" open={preview.confirmation.blockers.some(b=>b.code==='document_review')}><summary>{t('Check document content')} ({documentIssues.length})</summary><p>{t('Check the highlighted document content against your Word file, then confirm that you have reviewed it.')}</p><ul>{documentIssues.map((e,i) => <li key={i}>{t('Document position')} {e.source_order}: {e.text ? <bdi dir="auto">{e.text}</bdi> : t('Check this part against your Word file.')}</li>)}</ul><label><input type="checkbox" disabled={busy} checked={!!preview.source_reviewed} onChange={e => onChange({source_reviewed:e.target.checked})} />{t('I checked this content against my Word file.')}</label></details>}
    {section && <form onSubmit={e => {e.preventDefault();onChange({section_id:section.id,section_title:title})}}><label>{t('Section title')}<input dir="auto" value={title} onChange={e => setTitle(e.target.value)} /></label><button disabled={busy}>{t('Save section title')}</button></form>}
    <p role="status">{t('Questions')}: {collection.start}–{collection.end} {t('of')} {collection.total}</p>
    {preview.sections.map(s => {
      const items = collection.visible.filter(q => s.questions.includes(q))
      return items.length > 0 && <section key={s.id}><h3><bdi>{s.source_title}</bdi></h3>{s.directions && <p dir="auto" className="bank-directions">{s.directions}</p>}{items.map(q => <ReviewQuestion key={`${q.id}:${q.review_revision || 0}`} question={q} t={t} busy={busy} onSave={(question_id,changes) => onChange({question_id,changes})} />)}</section>
    })}
    {!collection.total && <p>{t('No questions found')}</p>}
    {collection.total > 0 && <div className="import-actions"><button disabled={collection.page === 0} onClick={() => navigate({ type:'page', page:collection.page - 1 })}>{t('Previous')}</button><span>{t('Page')} {collection.page + 1} {t('of')} {collection.pageCount}</span><button disabled={collection.page + 1 >= collection.pageCount} onClick={() => navigate({ type:'page', page:collection.page + 1 })}>{t('Next')}</button></div>}
  </details></section>
}

export async function loadBankQuestions(institutionId, signal, fetcher = staffApiFetch) {
 let path=`questions/?institution=${institutionId}`, all=[], seen=new Set()
 while(path){
  if(seen.has(path))throw new Error('Repeated question page')
  seen.add(path)
  const data=await fetcher(path,{signal});all.push(...(Array.isArray(data)?data:data.results))
  if(!data.next)break
  const next=new URL(data.next,'http://localhost')
  if(!next.pathname.endsWith('/api/v1/questions/'))throw new Error('Unexpected question page')
  next.searchParams.set('institution',institutionId);path=`questions/${next.search}`
 }
 return [...new Map(all.map(q=>[q.id,q])).values()]
}
export function questionBankGroups(questions,{subject='',status='',search='',section=''}={}){
 const groups=new Map()
 for(const q of questions){
  const m=q.source_metadata||{},title=m.section_title||''
  if(subject&&String(q.subject)!==String(subject)||status&&q.status!==status||section&&title!==section||search&&!q.text.toLocaleLowerCase().includes(search.toLocaleLowerCase()))continue
  const document=m.import_session_id||m.source_document?.sha256||`legacy:${q.source||''}`
  const key=JSON.stringify([q.subject,document,title?m.section_id||[m.section_order,title]:null])
  if(!groups.has(key))groups.set(key,{key,subject:q.subject,document,title,order:m.section_order??Infinity,filename:m.source_document?.filename||'',directions:[],questions:[]})
  const g=groups.get(key);g.questions.push(q)
  if(m.section_directions&&!g.directions.includes(m.section_directions))g.directions.push(m.section_directions)
 }
 return [...groups.values()].sort((a,b)=>String(a.subject).localeCompare(String(b.subject),undefined,{numeric:true})||a.document.localeCompare(b.document)||a.order-b.order||a.title.localeCompare(b.title)).map(g=>({...g,questions:g.title?[...g.questions].sort((a,b)=>(a.source_metadata?.document_order??Infinity)-(b.source_metadata?.document_order??Infinity)||a.id-b.id):g.questions}))
}
const bankTypes={multiple_choice:'Multiple choice',multiple_select:'Multiple select',true_false:'True / False'}
const bankStatuses={draft:'Draft',review:'In review',approved:'Approved',archived:'Archived'}
export function QuestionBank({questions,subjects,t}){
 const [filters,setFilters]=useState({subject:'',status:'',search:'',section:''})
 const groups=questionBankGroups(questions,filters)
 const sections=[...new Set(questions.filter(q=>!filters.subject||String(q.subject)===filters.subject).map(q=>q.source_metadata?.section_title).filter(Boolean))]
 const change=(key,value)=>setFilters(old=>({...old,[key]:value,...(key==='subject'?{section:''}:{})}))
 return <section className="structured-bank"><div className="bank-filters">
 <label>{t('Subject')}<select value={filters.subject} onChange={e=>change('subject',e.target.value)}><option value="">{t('All subjects')}</option>{subjects.map(s=><option key={s.id} value={s.id}>{s.name} · {s.code}</option>)}</select></label>
 <label>{t('Status')}<select value={filters.status} onChange={e=>change('status',e.target.value)}><option value="">{t('All')}</option>{['draft','review','approved','archived'].map(s=><option key={s} value={s}>{t(bankStatuses[s])}</option>)}</select></label>
 <label>{t('Section title')}<select value={filters.section} onChange={e=>change('section',e.target.value)}><option value="">{t('All sections')}</option>{sections.map(s=><option key={s}>{s}</option>)}</select></label>
 <label>{t('Search questions')}<input type="search" value={filters.search} onChange={e=>change('search',e.target.value)}/></label></div>
 <p role="status">{groups.reduce((n,g)=>n+g.questions.length,0)} {t('Questions')}</p>{!groups.length&&<p>{t('No questions found')}</p>}
 {subjects.filter(s=>groups.some(g=>String(g.subject)===String(s.id))).map(subject=><section key={subject.id} className="bank-subject"><h2><bdi>{subject.name}</bdi></h2><p><bdi>{subject.code}</bdi> · {groups.filter(g=>String(g.subject)===String(subject.id)).reduce((n,g)=>n+g.questions.length,0)} {t('Questions')}</p>
 {groups.filter(g=>String(g.subject)===String(subject.id)).map(g=><section key={g.key} className="bank-section"><h3><bdi>{g.title||t('Other questions')}</bdi> · {g.questions.length} {t('Questions')}</h3>{g.filename&&<p><bdi>{g.filename}</bdi></p>}{g.directions.map(d=><p key={d} dir="auto" className="bank-directions">{d}</p>)}
 {g.questions.map(q=><details className="import-question" key={q.id}><summary>{q.source_metadata?.question_number!=null&&<bdi className="source-number">Q{q.source_metadata.question_number}</bdi>} <bdi>{q.text.slice(0,120)}</bdi> · {t(bankTypes[q.question_type] || q.question_type)} · {t(bankStatuses[q.status] || q.status)}</summary><p dir="auto" style={{whiteSpace:'pre-wrap'}}>{q.text}</p><QuestionMedia media={q.media}/><ol>{q.options.map(o=><li key={o.id}><bdi>{o.text}</bdi>{o.is_correct&&<> · {t('Correct answer')}</>}</li>)}</ol><dl><dt>{t('Source document')}</dt><dd><bdi>{g.filename||q.source||'\u2014'}</bdi></dd>{q.source_metadata?.import_session_id && <><dt>{t('Import reference')}</dt><dd><bdi>{q.source_metadata.import_session_id}</bdi></dd></>}{q.source_metadata?.document_order != null && <><dt>{t('Document position')}</dt><dd>{q.source_metadata.document_order}</dd></>}</dl>{q.source_metadata?.equations?.map((e,i)=><p dir="auto" key={i}>{e.representation||t('Equation content requires manual review.')}</p>)}</details>)}
 </section>)}</section>)}</section>
}
export function CompletedImport({receipt,t}){return <p>{receipt.original_parsed_count??'\u2014'} {t('Questions detected')} / {receipt.excluded_count??'\u2014'} {t('Excluded')} / {receipt.imported_count} {t('Imported')}</p>}

export default function QuestionsPage() {
  const { sessionId } = useParams(), navigate = useNavigate()
  const { currentWorkspace } = useWorkspace()
  const { t, direction, label } = useCopy()
  const institutionId = currentWorkspace.institution.id
  const subjectRequest = useRef(null)
  const keyRequest = useRef(null)
  useEffect(()=>{setBusy(false);return()=>{keyRequest.current?.abort();keyRequest.current=null}},[institutionId,sessionId])
  useEffect(() => () => subjectRequest.current?.abort(),[institutionId,sessionId])
  const [kind, setKind] = useState(null), [preview, setPreview] = useState(null), [busy,setBusy] = useState(false)
  const [error,setError] = useState(''), [success,setSuccess] = useState(null), [questions,setQuestions] = useState(null), [subjects,setSubjects] = useState([]), [revision,setRevision] = useState(0), [recent,setRecent] = useState([]), [loadingSession,setLoadingSession] = useState(!!sessionId)
  useEffect(() => {
    const controller = new AbortController()
    setSubjects([]);setRecent([]);setQuestions(null);setError('')
    Promise.all([loadBankQuestions(institutionId,controller.signal),staffApiFetch(`questions/import/docx/preview/?institution=${institutionId}`,{signal:controller.signal})]).then(([q,s]) => {if(controller.signal.aborted)return;setQuestions(q);setSubjects(s.subjects);setRecent(s.recent_imports || [])}).catch(e => {if(e.name!=='AbortError')setError(t('We could not complete this request. Please retry.'))})
    return () => controller.abort()
  },[institutionId,revision])
  useEffect(() => {
    const controller = new AbortController()
    setPreview(null);setError('');setLoadingSession(!!sessionId)
    if (sessionId) setSuccess(null)
    if (sessionId) staffApiFetch(`questions/import/docx/${sessionId}/`,{signal:controller.signal})
      .then(data => {if(controller.signal.aborted)return;if (data.status === 'completed') setSuccess(data);else setPreview(data)})
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
    if (kind === 'docx' && !subjects.some(subject => String(subject.id) === data.get('subject'))) { setError(t('Select or create a subject before importing.')); return }
    await run(async () => {
      const result = await staffApiFetch(kind==='docx' ? 'questions/import/docx/preview/' : 'questions/import/',{method:'POST',body:data})
      if(kind==='docx')navigate(`/app/questions/import/word/${result.import_session_id}`);else{setSuccess(result.imported_rows);setRevision(v=>v+1)}
    })
  }
  function review(changes) {return run(async () => setPreview(await staffApiFetch(`questions/import/docx/${preview.import_session_id}/`,{method:'PATCH',body:{revision:preview.revision,...changes}})))}
  async function updateKey(action, apply=true) {
    keyRequest.current?.abort()
    const controller=new AbortController();keyRequest.current=controller;setBusy(true);setError('')
    try{const result=await action(controller.signal);if(controller.signal.aborted)return null;if(result && apply)setPreview(result);return result}
    catch(error){if(error.name==='AbortError')return null;throw error}
    finally{if(keyRequest.current===controller){keyRequest.current=null;setBusy(false)}}
  }
  async function deleteImport(item) {
    try{const result=await updateKey(signal=>manageImportAction(item,'delete',{signal,t}),false);if(result?.deleted)returnToBank()}
    catch(error){setError(importError(error,t))}
  }
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
  function confirm() {return run(async () => {const r = await staffApiFetch(`questions/import/docx/${preview.import_session_id}/confirm/`,{method:'POST',body:{revision:preview.revision}});setSuccess(r);setPreview(null)})}
  return <div className="question-bank" dir={direction}><h1>{t('Questions')}</h1>{error && <div role="alert">{error}<button onClick={() => setRevision(v=>v+1)}>{t('Retry')}</button></div>}
    {sessionId && <button onClick={returnToBank}>{t('Return to Question Bank')}</button>}
    {loadingSession ? <p role="status">{t('Loading…')}</p> : sessionId && !preview && success===null && error ? <p>{t('Retry')}</p> : success!==null ? <section role="status"><h2>{success === 'completed' ? t('Import completed') : label(`${typeof success === 'object' ? success.imported_count : success} questions imported as drafts.`, `تم استيراد ${typeof success === 'object' ? success.imported_count : success} سؤالًا كمسودات.`)}</h2>{typeof success === 'object' && <CompletedImport receipt={success} t={t}/>}<button onClick={returnToBank}>{t('View Question Bank')}</button></section> : preview ? <ImportReview key={`${institutionId}:${preview.import_session_id}`} preview={preview} t={t} busy={busy} subjects={subjects} onCreateSubject={createSubject} onDelete={deleteImport} onKeyRemove={()=>updateKey(signal=>manageImportAction(preview,'remove_key',{signal,t}))} onKeyUpload={(file,options)=>updateKey(signal=>uploadAnswerKey(preview,file,{...options,signal}))} onKeySave={(entry,changes)=>updateKey(signal=>saveAnswerMatch(preview,entry,changes,{signal}))} onTemplate={()=>updateKey(signal=>downloadAnswerTemplate(preview,{signal}),false)} onClassify={(block,classification)=>updateKey(signal=>classifyImportBlock(preview,block,classification,{signal}))} onChange={review} onConfirm={confirm} onCancel={returnToBank} /> : <>
      <div className="import-actions"><strong>{t('Import Questions')}</strong><button onClick={() => setKind('csv')}>{t('CSV')}</button><button onClick={() => setKind('docx')}>{t('Word document')}</button></div>
      {kind === 'docx' && <p>{t('New imports can be resumed for 7 days. Save each review change.')}</p>}
      <ImportCards imports={recent} t={t} busy={busy} onContinue={id=>navigate(`/app/questions/import/word/${id}`)} onDelete={deleteImport}/>
      {questions !== null && subjects.length === 0 && <SubjectEmptyState t={t} />}
      {kind && <form className="import-upload" onSubmit={upload}>{kind==='docx' && <><h2>{t('Import Questions from Word')}</h2><ImportModeChoice t={t} busy={busy}/><label>{t('Subject')}<select name="subject" required disabled={busy || subjects.length === 0}><option value="">{t('Select a subject')}</option>{subjects.map(subject => <option key={subject.id} value={subject.id}>{subject.name}</option>)}</select></label></>}<label>{t(kind==='docx'?'Word document':'CSV')}<input required name="file" type="file" accept={kind==='docx'?'.docx':'.csv'} disabled={busy} /></label><button disabled={busy || (kind==='docx' && subjects.length === 0)}>{t(busy?'Processing…':'Upload')}</button><button type="button" disabled={busy} onClick={() => setKind(null)}>{t('Cancel')}</button></form>}
      {questions===null ? <p>{t('Loading\u2026')}</p> : <QuestionBank questions={questions} subjects={subjects} t={t}/>}
    </>}{busy && preview && <p role="status">{t('Processing…')}</p>}</div>
}
