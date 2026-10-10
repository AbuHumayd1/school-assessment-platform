import { useEffect, useRef, useState } from 'react'
import { staffApiFetch } from '../../services/api.js'
import { questionWorkflowActions } from '../../utils/staffCapabilities.js'
import { importMessage } from './ImportBlocks.jsx'

export const questionWorkflowCopy = {
  'Submit for review':'إرسال للمراجعة', 'Approve':'اعتماد', 'Request changes':'طلب تعديلات', 'Archive':'أرشفة',
  'Submit selected for review':'إرسال المحدد للمراجعة', 'Approve selected':'اعتماد المحدد',
  'Approve imported questions':'اعتماد الأسئلة المستوردة',
  'Draft questions will be submitted for review and approved. Questions already in review will be approved directly. Approved questions will then be available for assessments.':'ستُرسل المسودات للمراجعة ثم تُعتمد. ستُعتمد الأسئلة قيد المراجعة مباشرةً. وستتاح الأسئلة المعتمدة للتقييمات.',
  'questions are ready for approval.':'أسئلة جاهزة للاعتماد.', 'questions are ready to be submitted for review.':'أسئلة جاهزة للإرسال للمراجعة.',
  'Already approved questions were left unchanged.':'تُركت الأسئلة المعتمدة مسبقًا دون تغيير.',
  'Retry refresh':'إعادة محاولة التحديث',
  'Retry failed questions':'إعادة محاولة الأسئلة التي تعذر إكمالها',
  'Select question':'اختيار السؤال', 'Select all matching questions':'اختيار جميع الأسئلة المطابقة', 'Clear selection':'إلغاء التحديد',
  'Selection includes all loaded questions matching the current filters with an available workflow action. Changing filters clears selection.':'يشمل التحديد جميع الأسئلة المحملة المطابقة للمرشحات الحالية والتي يتاح لها إجراء. يُلغى التحديد عند تغيير المرشحات.',
  'questions selected':'أسئلة محددة', 'questions submitted for review.':'أسئلة أُرسلت للمراجعة.',
  'questions approved successfully.':'أسئلة اعتُمدت بنجاح.', 'questions returned for changes.':'أسئلة أُعيدت للتعديل.',
  'questions archived.':'أسئلة أُرشفت.', 'questions require attention.':'أسئلة تحتاج إلى انتباه.',
  'Refresh failed. Reload Question Bank before continuing.':'تعذر التحديث. أعد تحميل بنك الأسئلة قبل المتابعة.',
  'These questions do not support this action.':'لا تدعم هذه الأسئلة هذا الإجراء.',
  'Select questions with the same status and an action you can perform.':'اختر أسئلة بالحالة نفسها وإجراء يُسمح لك بتنفيذه.',
  'Archive this approved question? It will no longer be available for new assessments.':'هل تريد أرشفة هذا السؤال المعتمد؟ لن يتاح للتقييمات الجديدة.',
  'Imported questions are saved as Draft. Review and approve them before adding them to an assessment.':'تُحفظ الأسئلة المستوردة كمسودات. راجعها واعتمدها قبل إضافتها إلى تقييم.',
}
const labels = {'submit-for-review':'Submit for review',approve:'Approve','request-changes':'Request changes',archive:'Archive'}
const outcomes = {'submit-for-review':'questions submitted for review.',approve:'questions approved successfully.','request-changes':'questions returned for changes.',archive:'questions archived.'}
export function workflowFailure(error,t) {
  const values=value=>value && typeof value==='object' ? Object.values(value).flatMap(values) : value == null ? [] : [String(value)]
  return values(error.data ?? error.message ?? 'Retry').map(value=>importMessage(value,t)).join(' ')
}

export function selectionReducer(selected, action) {
  if (action.type === 'clear') return []
  if (action.type === 'all') return [...new Set(action.ids)]
  if (action.type === 'success') return selected.filter(id => !action.ids.includes(id))
  return selected.includes(action.id) ? selected.filter(id => id !== action.id) : [...selected,action.id]
}
export function commonQuestionActions(questions, context) {
  if (!questions.length) return []
  if (questions.every(q=>approvalSteps(q,context)!==null) && questions.some(q=>q.status!=='approved')) return ['approve']
  return ['submit-for-review','approve','request-changes'].filter(action => questions.every(q => questionWorkflowActions(context,q).includes(action)))
}
export function approvalSteps(question,context) {
  if (!questionWorkflowActions(context,{...question,status:'review'}).includes('approve')) return null
  if(question.status==='draft') return ['submit-for-review','approve']
  if(question.status==='review') return ['approve']
  return question.status==='approved' ? [] : null
}
export function approvalConfirmation(questions,t) {
  const count=questions.filter(q=>q.status!=='approved').length
  return `${t('Approve')} ${count} ${t('Questions')}?\n\n${t('Draft questions will be submitted for review and approved. Questions already in review will be approved directly. Approved questions will then be available for assessments.')}`
}
export async function transitionQuestions({questions,action,context,signal,fetcher=staffApiFetch,onSuccess=()=>{},onSettled=()=>{}}) {
  const plans=questions.map(q=>action==='approve'?approvalSteps(q,context):questionWorkflowActions(context,q).includes(action)?[action]:null)
  if (!questions.length || plans.some(plan=>plan===null)) throw new Error('These questions do not support this action.')
  const succeeded=[], failed=[], skipped=[]
  for (const question of questions) {
    if (signal?.aborted) break
    const steps=plans[questions.indexOf(question)]
    if(!steps.length){skipped.push(question.id);continue}
    try {
      for(const step of steps){
        if(signal?.aborted) break
        await fetcher(`questions/${question.id}/${step}/?institution=${context.institutionId}`,{method:'POST',body:{},signal})
      }
      if(signal?.aborted) break
      succeeded.push(question.id)
    } catch (error) {
      if (error.name === 'AbortError') break
      failed.push({id:question.id,error})
    }
  }
  if (signal?.aborted) return null
  if (succeeded.length) await onSuccess(succeeded)
  await onSettled()
  return {action,succeeded,failed,skipped}
}

export function QuestionWorkflowControls({question,context,t,busy,onAction}) {
  const domainActions=questionWorkflowActions(context,question)
  const actions=approvalSteps(question,context)?.length ? ['approve',...domainActions.filter(a=>a==='request-changes')] : domainActions
  if (!actions.length) return null
  return <div className="import-actions">{actions.map(action=><button key={action} type="button" disabled={busy} onClick={()=>onAction([question],action)}>{t(labels[action])}</button>)}</div>
}

export function QuestionSelection({question,context,t,busy,selected,onSelect}) {
  if(!questionWorkflowActions(context,question).length || question.status==='approved')return null
  return <input type="checkbox" aria-label={`${t('Select question')} ${question.source_metadata?.question_number ?? question.id}`} disabled={busy} checked={selected} onClick={e=>e.stopPropagation()} onChange={onSelect}/>
}

export function useQuestionWorkflow({context,t,onRefresh,confirm=message=>window.confirm(message)}) {
  const [selected,setSelected]=useState([]), [busy,setBusy]=useState(false), [result,setResult]=useState(null), [error,setError]=useState('')
  const request=useRef(null)
  useEffect(()=>()=>request.current?.abort(),[])
  const select=action=>setSelected(old=>selectionReducer(old,action))
  async function act(questions,action) {
    if (request.current) return
    if (action==='approve' && !confirm(approvalConfirmation(questions,t))) return
    if (action==='archive' && !window.confirm(t('Archive this approved question? It will no longer be available for new assessments.'))) return
    const controller=new AbortController();request.current=controller;setBusy(true);setError('');setResult(null)
    try {
      const report=await transitionQuestions({questions,action,context,signal:controller.signal,onSuccess:ids=>select({type:'success',ids}),onSettled:async()=>{
        // Preserve the successful count even if refreshing the list fails.
        try {await onRefresh(controller.signal)} catch(e) {if(e.name!=='AbortError')setError(t('Refresh failed. Reload Question Bank before continuing.'))}
      }})
      if (!controller.signal.aborted) {select({type:'success',ids:report.skipped});setResult(report)}
    } catch(e) {if(!controller.signal.aborted)setError(t(e.message))}
    finally {if(!controller.signal.aborted){request.current=null;setBusy(false)}}
  }
  async function refresh(){
    if(request.current)return
    const controller=new AbortController();request.current=controller;setBusy(true);setError('')
    try{await onRefresh(controller.signal)}catch(e){if(!controller.signal.aborted)setError(t('Refresh failed. Reload Question Bank before continuing.'))}
    finally{if(!controller.signal.aborted){request.current=null;setBusy(false)}}
  }
  return {selected,select,busy,result,error,act,refresh}
}
export function QuestionWorkflowToolbar({questions,context,t,workflow,importedQuestions=[],allQuestions=questions}) {
  const {selected,select,busy,result,error,act}=workflow
  const chosen=questions.filter(q=>selected.includes(q.id))
  const selectable=questions.filter(q=>q.status!=='approved' && questionWorkflowActions(context,q).length)
  const imported=importedQuestions.filter(q=>approvalSteps(q,context)?.length)
  const ready=selectable.filter(q=>approvalSteps(q,context)?.length)
  const retryQuestions=allQuestions.filter(q=>result?.failed.some(f=>f.id===q.id) && (result.action==='approve'?approvalSteps(q,context)!==null:questionWorkflowActions(context,q).includes(result.action)))
  return <><p>{ready.length || selectable.length} {t(ready.length?'questions are ready for approval.':'questions are ready to be submitted for review.')}</p>
    {busy && <p role="status">{t('Processing…')}</p>}
    {!!imported.length && <button disabled={busy} onClick={()=>act(imported,'approve')}>{t('Approve imported questions')} ({imported.length})</button>}
    {!!selectable.length && <div className="import-actions"><button disabled={busy} onClick={()=>select({type:'all',ids:selectable.map(q=>q.id)})}>{t('Select all matching questions')}</button><button disabled={busy || !selected.length} onClick={()=>select({type:'clear'})}>{t('Clear selection')}</button><span>{chosen.length} {t('questions selected')}</span>{commonQuestionActions(chosen,context).map(action=><button key={action} disabled={busy} onClick={()=>act(chosen,action)}>{t(action==='submit-for-review'?'Submit selected for review':action==='approve'?'Approve selected':'Request changes')}</button>)}</div>}
    {!!selectable.length && <p>{t('Selection includes all loaded questions matching the current filters with an available workflow action. Changing filters clears selection.')}</p>}
    {!!chosen.length && !commonQuestionActions(chosen,context).length && <p>{t('Select questions with the same status and an action you can perform.')}</p>}
    {result && <div role="status"><p>{result.succeeded.length} {t(outcomes[result.action])}</p>{!!result.skipped?.length && <p>{t('Already approved questions were left unchanged.')}</p>}{!!result.failed.length && <><p>{result.failed.length} {t('questions require attention.')}</p><ul>{result.failed.map(f=><li key={f.id}>{t('Question')} {f.id}: {workflowFailure(f.error,t)}</li>)}</ul>{!!retryQuestions.length && <button disabled={busy} onClick={()=>act(retryQuestions,result.action)}>{t('Retry failed questions')} ({retryQuestions.length})</button>}</>}</div>}{error && <p role="alert">{error}<button onClick={workflow.refresh} disabled={busy}>{t('Retry refresh')}</button></p>}
  </>
}
