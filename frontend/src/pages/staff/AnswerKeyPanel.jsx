import { useRef, useState } from 'react'
import { staffApiFetch } from '../../services/api.js'
import { reconciliationCopy, importMessage } from './ImportBlocks.jsx'
import { confirmKeyReplacement } from './ImportWorkflow.jsx'

export const answerKeyCopy = {
  'Add an answer key for these questions, then review before importing. Questions are created only after confirmation.':'أضف مفتاح إجابة لهذه الأسئلة، ثم راجعها قبل الاستيراد. لا تُنشأ الأسئلة إلا بعد التأكيد.',
  ...reconciliationCopy,
  'Answer Key':'مفتاح الإجابة', 'Upload Answer Key':'رفع مفتاح الإجابة', 'Replace Answer Key':'استبدال مفتاح الإجابة',
  'Upload a separate key to this review session. Questions are created only after confirmation.':'ارفع مفتاحًا منفصلًا إلى جلسة المراجعة. لا تُنشأ الأسئلة إلا بعد التأكيد.',
  'Use a DOCX, XLSX or CSV answer key up to 2 MB.':'استخدم مفتاح إجابة بصيغة DOCX أو XLSX أو CSV بحجم لا يتجاوز 2 ميغابايت.',
  'Use a DOCX, XLSX or CSV answer key.':'استخدم مفتاح إجابة بصيغة DOCX أو XLSX أو CSV.',
  'Choose an answer-key file.':'اختر ملف مفتاح الإجابة.',
  'This answer key is invalid, unsafe or exceeds the import limits.':'مفتاح الإجابة غير صالح أو غير آمن أو يتجاوز حدود الاستيراد.',
  'Formula cells are not supported in answer keys.':'لا تُدعم خلايا الصيغ في مفاتيح الإجابة.',
  'The answer key exceeds the row, column or cell limits.':'يتجاوز مفتاح الإجابة حدود الصفوف أو الأعمدة أو الخلايا.',
  'Select the answer-key columns.':'حدد أعمدة مفتاح الإجابة.',
  'Select a populated answer-key worksheet.':'اختر ورقة عمل تحتوي على بيانات مفتاح الإجابة.',
  'Use distinct valid column indexes.':'اختر أعمدة صالحة ومختلفة.',
  'The answer does not uniquely match the selected question options.':'لا تطابق الإجابة خيارات السؤال المحدد بشكل فريد.',
  'Select the intended question before resolving the answer.':'اختر السؤال المقصود قبل تحديد الإجابة المعتمدة.',
  'Select a question from this import session.':'اختر سؤالًا من جلسة الاستيراد هذه.',
  'The answer-key request could not be completed.':'تعذر إكمال طلب مفتاح الإجابة.',
  'Matched':'مطابق', 'Unmatched':'غير مطابق', 'Ambiguous':'ملتبس', 'Invalid answer':'إجابة غير صالحة', 'Duplicate':'مكرر', 'Conflicts':'تعارضات',
  'Answer key entries':'إدخالات مفتاح الإجابة', 'Questions missing valid answers':'أسئلة دون إجابات صالحة', 'Match status':'حالة المطابقة',
  'Existing answer':'الإجابة الحالية', 'Reviewed answer':'الإجابة بعد المراجعة', 'Imported answer':'الإجابة المستوردة',
  'Intended question':'السؤال المقصود', 'Select a question':'اختر سؤالًا', 'Authoritative answer':'الإجابة المعتمدة',
  'Save answer match':'حفظ مطابقة الإجابة', 'Resolve conflict':'حل التعارض', 'Exclude key entry':'استبعاد إدخال المفتاح', 'Restore key entry':'استعادة إدخال المفتاح',
  'Agrees with the existing answer':'يتفق مع الإجابة الحالية', 'Resolved by manual review':'تم الحل بالمراجعة اليدوية',
  'Use option letters, exact option text, or True/False. Multiple-select answers may use A,C.':'استخدم حروف الخيارات أو نص الخيار المطابق تمامًا أو True/False. يمكن استخدام A,C للاختيار المتعدد.',
  'Possible questions; select the intended source question.':'أسئلة محتملة؛ اختر السؤال المقصود من المصدر.',
  'Replacement removes old automatic matches and keeps saved manual answers.':'يزيل الاستبدال المطابقات التلقائية السابقة ويحافظ على الإجابات اليدوية المحفوظة.',
  'Resolve or exclude every unresolved answer-key entry.':'حل أو استبعد كل إدخال غير محسوم في مفتاح الإجابة.',
  'No matching key entries':'لا توجد إدخالات مفتاح مطابقة', 'Worksheet':'ورقة العمل', 'Select a worksheet':'اختر ورقة عمل',
  'Map answer-key columns':'تحديد أعمدة مفتاح الإجابة', 'Question Number':'رقم السؤال', 'Answer':'الإجابة', 'Section':'القسم',
  'Change answer':'تغيير الإجابة', 'Save answer':'حفظ الإجابة', 'Match Answer':'مطابقة الإجابة', 'Change match':'تغيير المطابقة',
  'Correct answer':'الإجابة الصحيحة',
  'Add Answers':'إضافة الإجابات', 'Answer files and template':'ملفات الإجابات والقالب',
  'Unrecognized answer-key paragraph.':'فقرة غير معروفة في مفتاح الإجابة.',
  'A valid source question number is required.':'يجب تحديد رقم سؤال مصدر صالح.',
  'The source section identifier exceeds the limit.':'يتجاوز معرف قسم المصدر الحد المسموح.',
  'Extra columns require review; quote comma-separated answers in CSV.':'تحتاج الأعمدة الإضافية إلى مراجعة؛ ضع الإجابات المفصولة بفواصل بين علامتي اقتباس في CSV.',
}

export const answerKeyStates = {matched:'Matched',unmatched:'Unmatched',ambiguous:'Ambiguous',invalid_answer:'Invalid answer',duplicate:'Duplicate',conflict:'Conflicts',excluded:'Excluded'}
const needsReview = new Set(['unmatched','ambiguous','invalid_answer','duplicate','conflict'])

export function supportedAnswerKey(file) {
  return !!file && /\.(docx|xlsx|csv)$/i.test(file.name) && file.size <= 2 * 1024 * 1024
}

export function answerKeyCollection(preview, filter='all', section='') {
  const questions = new Map(preview.sections.flatMap(s=>s.questions.map(q=>[q.id,{section:s,question:q}])))
  return [...(preview.embedded_answer_key?.entries || []),...(preview.separate_answer_key?.entries || [])].map(entry=>({...entry,target:questions.get(entry.question_id)})).filter(entry=>{
    const statusMatches=filter==='all'||filter==='needs_review'&&needsReview.has(entry.status)&&!(entry.status==='duplicate'&&entry.resolved)||filter==='conflict'&&entry.status==='conflict'||filter==='unmatched'&&entry.status==='unmatched'||filter==='matched'&&entry.status==='matched'||filter==='ambiguous'&&entry.status==='ambiguous'
    return statusMatches && (!section || entry.target?.section.id===section || !entry.target && (entry.section_id===section || entry.candidate_ids?.some(id=>questions.get(id)?.section.id===section)))
  })
}

export async function uploadAnswerKey(preview, file, {sheet='',columns=null,signal,fetcher=staffApiFetch}={}) {
  if(!supportedAnswerKey(file))throw new Error('Use a DOCX, XLSX or CSV answer key up to 2 MB.')
  const body=new FormData();body.set('file',file);body.set('revision',preview.revision)
  if(sheet)body.set('sheet',sheet)
  if(columns)body.set('columns',JSON.stringify(columns))
  return fetcher(`questions/import/docx/${preview.import_session_id}/answer-key/`,{method:'POST',body,signal})
}

export function saveAnswerMatch(preview,entryId,changes,{signal,fetcher=staffApiFetch}={}) {
  return fetcher(`questions/import/docx/${preview.import_session_id}/answer-key/matches/${entryId}/`,{method:'PATCH',body:{revision:preview.revision,...changes},signal})
}

function MatchRow({entry,preview,t,busy,onSave}) {
  const [target,setTarget]=useState(entry.question_id || ''),[answer,setAnswer]=useState(entry.answer_override || entry.answer),[error,setError]=useState('')
  const selected=preview.sections.flatMap(s=>s.questions.map(q=>({question:q,section:s}))).find(item=>item.question.id===target)
  async function save(changes){setError('');try{await onSave(entry.id,changes)}catch(e){setError(matchError(e,t))}}
  return <article className="import-question answer-key-match"><header><strong><bdi>{entry.target?.section.source_title || entry.section || '—'}</bdi> · <bdi>{entry.question_number!=null?`Q${entry.question_number}`:entry.raw_question_number || '—'}</bdi></strong><span className={`answer-key-status answer-key-status--${entry.status}`}>{t(answerKeyStates[entry.status])}</span></header>
    {entry.reason && <p>{t(entry.reason==='invalid_answer_label'||entry.reason==='option_text_not_unique'?'This answer does not match the available options.':entry.reason==='conflicting_existing_answer'?'This answer differs from the saved answer. Check which is correct.':'We could not determine which question this answer belongs to.')}</p>}
    {entry.diagnostic && <p>{t(entry.diagnostic)}</p>}{entry.status==='ambiguous' && <p>{entry.candidate_count} {t('Possible questions; select the intended source question.')}</p>}{entry.agreement && <p>{t('Agrees with the existing answer')}</p>}{entry.resolved && <p>{t('Resolved by manual review')}</p>}
    {selected && <><p dir="auto">{selected.question.text}</p><ol>{selected.question.options.map(o=><li key={o.label}><bdi>{o.label} · {o.text}</bdi></li>)}</ol><p>{t('Existing answer')}: <bdi>{formatAnswer(selected.question.answer_baseline ?? selected.question.original?.correct_answer)}</bdi></p><p>{t('Reviewed answer')}: <bdi>{formatAnswer(selected.question.correct_answer)}</bdi></p></>}
    <p>{t('Imported answer')}: <bdi>{entry.answer}</bdi></p>
    {error && <p role="alert">{error}</p>}
    <form onSubmit={e=>{e.preventDefault();save({question_id:target,answer,excluded:false})}}>
      <fieldset disabled={busy || entry.status==='excluded'}><label>{t('Intended question')}<select required value={target} onChange={e=>setTarget(e.target.value)}><option value="">{t('Select a question')}</option>{preview.sections.map(s=><optgroup key={s.id} label={s.source_title}>{s.questions.map(q=><option key={q.id} value={q.id}>Q{q.source_number} · {q.text.slice(0,70)}{!q.included?` (${t('Excluded')})`:''}</option>)}</optgroup>)}</select></label>
      <button type="button" disabled={!target} onClick={()=>save({question_id:target,excluded:false})}>{entry.linked_question_id?t('Change match'):t('Match Answer')}</button>
      <details open={entry.status==='conflict'}><summary>{t('Change answer')}</summary><label>{t('Correct answer')}<input required maxLength={1000} dir="auto" value={answer} onChange={e=>setAnswer(e.target.value)}/></label><p>{t('Use option letters, exact option text, or True/False. Multiple-select answers may use A,C.')}</p>
      <button>{entry.status==='conflict'?t('Resolve conflict'):t('Save answer')}</button></details></fieldset>
    </form><button disabled={busy} onClick={()=>save({excluded:entry.status!=='excluded'})}>{entry.status==='excluded'?t('Restore key entry'):t('Exclude key entry')}</button>
  </article>
}

export function formatAnswer(value){return Array.isArray(value)?value.join(', '):value || '—'}

export function matchError(error,t){
  const flatten=value=>typeof value==='string'?[value]:Array.isArray(value)?value.flatMap(flatten):value&&typeof value==='object'?Object.values(value).flatMap(flatten):[]
  const messages=flatten(error.data?.file || error.data?.answer || error.data?.question_id || error.data?.detail)
  return messages.length?messages.map(message=>t(importMessage(message))).join(' '):t(importMessage(error.message || 'The answer-key request could not be completed.'))
}

export function downloadAnswerTemplate(preview,{signal,fetcher=staffApiFetch}={}) {
  return fetcher(`questions/import/docx/${preview.import_session_id}/answer-key-template/`,{signal,responseType:'blob'})
}

export default function AnswerKeyPanel({preview,t,busy,onUpload,onSave,onRemove,onTemplate,initialFilter='needs_review'}) {
  const fileInput=useRef(null)
  const [file,setFile]=useState(null),[sheet,setSheet]=useState(''),[columns,setColumns]=useState(null),[hints,setHints]=useState({}),[error,setError]=useState('')
  const [filter,setFilter]=useState(initialFilter),[section,setSection]=useState(''),[page,setPage]=useState(0)
  const separate=preview.import_mode==='separate_key'||!preview.import_mode && !!onUpload
  const sourceKey=preview.separate_answer_key||preview.embedded_answer_key
  const key=sourceKey && {...sourceKey,summary:preview.reconciliation?{...preview.reconciliation.summary,questions_missing_answer:preview.reconciliation.questions_missing_answer}:sourceKey.summary,parsed_entry_count:(preview.embedded_answer_key?.entries.length||0)+(preview.separate_answer_key?.entries.length||0)},collection=answerKeyCollection(preview,filter,section)
  const current=Math.min(page,Math.max(0,Math.ceil(collection.length/10)-1))
  const matchedQuestions=new Set(answerKeyCollection(preview).filter(e=>e.status==='matched'||e.status==='duplicate'&&e.resolved).map(e=>e.question_id).filter(Boolean)).size
  async function download(){
    setError('')
    try{const blob=await onTemplate();if(!blob)return;const url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='answer-key-template.xlsx';link.click();setTimeout(()=>URL.revokeObjectURL(url),1000)}catch(error){setError(matchError(error,t))}
  }
  async function remove(){
    setError('')
    try{const result=await onRemove();if(result===null)return;setHints({});setFile(null);if(fileInput.current)fileInput.current.value='';setSheet('');setColumns(null);setFilter('needs_review');setSection('');setPage(0)}
    catch(error){setError(matchError(error,t))}
  }
  async function upload(e){
    e.preventDefault();setError('')
    if(!supportedAnswerKey(file)){setError(t('Use a DOCX, XLSX or CSV answer key up to 2 MB.'));return}
    if(!confirmKeyReplacement(preview,t))return
    try{const result=await onUpload(file,{sheet,columns});if(result===null)return;setHints({});setFile(null);if(fileInput.current)fileInput.current.value='';setSheet('');setColumns(null);setFilter('needs_review');setSection('');setPage(0)}
    catch(error){setError(matchError(error,t));setHints({sheets:error.data?.sheets,columns:Array.isArray(error.data?.columns)?error.data.columns:null})}
  }
  return <section className="answer-key-panel"><h3>{t('Answer Key')}</h3><details open={separate&&!preview.separate_answer_key}><summary>{t(separate?(preview.separate_answer_key?'Answer files and template':'Add Answers'):'Import details')}</summary>{separate?<><p>{t('Add an answer key for these questions, then review before importing. Questions are created only after confirmation.')}</p><p>{t('For the most reliable matching, download this template, enter the correct answers, and upload it here.')}</p><button disabled={busy||!onTemplate} onClick={download}>{t('Download Answer Key Template')}</button><h4>{t('Upload Existing Answer Key')}</h4></>:<p>{t('Check answers')}</p>}
    {separate && !preview.separate_answer_key && <p role="status">{t('No answer key uploaded.')}</p>}
    {separate && preview.separate_answer_key && onRemove && <button disabled={busy} onClick={remove}>{t('Remove Answer Key')}</button>}
    {separate && <form onSubmit={upload} className="answer-key-upload"><label>{preview.separate_answer_key?t('Replace Answer Key'):t('Upload Answer Key')}<input ref={fileInput} type="file" accept=".docx,.xlsx,.csv" disabled={busy} onChange={e=>{setFile(e.target.files[0] || null);setHints({});setSheet('');setColumns(null);setError('')}}/></label>
      {hints.sheets && <label>{t('Worksheet')}<select required value={sheet} onChange={e=>setSheet(e.target.value)}><option value="">{t('Select a worksheet')}</option>{hints.sheets.map(name=><option key={name}>{name}</option>)}</select></label>}
      {hints.columns && <fieldset><legend>{t('Tell us which columns contain:')}</legend>{[['number','Question Number'],['answer','Answer'],['section','Section']].map(([field,label])=><label key={field}>{t(label)}<select required={field!=='section'} value={columns?.[field] ?? ''} onChange={e=>setColumns(previous=>{const next={...previous};if(e.target.value==='')delete next[field];else next[field]=Number(e.target.value);return next})}><option value="">—</option>{hints.columns.map((name,index)=><option key={index} value={index}>{name || String(index+1)}</option>)}</select></label>)}</fieldset>}
      <button disabled={busy || !file}>{preview.separate_answer_key?t('Replace Answer Key'):t('Upload Answer Key')}</button></form>}
    {separate && preview.separate_answer_key && <p>{t('Replacement removes old automatic matches and keeps saved manual answers.')}</p>}{error && <p role="alert">{error}</p>}</details>
    {key && <><p><bdi>{key.source_document.filename}</bdi> · <bdi>{key.source_document.file_type.toUpperCase()}</bdi></p><p role="status">{matchedQuestions} / {preview.summary.questions_detected} {t('Answers matched')}{key.summary.blocker_count>0 && <> · {key.summary.blocker_count} {t('Answers need your attention')}</>}</p>
      {key.summary.blocker_count>0 && <p role="alert">{t('Resolve or exclude every unresolved answer-key entry.')}</p>}
      <details open={key.summary.blocker_count>0}><summary>{t('Check answers')}</summary><div className="bank-filters"><label>{t('Match status')}<select value={filter} onChange={e=>{setFilter(e.target.value);setPage(0)}}>{[['all','All'],['matched','Matched'],['needs_review','Needs review'],['ambiguous','Ambiguous'],['unmatched','Unmatched'],['conflict','Conflicts']].map(([value,label])=><option key={value} value={value}>{t(label)}</option>)}</select></label><label>{t('Section title')}<select value={section} onChange={e=>{setSection(e.target.value);setPage(0)}}><option value="">{t('All sections')}</option>{preview.sections.map(s=><option key={s.id} value={s.id}>{s.source_title}</option>)}</select></label></div>
      <p role="status">{collection.length} {t('Answer key entries')}</p>{collection.slice(current*10,current*10+10).map(entry=><MatchRow key={`${entry.source||'key'}:${entry.id}:${preview.revision}`} entry={entry} preview={preview} t={t} busy={busy} onSave={onSave}/>)}
      {!collection.length && <p>{t('No matching key entries')}</p>}{collection.length>10 && <div className="import-actions"><button disabled={current===0} onClick={()=>setPage(current-1)}>{t('Previous')}</button><span>{t('Page')} {current+1} {t('of')} {Math.ceil(collection.length/10)}</span><button disabled={(current+1)*10>=collection.length} onClick={()=>setPage(current+1)}>{t('Next')}</button></div>}
    </details></>}
  </section>
}
