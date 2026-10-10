import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
import {createServer} from 'vite'
import {readFile} from 'node:fs/promises'
import {questionWorkflowActions} from '../src/utils/staffCapabilities.js'

const server=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}})
const {QuestionWorkflowControls,QuestionWorkflowToolbar,selectionReducer,commonQuestionActions,transitionQuestions,questionWorkflowCopy,approvalConfirmation,QuestionSelection}=await server.ssrLoadModule('/src/pages/staff/QuestionWorkflow.jsx')
const {questionBankGroups,QuestionBank}=await server.ssrLoadModule('/src/pages/staff/QuestionsPage.jsx')
await server.close()
const context={role:'institution_admin',userId:7,institutionId:21,workspaceMode:'institution'}
const q=(id,status='draft',extras={})=>({id,institution:21,created_by:7,status,text:`Question ${id}`,subject:8,question_type:'multiple_choice',options:[],media:[],...extras})
const html=(component,props)=>renderToStaticMarkup(React.createElement(component,props))
const controls=(question,ctx=context)=>html(QuestionWorkflowControls,{question,context:ctx,t:s=>s,busy:false,selected:false,onSelect:()=>{},onAction:()=>{}})

test('administrator draft exposes approval while teacher retains submission',()=>{
 assert.match(controls(q(1)),/>Approve</);assert.doesNotMatch(controls(q(1)),/Submit for review/);assert.match(controls(q(1),{...context,role:'teacher'}),/Submit for review/)
 assert.deepEqual(questionWorkflowActions({...context,role:'teacher'},q(1)),['submit-for-review'])
 assert.deepEqual(questionWorkflowActions({...context,role:'teacher',userId:9},q(1)),[])
})
test('review allows administrator approval and reviewer request changes',()=>{
 assert.match(controls(q(1,'review')),/>Approve</);assert.match(controls(q(1,'review')),/Request changes/)
 assert.deepEqual(questionWorkflowActions({...context,role:'examiner'},q(1,'review')),['request-changes'])
 assert.deepEqual(questionWorkflowActions({...context,role:'teacher'},q(1,'review')),[])
})
test('approved cannot expose draft or review transitions',()=>{
 const markup=controls(q(1,'approved'));assert.match(markup,/Archive/);assert.doesNotMatch(markup,/Submit for review|Approve|Request changes/)
 assert.deepEqual(questionWorkflowActions(context,q(1,'archived')),[])
})
test('student and foreign-institution questions fail closed',()=>{
 assert.equal(controls(q(1,'review'),{...context,role:'student'}),'')
 assert.equal(controls(q(1,'review',{institution:22})),'')
 assert.deepEqual(questionWorkflowActions({...context,institutionId:null},q(1)),[])
})
test('managed client restrictions remain while platform authority can prepare',()=>{
 assert.equal(controls(q(1,'review'),{...context,workspaceMode:'managed_exam'}),'')
 assert.match(controls(q(1,'review'),{...context,role:'platform_admin',workspaceMode:'managed_exam'}),/>Approve</)
})
test('same capabilities apply to any institution identity',()=>{
 for(const institutionId of [1,3,21,900]) assert.deepEqual(questionWorkflowActions({...context,institutionId},q(1,'review',{institution:institutionId})),['request-changes','approve'])
})
test('selection toggles, selects exact supplied scope, clears successes and can clear all',()=>{
 let state=selectionReducer([],{type:'toggle',id:1});state=selectionReducer(state,{type:'toggle',id:2})
 assert.deepEqual(state,[1,2]);assert.deepEqual(selectionReducer(state,{type:'toggle',id:1}),[2])
 state=selectionReducer(state,{type:'all',ids:[2,3,3]});assert.deepEqual(state,[2,3])
 assert.deepEqual(selectionReducer(state,{type:'success',ids:[2]}),[3]);assert.deepEqual(selectionReducer(state,{type:'clear'}),[])
})
test('mixed statuses cannot accidentally receive bulk approval or submission',()=>{
 assert.deepEqual(commonQuestionActions([q(1),q(2,'review')],context),['approve'])
 assert.deepEqual(commonQuestionActions([q(1),q(2)],context),['approve'])
 assert.deepEqual(commonQuestionActions([q(1,'review')],{...context,role:'examiner'}),['request-changes'])
})
test('toolbar states loaded matching-filter scope and exact selected count',()=>{
 const markup=html(QuestionWorkflowToolbar,{questions:[q(1),q(2)],context,t:s=>s,workflow:{selected:[1],select:()=>{},busy:false,result:null,error:'',act:()=>{}}})
 assert.match(markup,/Select all matching questions/);assert.match(markup,/all loaded questions matching the current filters/)
 assert.match(markup,/1.*questions selected/);assert.match(markup,/Approve selected/);assert.doesNotMatch(markup,/Submit selected for review/)
})
test('each existing filter restricts select-all source rows',()=>{
 const rows=[q(1),q(2,'review'),q(3,'draft',{subject:9}),q(4,'draft',{source_metadata:{section_title:'B'}})]
 for(const [filter,ids] of [[{status:'review'},[2]],[{subject:'9'},[3]],[{section:'B'},[4]],[{search:'Question 1'},[1]]]) {
  const matching=questionBankGroups(rows,filter).flatMap(g=>g.questions)
  assert.deepEqual(selectionReducer([],{type:'all',ids:matching.map(q=>q.id)}),ids)
 }
})
test('bulk submission calls individual endpoints sequentially and refreshes after success',async()=>{
 const calls=[];let inFlight=0,refreshed
 const result=await transitionQuestions({questions:[q(1),q(2)],action:'submit-for-review',context,fetcher:async(path,options)=>{
  assert.equal(inFlight++,0);calls.push(path);assert.equal(options.method,'POST');assert.deepEqual(options.body,{});await Promise.resolve();inFlight--
 },onSuccess:ids=>{refreshed=ids}})
 assert.deepEqual(calls,['questions/1/submit-for-review/?institution=21','questions/2/submit-for-review/?institution=21'])
 assert.deepEqual(refreshed,[1,2]);assert.deepEqual(result.succeeded,[1,2]);assert.deepEqual(result.failed,[])
})
test('bulk approval reuses approve action and preserves exact success/failure counts',async()=>{
 const calls=[];let refreshed
 const result=await transitionQuestions({questions:[q(1,'review'),q(2,'review'),q(3,'review')],action:'approve',context,fetcher:async path=>{calls.push(path);if(path.includes('/2/'))throw new Error('Invalid options')},onSuccess:ids=>{refreshed=ids}})
 assert.equal(calls.length,3);assert.ok(calls.every(path=>path.includes('/approve/')))
 assert.deepEqual(result.succeeded,[1,3]);assert.deepEqual(result.failed.map(f=>f.id),[2]);assert.deepEqual(refreshed,[1,3])
 const markup=html(QuestionWorkflowToolbar,{questions:[],context,t:s=>s,workflow:{selected:[],select:()=>{},busy:false,result,error:'',act:()=>{}}})
 assert.match(markup,/2.*questions approved successfully/);assert.match(markup,/1.*questions require attention/);assert.match(markup,/Question.*2/)
})
test('all failures never refresh or count as successful approval',async()=>{
 const result=await transitionQuestions({questions:[q(1,'review')],action:'approve',context,fetcher:async()=>{throw new Error('Forbidden')},onSuccess:()=>assert.fail('Must not refresh as success')})
 assert.equal(result.succeeded.length,0);assert.equal(result.failed.length,1)
})
test('invalid transitions rejected before requests without shortcuts',async()=>{
 await assert.rejects(transitionQuestions({questions:[q(1,'archived')],action:'approve',context,fetcher:()=>assert.fail('No archived approval')}))
 await assert.rejects(transitionQuestions({questions:[q(1,'review')],action:'approve',context:{...context,role:'examiner'},fetcher:()=>assert.fail('No unauthorized request')}))
})
test('workspace cancellation stops batch and prevents stale refresh',async()=>{
 const controller=new AbortController();let calls=0
 const result=await transitionQuestions({questions:[q(1),q(2)],action:'submit-for-review',context,signal:controller.signal,fetcher:async()=>{calls++;controller.abort()},onSuccess:()=>assert.fail('No stale refresh')})
 assert.equal(result,null);assert.equal(calls,1)
})
test('Arabic workflow labels and draft guidance remain available',()=>{
 const markup=html(QuestionWorkflowToolbar,{questions:[q(1)],context,t:s=>questionWorkflowCopy[s]||s,workflow:{selected:[1],select:()=>{},busy:false,result:null,error:'',act:()=>{}}})
 assert.match(markup,/اعتماد المحدد/);assert.match(markup,/أسئلة جاهزة للاعتماد/)
})
test('generic bank renders workflow and preserves subject status section search filters',()=>{
 const markup=html(QuestionBank,{questions:[q(1)],subjects:[{id:8,name:'Subject',code:'S'}],t:s=>s,context})
 for(const text of ['Subject','Status','Section title','Search questions','Approve','questions are ready for approval']) assert.ok(markup.includes(text))
})
test('bank clears selection on filter changes and refreshes through real scoped loader',async()=>{
 const source=await readFile(new URL('../src/pages/staff/QuestionsPage.jsx',import.meta.url),'utf8')
 assert.match(source,/workflow.select\(\{type:'clear'\}\);setFilters/)
 assert.match(source,/await loadBankQuestions\(institutionId,signal\)/)
 assert.match(source,/if\(!signal\?.aborted\)setQuestions\(refreshed\)/)
})

async function workflowController(run) {
 const fixture={states:[],cursor:0,calls:[],failId:2}
 globalThis.__questionWorkflowTest=fixture
 const app=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]},plugins:[{
  name:'question-workflow-controller',enforce:'pre',
  resolveId(id){if(id==='workflow-hooks'||id==='workflow-api')return `\0${id}`},
  load(id){
   if(id==='\0workflow-hooks')return `export function useState(initial){const f=globalThis.__questionWorkflowTest,i=f.cursor++;if(!(i in f.states))f.states[i]=initial;return[f.states[i],value=>{f.states[i]=typeof value==='function'?value(f.states[i]):value}]} export function useRef(initial){const [ref]=useState({current:initial});return ref} export function useEffect(){}`
   if(id==='\0workflow-api')return `export async function staffApiFetch(path){const f=globalThis.__questionWorkflowTest;f.calls.push(path);if(path.includes('/'+f.failId+'/'))throw Object.assign(new Error('Invalid options'),{data:{detail:'Invalid options'}});return{}}`
  },
  transform(source,id){if(id.endsWith('/src/pages/staff/QuestionWorkflow.jsx'))return source.replace("from 'react'","from 'workflow-hooks'").replace("from '../../services/api.js'","from 'workflow-api'")}
 }]})
 try {
  const {useQuestionWorkflow}=await app.ssrLoadModule('/src/pages/staff/QuestionWorkflow.jsx')
  const draw=onRefresh=>{fixture.cursor=0;return useQuestionWorkflow({context,t:s=>s,onRefresh,confirm:message=>{fixture.confirmation=message;return fixture.confirmed!==false}})}
  await run(fixture,draw)
 } finally {delete globalThis.__questionWorkflowTest;await app.close()}
}
test('workflow controller refreshes once, clears successful selection and preserves failed selection and reasons',async()=>workflowController(async(fixture,draw)=>{
 let refreshed=0;const refresh=async()=>refreshed++
 let workflow=draw(refresh);workflow.select({type:'all',ids:[1,2,3]});workflow=draw(refresh)
 await workflow.act([q(1,'review'),q(2,'review'),q(3,'review')],'approve')
 workflow=draw(refresh)
 assert.equal(refreshed,1);assert.deepEqual(workflow.selected,[2]);assert.equal(workflow.busy,false)
 assert.deepEqual(workflow.result.succeeded,[1,3]);assert.deepEqual(workflow.result.failed.map(f=>f.id),[2])
 const markup=html(QuestionWorkflowToolbar,{questions:[q(2,'review')],context,t:s=>s,workflow})
 assert.match(markup,/Invalid options/)
}))
test('workflow controller retains accurate committed counts if list refresh fails',async()=>workflowController(async(fixture,draw)=>{
 fixture.failId=null;const refresh=async()=>{throw new Error('Network failed')}
 await draw(refresh).act([q(1,'review')],'approve')
 const workflow=draw(refresh)
 assert.deepEqual(workflow.result.succeeded,[1]);assert.match(workflow.error,/Refresh failed/);assert.equal(workflow.busy,false)
}))

test('mixed administrator approval submits drafts first, approves review directly and skips approved',async()=>{
 const calls=[]
 const result=await transitionQuestions({questions:[q(1),q(2,'review'),q(3,'approved')],action:'approve',context,fetcher:async path=>calls.push(path)})
 assert.deepEqual(calls,['questions/1/submit-for-review/?institution=21','questions/1/approve/?institution=21','questions/2/approve/?institution=21'])
 assert.deepEqual(result.succeeded,[1,2]);assert.deepEqual(result.skipped,[3])
})
test('failed second step is not counted as approval and always refreshes for recovery',async()=>{
 let refreshed=0
 const result=await transitionQuestions({questions:[q(1)],action:'approve',context,fetcher:async path=>{if(path.includes('/approve/'))throw new Error('Invalid options')},onSettled:()=>refreshed++})
 assert.equal(refreshed,1);assert.deepEqual(result.succeeded,[]);assert.equal(result.failed[0].id,1)
})
test('failed submission never attempts approval',async()=>{
 const calls=[]
 await transitionQuestions({questions:[q(1)],action:'approve',context,fetcher:async path=>{calls.push(path);throw new Error('Not allowed')}})
 assert.deepEqual(calls,['questions/1/submit-for-review/?institution=21'])
})
test('administrator approval confirmation counts only pending questions and explains transitions in both languages',()=>{
 assert.match(approvalConfirmation([q(1),q(2,'review'),q(3,'approved')],s=>s),/Approve 2 Questions\?/)
 assert.match(approvalConfirmation([q(1)],s=>questionWorkflowCopy[s]||s),/ستُرسل المسودات للمراجعة ثم تُعتمد/)
})
test('cancelled approval confirmation performs no requests',async()=>workflowController(async(fixture,draw)=>{
 fixture.confirmed=false
 await draw(async()=>assert.fail('No refresh')).act([q(1)],'approve')
 assert.deepEqual(fixture.calls,[]);assert.match(fixture.confirmation,/Approve 1 Questions/)
}))
test('collapsed question summary has selection but no workflow buttons; detail retains actions',()=>{
 const markup=html(QuestionBank,{questions:[q(1)],subjects:[{id:8,name:'Subject',code:'S'}],t:s=>s,context})
 const summary=markup.match(/<summary>(.*?)<\/summary>/s)[1]
 assert.match(summary,/type="checkbox"/);assert.doesNotMatch(summary,/<button/)
 assert.match(markup,/<\/summary><div class="import-actions"><button/)
 assert.equal(html(QuestionSelection,{question:q(1,'approved'),context,t:s=>s,busy:false,selected:false,onSelect:()=>{}}),'')
})
test('imported approval uses only the exact new receipt IDs and respects authority',()=>{
 const calls=[];const workflow={selected:[],select:()=>{},busy:false,result:null,error:'',act:(rows,action)=>calls.push([rows.map(q=>q.id),action])}
 const element=QuestionWorkflowToolbar({questions:[q(3)],importedQuestions:[q(1),q(2,'approved')],context,t:s=>s,workflow})
 function walk(node){return node&&typeof node==='object'?[node,...React.Children.toArray(node.props?.children).flatMap(walk)]:[]}
 const button=walk(element).find(n=>n.type==='button'&&n.props.children?.[0]==='Approve imported questions')
 button.props.onClick();assert.deepEqual(calls,[[[1],'approve']])
 const teacher=html(QuestionWorkflowToolbar,{questions:[q(1)],importedQuestions:[q(1)],context:{...context,role:'teacher'},t:s=>s,workflow:{...workflow,selected:[1]}})
 assert.doesNotMatch(teacher,/Approve imported|Approve selected/);assert.match(teacher,/Submit selected for review/)
})
test('failed approval can retry refreshed Review question outside current Draft filter',async()=>{
 const calls=[]
 const workflow={selected:[1],select:()=>{},busy:false,error:'',result:{action:'approve',succeeded:[],skipped:[],failed:[{id:1,error:new Error('Invalid options')}]},act:(rows,action)=>calls.push([rows,action])}
 const element=QuestionWorkflowToolbar({questions:[],allQuestions:[q(1,'review')],context,t:s=>s,workflow})
 function walk(node){return node&&typeof node==='object'?[node,...React.Children.toArray(node.props?.children).flatMap(walk)]:[]}
 walk(element).find(n=>n.type==='button'&&n.props.children?.[0]==='Retry failed questions').props.onClick()
 const paths=[]
 await transitionQuestions({questions:calls[0][0],action:calls[0][1],context,fetcher:async path=>paths.push(path)})
 assert.deepEqual(paths,['questions/1/approve/?institution=21'])
})
