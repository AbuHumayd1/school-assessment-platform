import { staffApiFetch } from '../../services/api.js'

export const importWorkflowCopy = {
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

export function ImportModeChoice({t,busy}) {
  return <fieldset disabled={busy} className="import-mode-choice"><legend>{t('How are answers provided?')}</legend>
    <label><input required type="radio" name="import_mode" value="embedded_key"/>{t('Questions with answers embedded')}<span>{t('The question document already contains its answer key.')}</span></label>
    <label><input required type="radio" name="import_mode" value="separate_key"/>{t('Questions + separate answer key')}<span>{t('Upload the question document first, then add a DOCX, XLSX or CSV answer key.')}</span></label>
  </fieldset>
}

export function ImportWorkflowHeading({preview,t}) {
  const separate=sessionMode(preview)==='separate_key'
  return <div><h3>{t(modeLabel(sessionMode(preview)))}</h3><p>{t(separate?'Upload Questions → Add Answers → Check → Import':'Upload → Check → Import')}</p></div>
}

export function ImportCards({imports,t,busy,onContinue,onDelete}) {
  return <section className="import-list"><h2>{t('Imports')}</h2>{!imports.length && <p>{t('No unfinished imports.')}</p>}{imports.map(item=><article className="import-question" key={item.import_session_id}>
    <h3><bdi>{item.filename || t('Word document')}</bdi></h3><p>{t(modeLabel(item.import_mode))} · {t(item.status==='completed'?'Import completed':'Unfinished')}</p>
    {item.subject_name && <p>{t('Subject')}: <bdi>{item.subject_name}</bdi></p>}
    <p>{item.questions_detected} {t('Questions detected')} / {item.summary?.ready_count ?? '—'} {t('Ready')} / {item.summary?.review_count ?? '—'} {t('Needs review')} / {item.summary?.error_count ?? '—'} {t('Errors')}</p>
    <p>{item.summary?.answers_matched ?? '—'} {t('Answers matched')} / {item.summary?.answers_missing ?? '—'} {t('Missing answers')}</p>
    <p>{t('Answer Key')}: {item.import_mode==='separate_key' ? <bdi>{item.answer_key_document?.filename || t('No answer key uploaded.')}</bdi> : t('Embedded in question document')}</p>
    <p>{t('Last updated')}: <bdi>{new Date(item.updated_at || item.created_at).toLocaleString()}</bdi></p>
    <div className="import-actions"><button disabled={busy} onClick={()=>onContinue(item.import_session_id)}>{t('Continue')}</button>{item.status!=='completed' && <button disabled={busy} onClick={()=>onDelete(item)}>{t('Delete Import')}</button>}</div>
  </article>)}</section>
}

export function confirmKeyReplacement(preview,t,confirm=message=>window.confirm(message)) {
  return !preview.separate_answer_key || confirm(t('Replace the current answer key? Old automatic matches will be removed. Saved manual answers will be kept.'))
}

export async function manageImportAction(preview,action,{t=s=>s,confirm=message=>window.confirm(message),fetcher=staffApiFetch,signal}={}) {
  if(action!=='remove_key' && action!=='delete')throw new Error('Unsupported import action')
  const message=action==='remove_key'?'Remove this answer key? Automatic key answers will be removed. Saved manual and embedded answers will be kept.':'Delete this import?'
  const explanation=action==='delete'?'\n\n'+t('This will permanently remove this unfinished import and its temporary review state and media. No Question Bank questions will be deleted.'):' '
  if(!confirm(t(message)+explanation))return null
  const path=`questions/import/docx/${preview.import_session_id}/${action==='remove_key'?'answer-key/':''}`
  const result=await fetcher(path,{method:'DELETE',body:{revision:preview.revision},signal})
  return action==='delete'?{deleted:true}:result
}
