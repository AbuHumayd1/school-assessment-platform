import { staffApiFetch } from '../../services/api.js'
import { useState } from 'react'

export const importWorkflowCopy = {
  'Process Questions':'معالجة الأسئلة', 'Questions document':'مستند الأسئلة',
  'Choose both documents, then process the questions and answers together.':'اختر المستندين، ثم عالج الأسئلة والإجابات معًا.',
  'Resume previous import':'استئناف استيراد سابق', 'Continue import':'متابعة الاستيراد',
  'Needs attention':'يحتاج إلى انتباه', 'Questions needing attention':'أسئلة تحتاج إلى انتباه',
  'Correct the question below, or exclude it before importing.':'صحح السؤال أدناه، أو استبعده قبل الاستيراد.',
  'Review question':'مراجعة السؤال', 'Choose a questions document.':'اختر مستند الأسئلة.',
  'Questions processed, but the answer key could not be added. Add it below to continue.':'عُولجت الأسئلة، لكن تعذر إضافة مفتاح الإجابة. أضفه أدناه للمتابعة.',
  'You can leave and resume this review later.':'يمكنك المغادرة واستئناف هذه المراجعة لاحقًا.',
  'This import is unavailable. It may have expired.':'هذا الاستيراد غير متاح. ربما انتهت صلاحيته.',
  'This removes the documents and saved review for this import. No Question Bank questions will be deleted.':'سيُحذف المستندان والمراجعة المحفوظة لهذا الاستيراد. لن تُحذف أي أسئلة من بنك الأسئلة.',
  'Imports':'عمليات الاستيراد', 'Continue':'متابعة', 'Unfinished':'غير مكتمل', 'Last updated':'آخر تحديث',
  'Upload → Check → Import':'رفع ← مراجعة ← استيراد',
  'Upload Questions → Add Answers → Check → Import':'رفع الأسئلة ← إضافة الإجابات ← مراجعة ← استيراد',
  'Review Questions':'مراجعة الأسئلة',
  'Import Questions from Word':'استيراد الأسئلة من Word', 'How are answers provided?':'كيف تُقدَّم الإجابات؟',
  'Questions with answers embedded':'أسئلة بإجابات مضمنة', 'Questions + separate answer key':'أسئلة مع مفتاح إجابة منفصل',
  'The question document already contains its answer key.':'يحتوي مستند الأسئلة على مفتاح الإجابة.',
  'Upload the question document first, then add a DOCX, XLSX or CSV answer key.':'ارفع مستند الأسئلة أولاً، ثم أضف مفتاح إجابة بصيغة DOCX أو XLSX أو CSV.',
  'Embedded Answer Key':'مفتاح إجابة مضمن', 'Separate Answer Key':'مفتاح إجابة منفصل',
  'Embedded in question document':'مضمن في مستند الأسئلة', 'No answer key uploaded.':'لم يُرفع مفتاح إجابة.',
  'Upload Questions → Review → Confirm':'رفع الأسئلة ← المراجعة ← التأكيد',
  'Upload Questions → Review Questions → Answer Key → Final Review → Confirm':'رفع الأسئلة ← مراجعة الأسئلة ← مفتاح الإجابة ← المراجعة النهائية ← التأكيد',
  'Delete Import':'حذف الاستيراد', 'Remove Answer Key':'إزالة مفتاح الإجابة',
  'Delete this import?':'هل تريد حذف هذا الاستيراد؟',
  'This will permanently remove this unfinished import and its temporary review state and media. No Question Bank questions will be deleted.':'سيُحذف هذا الاستيراد غير المكتمل وحالة المراجعة والوسائط المؤقتة نهائيًا. لن تُحذف أي أسئلة من بنك الأسئلة.',
  'Remove this answer key? Automatic key answers will be removed. Saved manual and embedded answers will be kept.':'هل تريد إزالة مفتاح الإجابة؟ ستُزال إجابات المفتاح التلقائية مع الاحتفاظ بالإجابات اليدوية والمضمنة.',
  'Replace the current answer key? Old automatic matches will be removed. Saved manual answers will be kept.':'هل تريد استبدال مفتاح الإجابة الحالي؟ ستُزال المطابقات التلقائية السابقة مع الاحتفاظ بالإجابات اليدوية المحفوظة.',
  'Upload a separate answer key or explicitly review the correct answers.':'ارفع مفتاح إجابة منفصلاً أو راجع الإجابات الصحيحة واعتمدها صراحةً.',
  'This import uses embedded answers. Start a separate-key import to upload a key.':'يستخدم هذا الاستيراد إجابات مضمنة. ابدأ استيرادًا بمفتاح منفصل لرفع مفتاح إجابة.',
  'No unfinished imports.':'لا توجد عمليات استيراد غير مكتملة.',
  'Embedded answers missing or invalid? Correct the affected questions manually before confirming.':'هل توجد إجابات مضمنة مفقودة أو غير صالحة؟ صحح الأسئلة المتأثرة يدويًا قبل التأكيد.',
  'Import mode is fixed for this session. Start a new import to use another mode.':'وضع الاستيراد ثابت لهذه الجلسة. ابدأ استيرادًا جديدًا لاستخدام وضع آخر.',
  'Delete the current server preview revision.':'أعد تحميل المراجعة الحالية قبل حذف الاستيراد.',
  'Remove the key from the current server preview revision.':'أعد تحميل المراجعة الحالية قبل إزالة المفتاح.',
  'Choose embedded answers or a separate answer key.':'اختر إجابات مضمنة أو مفتاح إجابة منفصلاً.',
  'Answer-key section is unknown or ambiguous; correct affected answers manually.':'قسم مفتاح الإجابة غير معروف أو ملتبس؛ صحح الإجابات المتأثرة يدويًا.',
  'Answer-key section is ambiguous; correct affected answers manually.':'قسم مفتاح الإجابة ملتبس؛ صحح الإجابات المتأثرة يدويًا.',
  'Invalid or unsupported embedded answer; correct the affected question manually.':'إجابة مضمنة غير صالحة أو غير مدعومة؛ صحح السؤال المتأثر يدويًا.',
}

export function sessionMode(preview) {
  return preview.import_mode || (preview.separate_answer_key ? 'separate_key' : 'embedded_key')
}
export const modeLabel = mode => mode === 'separate_key' ? 'Separate Answer Key' : 'Embedded Answer Key'

export function ImportModeChoice({t,busy,mode,onChange}) {
  return <fieldset disabled={busy} className="import-mode-choice"><legend>{t('How are answers provided?')}</legend>
    <label><input required type="radio" name="import_mode" value="embedded_key" checked={mode === undefined ? undefined : mode === 'embedded_key'} onChange={onChange ? () => onChange('embedded_key') : undefined}/>{t('Questions with answers embedded')}<span>{t('The question document already contains its answer key.')}</span></label>
    <label><input required type="radio" name="import_mode" value="separate_key" checked={mode === undefined ? undefined : mode === 'separate_key'} onChange={onChange ? () => onChange('separate_key') : undefined}/>{t('Questions + separate answer key')}<span>{t('Choose both documents, then process the questions and answers together.')}</span></label>
  </fieldset>
}

export function WordImportFields({subjects,t,busy,mode,onModeChange}) {
  return <><label>{t('Subject')}<select name="subject" required disabled={busy || subjects.length === 0} defaultValue=""><option value="">{t('Select a subject')}</option>{subjects.map(subject => <option key={subject.id} value={subject.id}>{subject.name}</option>)}</select></label>
    <ImportModeChoice t={t} busy={busy} mode={mode} onChange={onModeChange}/>
    <label>{t('Questions document')}<input required name="file" type="file" accept=".docx" disabled={busy}/></label>
    {mode === 'separate_key' && <label>{t('Answer Key')}<input required name="answer_key_file" type="file" accept=".docx,.xlsx,.csv" disabled={busy}/><small>{t('Use a DOCX, XLSX or CSV answer key up to 2 MB.')}</small></label>}
    <button disabled={busy || subjects.length === 0}>{t(busy ? 'Processing…' : 'Process Questions')}</button></>
}

export function WordImportForm({subjects,t,busy,onSubmit,onCancel}) {
  const [mode,setMode] = useState('')
  return <form className="import-upload" onSubmit={onSubmit}><h2>{t('Import Questions from Word')}</h2><WordImportFields subjects={subjects} t={t} busy={busy} mode={mode} onModeChange={setMode}/><button type="button" disabled={busy} onClick={onCancel}>{t('Cancel')}</button></form>
}

export function ImportWorkflowHeading({preview,t}) {
  return <div><h3>{t(modeLabel(sessionMode(preview)))}</h3><p>{t('Review Questions')}</p></div>
}

export function ImportCards({imports,t,busy,onContinue,onDelete}) {
  const resumable = imports.filter(item => item.status !== 'completed')
  if (!resumable.length) return null
  return <details className="import-list"><summary>{t('Resume previous import')} ({resumable.length})</summary>{resumable.map(item=><article className="import-question" key={item.import_session_id}>
    <h3><bdi>{item.filename || t('Word document')}</bdi></h3>
    {item.subject_name && <p>{t('Subject')}: <bdi>{item.subject_name}</bdi></p>}
    <p>{item.questions_detected} {t('Questions detected')} · {item.summary?.ready_count ?? '—'} {t('Ready')} · {(item.summary?.review_count || 0) + (item.summary?.error_count || 0)} {t('Needs attention')}</p>
    <p>{t('Last updated')}: <bdi>{new Date(item.updated_at || item.created_at).toLocaleString()}</bdi></p>
    <div className="import-actions"><button disabled={busy} onClick={()=>onContinue(item.import_session_id)}>{t('Continue import')}</button><button disabled={busy} onClick={()=>onDelete(item)}>{t('Delete Import')}</button></div>
  </article>)}</details>
}

export function confirmKeyReplacement(preview,t,confirm=message=>window.confirm(message)) {
  return !preview.separate_answer_key || confirm(t('Replace the current answer key? Old automatic matches will be removed. Saved manual answers will be kept.'))
}

export async function manageImportAction(preview,action,{t=s=>s,confirm=message=>window.confirm(message),fetcher=staffApiFetch,signal}={}) {
  if(action!=='remove_key' && action!=='delete')throw new Error('Unsupported import action')
  const message=action==='remove_key'?'Remove this answer key? Automatic key answers will be removed. Saved manual and embedded answers will be kept.':'Delete this import?'
  const explanation=action==='delete'?'\n\n'+t('This removes the documents and saved review for this import. No Question Bank questions will be deleted.'):' '
  if(!confirm(t(message)+explanation))return null
  const path=`questions/import/docx/${preview.import_session_id}/${action==='remove_key'?'answer-key/':''}`
  const result=await fetcher(path,{method:'DELETE',body:{revision:preview.revision},signal})
  return action==='delete'?{deleted:true}:result
}
