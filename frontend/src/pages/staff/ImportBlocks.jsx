import { staffApiFetch } from '../../services/api.js'
import { useState } from 'react'

export const reconciliationCopy = {
  'Your import is ready': 'الاستيراد جاهز',
  'Import details': 'تفاصيل الاستيراد',
  'Questions found': 'الأسئلة المكتشفة',
  'No issues found': 'لم يُعثر على مشكلات',
  'Items needing attention': 'عناصر تحتاج إلى انتباه',
  'Additional issues': 'مشكلات إضافية',
  'Import Questions': 'استيراد الأسئلة',
  'We need your help with one part of the document.': 'نحتاج إلى مساعدتك في جزء من المستند.',
  'What are these numbered items?': 'ما نوع هذه العناصر المرقمة؟',
  'Choose an option': 'اختر خيارًا',
  'Check document content': 'مراجعة محتوى المستند',
  'Review document section': 'مراجعة جزء المستند',
  'Check this part against your Word file.': 'راجع هذا الجزء مقابل ملف Word.',
  'This import has changed. Refresh it and try again.': 'تغيّر هذا الاستيراد. حدّثه وحاول مرة أخرى.',
  'Check your column choices and refresh this import before trying again.': 'راجع اختيارات الأعمدة وحدّث هذا الاستيراد قبل المحاولة مرة أخرى.',
  'I checked this content against my Word file.': 'راجعت هذا المحتوى مقابل ملف Word.',
  'Answers matched': 'الإجابات المطابقة',
  'Answers need your attention': 'إجابات تحتاج إلى انتباه',
  'Check answers': 'مراجعة الإجابات',
  'Tell us which columns contain:': 'حدد الأعمدة التي تحتوي على:',
  'We could not determine which question this answer belongs to.': 'تعذر تحديد السؤال الذي تنتمي إليه هذه الإجابة.',
  'This answer does not match the available options.': 'هذه الإجابة لا تطابق الخيارات المتاحة.',
  'This answer differs from the saved answer. Check which is correct.': 'تختلف هذه الإجابة عن الإجابة المحفوظة. تحقق من الإجابة الصحيحة.',
  'Tell us whether the highlighted document parts contain questions or answers, or should be ignored.': 'حدد ما إذا كانت الأجزاء المميزة تحتوي على أسئلة أو إجابات أو يجب تجاهلها.',
  'Check the highlighted document content against your Word file, then confirm that you have reviewed it.': 'راجع محتوى المستند المميز مقابل ملف Word ثم أكد أنك راجعته.',
  'Source blocks': 'كتل المستند',
  'Classify uncertain numbered blocks before confirming.': 'صنّف الكتل المرقمة غير المؤكدة قبل التأكيد.',
  'Questions': 'الأسئلة', 'Answer Key': 'مفتاح الإجابة', 'Ignore': 'تجاهل',
  'Classification': 'التصنيف', 'Link Answer': 'ربط الإجابة', 'Relink Answer': 'إعادة ربط الإجابة',
  'Download Answer Key Template': 'تنزيل قالب مفتاح الإجابة',
  'Upload Existing Answer Key': 'رفع مفتاح إجابة موجود',
  'For the most reliable matching, download this template, enter the correct answers, and upload it here.': 'للحصول على المطابقة الأكثر موثوقية، نزّل هذا القالب وأدخل الإجابات الصحيحة ثم ارفعه هنا.',
  'Missing answer': 'إجابة مفقودة', 'Ambiguous': 'غير محدد',
  'Matching reason': 'سبب المطابقة', 'Save authoritative answer': 'حفظ الإجابة المعتمدة',
  'Embedded answer reconciliation': 'مطابقة الإجابات المضمنة',
  'Excluded key entries': 'إدخالات المفتاح المستبعدة',
  'section_identity_not_found': 'لم يُعثر على معرّف القسم',
  'section_title_not_found': 'لم يُعثر على عنوان القسم',
  'section_title_ambiguous': 'عنوان القسم غير محدد',
  'section_missing_and_number_not_global_unique': 'القسم مفقود ورقم السؤال مكرر',
  'multiple_candidate_questions': 'توجد عدة أسئلة محتملة',
  'question_number_not_found': 'لم يُعثر على رقم السؤال',
  'invalid_answer_label': 'الإجابة لا تطابق الخيارات',
  'option_text_not_unique': 'نص الخيار غير فريد',
  'conflicting_existing_answer': 'تعارض مع الإجابة الموجودة',
  'unknown_or_foreign_question_id': 'معرّف السؤال غير معروف أو يخص جلسة أخرى',
  'linked_question_not_found': 'لم يُعثر على السؤال المرتبط',
  'Unknown, foreign or duplicate Question ID. Use the template for this import session.': 'معرّف السؤال غير معروف أو مكرر أو يخص جلسة أخرى. استخدم قالب جلسة الاستيراد هذه.',
  'Choose Questions, Answer Key or Ignore.': 'اختر الأسئلة أو مفتاح الإجابة أو التجاهل.',
  'Select a block from this import session.': 'اختر كتلة من جلسة الاستيراد هذه.',
  'The answer key exceeds the entry limit.': 'يتجاوز مفتاح الإجابة الحد المسموح للإدخالات.',
  'The question collection exceeds the import limit.': 'تتجاوز مجموعة الأسئلة الحد المسموح للاستيراد.',
  'Answer-key object requires manual review.': 'يحتاج العنصر في مفتاح الإجابة إلى مراجعة يدوية.',
  'Unrecognized answer-key table row.': 'صف غير معروف في جدول مفتاح الإجابة.',
  'Answer-key table requires source review.': 'يتطلب جدول مفتاح الإجابة مراجعة المصدر.',
  'Unrecognized answer-key paragraph; review the source block.': 'فقرة غير معروفة في مفتاح الإجابة؛ راجع كتلة المصدر.',
  'Embedded answer entry requires reconciliation.': 'يتطلب إدخال الإجابة المضمنة مطابقة يدوية.',
}

export function importMessage(message) {
  if (['Delete the current server preview revision.', 'Remove the key from the current server preview revision.', 'Confirm the current server preview revision.'].includes(message)) return 'This import has changed. Refresh it and try again.'
  if (message==='Use the current revision and valid column mapping.') return 'Check your column choices and refresh this import before trying again.'
  return message
}

export function blockError(error,t) {
  const flatten=value=>typeof value==='string'?[value]:Array.isArray(value)?value.flatMap(flatten):value&&typeof value==='object'?Object.values(value).flatMap(flatten):[]
  const messages=flatten(error.data)
  return messages.length?messages.map(message=>t(importMessage(message))).join(' '):t(importMessage(error.message))
}

export function classifyImportBlock(preview, blockId, classification, {signal, fetcher=staffApiFetch}={}) {
  return fetcher(`questions/import/docx/${preview.import_session_id}/blocks/${blockId}/classification/`, {
    method:'PATCH', body:{revision:preview.revision, classification}, signal,
  })
}

export default function ImportBlocks({preview,t,busy,onClassify}) {
  const [error,setError]=useState('')
  async function classify(id,value){
    setError('')
    try{await onClassify(id,value)}catch(error){setError(blockError(error,t))}
  }
  if (!preview.blocks?.length || !onClassify) return null
  const needsHelp=preview.blocks.some(b=>b.needs_classification)
  return <details id="import-document-parts" className="import-blocks" open={needsHelp}>
    <summary>{t(needsHelp?'We need your help with one part of the document.':'Import details')}</summary>
    {error && <p role="alert">{error}</p>}
    {preview.blocks.map(block=><div className="import-block" key={block.id}>
      <strong><bdi>{block.title}</bdi></strong>
      <span>{block.section?.questions.length ?? block.entries?.length ?? 0}</span>
      {block.needs_classification && <p>{t('What are these numbered items?')}</p>}
      <label>{t(block.needs_classification?'What are these numbered items?':'Classification')}<select disabled={busy} value={block.needs_classification?'':block.classification} onChange={e=>classify(block.id,e.target.value)}>
        {block.needs_classification && <option value="" disabled>{t('Choose an option')}</option>}
        {[['questions','Questions'],['answer_key','Answer Key'],['ignore','Ignore']].map(([value,label])=><option key={value} value={value}>{t(label)}</option>)}
      </select></label>
      {block.section?.questions.slice(0,3).map(q=><p dir="auto" key={q.id}>Q{q.source_number} · {q.text.slice(0,160)}</p>)}
      {block.uncertain && block.unparsed?.slice(0,3).map((item,i)=><p dir="auto" key={`raw-${i}`}>{item.text}</p>)}
    </div>)}
  </details>
}
