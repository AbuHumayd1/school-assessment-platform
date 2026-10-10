import { useEffect, useRef, useState } from 'react'
import { staffApiFetch } from '../../services/api.js'
import { questionWorkflowActions } from '../../utils/staffCapabilities.js'
import { importMessage } from './ImportBlocks.jsx'

export const questionWorkflowCopy = {
  'Submit for review':'إرسال للمراجعة', 'Approve':'اعتماد', 'Request changes':'طلب تعديلات', 'Archive':'أرشفة',
  'Submit selected for review':'إرسال المحدد للمراجعة', 'Approve selected':'اعتماد المحدد',
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
  return ['submit-for-review','approve','request-changes'].filter(action => questions.every(q => questionWorkflowActions(context,q).includes(action)))
}
export async function transitionQuestions({questions,action,context,signal,fetcher=staffApiFetch,onSuccess=()=>{}}) {
  if (!questions.length || questions.some(q => !questionWorkflowActions(context,q).includes(action))) throw new Error('These questions do not support this action.')
  const succeeded=[], failed=[]
  for (const question of questions) {
    if (signal?.aborted) break
    try {
      await fetcher(`questions/${question.id}/${action}/?institution=${context.institutionId}`,{method:'POST',body:{},signal})
      succeeded.push(question.id)
    } catch (error) {
      if (error.name === 'AbortError') break
      failed.push({id:question.id,error})
    }
  }
  if (signal?.aborted) return null
  if (succeeded.length) await onSuccess(succeeded)
  return {action,succeeded,failed}
}

export function QuestionWorkflowControls({question,context,t,busy,onAction,selected,onSelect}) {
  const actions=questionWorkflowActions(context,question)
  if (!actions.length) return null
  return <div className="import-actions"><label><input type="checkbox" disabled={busy} checked={selected} onChange={onSelect}/>{t('Select question')} {question.source_metadata?.question_number ?? question.id}</label>{actions.map(action=><button key={action} type="button" disabled={busy} onClick={()=>onAction([question],action)}>{t(labels[action])}</button>)}</div>
}

export function useQuestionWorkflow({context,t,onRefresh}) {
  const [selected,setSelected]=useState([]), [busy,setBusy]=useState(false), [result,setResult]=useState(null), [error,setError]=useState('')
  const request=useRef(null)
  useEffect(()=>()=>request.current?.abort(),[])
  const select=action=>setSelected(old=>selectionReducer(old,action))
  async function act(questions,action) {
    if (request.current) return
    if (action==='archive' && !window.confirm(t('Archive this approved question? It will no longer be available for new assessments.'))) return
    const controller=new AbortController();request.current=controller;setBusy(true);setError('');setResult(null)
    try {
      const report=await transitionQuestions({questions,action,context,signal:controller.signal,onSuccess:async ids=>{
        select({type:'success',ids})
        // Preserve the successful count even if refreshing the list fails.
        try {await onRefresh(controller.signal)} catch(e) {if(e.name!=='AbortError')setError(t('Refresh failed. Reload Question Bank before continuing.'))}
      }})
      if (!controller.signal.aborted) setResult(report)
    } catch(e) {if(!controller.signal.aborted)setError(t(e.message))}
    finally {if(!controller.signal.aborted){request.current=null;setBusy(false)}}
  }
  return {selected,select,busy,result,error,act}
}
export function QuestionWorkflowToolbar({questions,context,t,workflow}) {
  const {selected,select,busy,result,error,act}=workflow
  const chosen=questions.filter(q=>selected.includes(q.id))
  const selectable=questions.filter(q=>questionWorkflowActions(context,q).length)
  return <><p>{t('Imported questions are saved as Draft. Review and approve them before adding them to an assessment.')}</p>
    {!!selectable.length && <div className="import-actions"><button disabled={busy} onClick={()=>select({type:'all',ids:selectable.map(q=>q.id)})}>{t('Select all matching questions')}</button><button disabled={busy || !selected.length} onClick={()=>select({type:'clear'})}>{t('Clear selection')}</button><span>{chosen.length} {t('questions selected')}</span>{commonQuestionActions(chosen,context).map(action=><button key={action} disabled={busy} onClick={()=>act(chosen,action)}>{t(action==='submit-for-review'?'Submit selected for review':action==='approve'?'Approve selected':'Request changes')}</button>)}</div>}
    {!!selectable.length && <p>{t('Selection includes all loaded questions matching the current filters with an available workflow action. Changing filters clears selection.')}</p>}
    {!!chosen.length && !commonQuestionActions(chosen,context).length && <p>{t('Select questions with the same status and an action you can perform.')}</p>}
    {result && <div role="status"><p>{result.succeeded.length} {t(outcomes[result.action])}</p>{!!result.failed.length && <><p>{result.failed.length} {t('questions require attention.')}</p><ul>{result.failed.map(f=><li key={f.id}>{t('Question')} {f.id}: {workflowFailure(f.error,t)}</li>)}</ul></>}</div>}{error && <p role="alert">{error}</p>}
  </>
}
