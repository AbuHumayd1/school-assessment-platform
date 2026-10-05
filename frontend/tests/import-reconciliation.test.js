import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { readFile } from 'node:fs/promises'

const server=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}})
const {default:Panel,answerKeyCollection,downloadAnswerTemplate,saveAnswerMatch}=await server.ssrLoadModule('/src/pages/staff/AnswerKeyPanel.jsx')
const {default:Blocks,classifyImportBlock,reconciliationCopy,blockError,importMessage}=await server.ssrLoadModule('/src/pages/staff/ImportBlocks.jsx')
const {ImportReviewContent,ReviewQuestion}=await server.ssrLoadModule('/src/pages/staff/QuestionsPage.jsx')
const api=await server.ssrLoadModule('/src/services/api.js')
await server.close()
const t=value=>value
const question={id:'s1q1',preview_question_id:'s1q1',mapping_token:'PQ-local',source_number:1,text:'Reviewable prompt',options:[{label:'A',text:'Alpha'},{label:'B',text:'Beta'}],question_type:'multiple_choice',correct_answer:null,included:true,reviewed:false,readiness:'needs_review',errors:[],warnings:['Missing answer'],equations:[],media:[],original:{text:'Reviewable prompt',options:[],correct_answer:null}}
const statuses=['matched','ambiguous','unmatched','conflict','invalid_answer','duplicate','excluded']
const entries=statuses.map((status,i)=>({id:`k${i}`,status,question_number:1,answer:'B',section:'One',question_id:status==='matched'?'s1q1':undefined,candidate_ids:['s1q1'],candidate_count:1,reason:status==='ambiguous'?'section_missing_and_number_not_global_unique':undefined}))
const key={entries,parsed_entry_count:entries.length,source_document:{filename:'key.csv',file_type:'csv',sha256:'hash'},summary:{matched_count:1,ambiguous_count:1,unmatched_count:1,conflict_count:1,needs_review_count:5,blocker_count:4,questions_missing_answer:1}}
const preview={import_session_id:'local-session',revision:9,import_mode:'separate_key',metadata:{},sections:[{id:'s1',section_key:'PS-local',source_title:'One',source_order:1,questions:[question]}],key_errors:[],summary:{questions_detected:1,ready_count:0,review_count:1,error_count:0,answers_missing:1},confirmation:{eligible:false,blockers:[]},separate_answer_key:key,blocks:[{id:'block-s1',title:'Uncertain block',classification:'questions',uncertain:true,needs_classification:true,section:{questions:[question]}}]}
const html=(component,props)=>renderToStaticMarkup(React.createElement(component,props))
const panel=(extra={})=>html(Panel,{preview,t,busy:false,onUpload:()=>{},onSave:()=>{},onTemplate:()=>{},...extra})

test('separate workflow offers optional recommended template and existing upload',()=>{
 const markup=panel()
 assert.match(markup,/Download Answer Key Template/);assert.match(markup,/For the most reliable matching/)
 assert.match(markup,/Upload Existing Answer Key/);assert.match(markup,/accept=".docx,.xlsx,.csv"/)
 assert.doesNotMatch(markup,/required=""[^>]*type="file"/)
})
test('template download uses authorized staff request and blob response',async()=>{
 const signal=new AbortController().signal,blob=new Blob(['xlsx']);let sent
 const result=await downloadAnswerTemplate(preview,{signal,fetcher:async(...args)=>{sent=args;return blob}})
 assert.equal(result,blob);assert.equal(sent[0],'questions/import/docx/local-session/answer-key-template/')
 assert.equal(sent[1].responseType,'blob');assert.equal(sent[1].signal,signal)
})
test('binary download retains session credentials and selected workspace',async()=>{
 const originalFetch=globalThis.fetch
 try{
  api.setInstitutionContext(7)
  globalThis.fetch=async(url,options)=>{
   assert.equal(options.credentials,'include');assert.equal(options.headers.get('X-Institution-ID'),'7')
   assert.ok(url.endsWith('/answer-key-template/'));assert.equal(options.responseType,undefined)
   return new Response('workbook',{headers:{'Content-Type':'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'}})
  }
  const blob=await api.staffApiFetch('questions/import/docx/local-session/answer-key-template/',{responseType:'blob'})
  assert.equal(await blob.text(),'workbook')
 }finally{globalThis.fetch=originalFetch;api.clearSessionContext()}
})
test('binary download preserves real JSON authorization errors',async()=>{
 const originalFetch=globalThis.fetch,originalWindow=globalThis.window
 try{
  globalThis.window={dispatchEvent:()=>{}}
  globalThis.fetch=async()=>new Response(JSON.stringify({detail:'Denied'}),{status:403,headers:{'Content-Type':'application/json'}})
  await assert.rejects(api.staffApiFetch('questions/import/docx/local-session/answer-key-template/',{responseType:'blob'}),error=>error.status===403&&error.data.detail==='Denied')
 }finally{globalThis.fetch=originalFetch;globalThis.window=originalWindow}
})
for(const [filter,count] of [['all',7],['matched',1],['needs_review',5],['ambiguous',1],['unmatched',1],['conflict',1]]){
 test(`reconciliation ${filter} filter exposes the complete intended collection`,()=>assert.equal(answerKeyCollection(preview,filter).length,count))
}
test('section filter preserves unresolved candidates',()=>assert.equal(answerKeyCollection(preview,'ambiguous','s1').length,1))
test('embedded entries use the shared collection and filters',()=>{
 const embedded={...preview,import_mode:'embedded_key',separate_answer_key:undefined,embedded_answer_key:key}
 assert.equal(answerKeyCollection(embedded,'ambiguous').length,1)
 const markup=panel({preview:embedded});assert.match(markup,/Check answers/)
 assert.match(markup,/Match Answer/);assert.doesNotMatch(markup,/Download Answer Key Template|Upload Existing Answer Key/)
})
test('linking is a distinct non-submit action from authoritative correction',()=>{
 const markup=panel();assert.match(markup,/type="button"[^>]*>Match Answer/)
 assert.match(markup,/Intended question/);assert.match(markup,/optgroup label="One"/)
 assert.match(markup,/Correct answer/);assert.match(markup,/Exclude key entry/)
})
test('persisted explicit link offers relink after recovery',()=>{
 const recovered={...preview,separate_answer_key:{...key,entries:[{...entries[0],linked_question_id:'s1q1',resolution_source:'manual_link'}]}}
 assert.match(panel({preview:recovered,initialFilter:'all'}),/Change match/)
})
test('link request does not silently include an authoritative answer override',async()=>{
 let sent;await saveAnswerMatch(preview,'k1',{question_id:'s1q1',excluded:false},{fetcher:async(...args)=>{sent=args}})
 assert.deepEqual(sent[1].body,{revision:9,question_id:'s1q1',excluded:false})
 assert.equal(sent[1].method,'PATCH')
})
test('exclude extra key entry sends only explicit decision and revision',async()=>{
 let sent;await saveAnswerMatch(preview,'k2',{excluded:true},{fetcher:async(...args)=>{sent=args}})
 assert.deepEqual(sent[1].body,{revision:9,excluded:true})
})
test('uncertain block offers all three classifications and extracted preview',()=>{
 const markup=html(Blocks,{preview,t,busy:false,onClassify:()=>{}})
 for(const text of ['We need your help with one part of the document.','Uncertain block','Questions','Answer Key','Ignore','Reviewable prompt'])assert.ok(markup.includes(text))
 assert.match(markup,/<details[^>]*open/)
})
test('unheaded table and unknown key paragraph retain visible source text',()=>{
 const d={...preview,blocks:[{id:'table',title:'Table 5',classification:'ignore',uncertain:true,entries:[],unparsed:[{text:'1 | B'}]}]}
 assert.match(html(Blocks,{preview:d,t,busy:false,onClassify:()=>{}}),/1 \| B/)
})
for(const classification of ['questions','answer_key','ignore']){
 test(`classification ${classification} sends session-local block and current revision`,async()=>{
  let sent;await classifyImportBlock(preview,'block-s1',classification,{fetcher:async(...args)=>{sent=args;return {...preview,revision:10}}})
  assert.equal(sent[0],'questions/import/docx/local-session/blocks/block-s1/classification/')
  assert.deepEqual(sent[1].body,{revision:9,classification});assert.equal(sent[1].method,'PATCH')
  const message='Choose Questions, Answer Key or Ignore.'
  assert.equal(blockError({data:{classification:[message]}},t),message)
  assert.equal(blockError({data:{classification:[message]}},s=>reconciliationCopy[s]||s),'اختر الأسئلة أو مفتاح الإجابة أو التجاهل.')
 })
}
test('review renders updated server counts and persisted classification',()=>{
 const updated={...preview,summary:{...preview.summary,questions_detected:20,ready_count:20,review_count:0},blocks:[{...preview.blocks[0],classification:'answer_key',needs_classification:false}]}
 const markup=html(ImportReviewContent,{preview:updated,t,busy:false,subjects:[],onChange:()=>{},onConfirm:()=>{},onClassify:()=>{},onKeySave:()=>{},onKeyUpload:()=>{}})
 assert.match(markup,/value="answer_key" selected/);assert.match(markup,/>20</)
})
test('missing answer retains question/options and review status',()=>{
 const markup=html(ReviewQuestion,{question,t,busy:false,onSave:()=>{}})
 assert.match(markup,/needs_review/);assert.match(markup,/Missing answer/);assert.match(markup,/Reviewable prompt/);assert.match(markup,/Alpha/)
 assert.doesNotMatch(markup,/import-readiness--error/)
})
test('diagnostic reason is translated into an understandable action',()=>{
 const markup=panel();assert.match(markup,/We could not determine which question this answer belongs to/);assert.doesNotMatch(markup,/section_missing_and_number_not_global_unique|Matching reason/)
 assert.match(markup,/Ambiguous/)
})
for(const language of ['english','bilingual','arabic']){
 test(`${language} reconciliation and classification retain accessible structure`,()=>{
  const translate=s=>language==='english'?s:language==='arabic'?(reconciliationCopy[s]||s):`${s} / ${reconciliationCopy[s]||s}`
  const markup=html('div',{dir:language==='arabic'?'rtl':'ltr',children:[React.createElement(Blocks,{key:'blocks',preview,t:translate,busy:false,onClassify:()=>{}}),React.createElement(Panel,{key:'panel',preview,t:translate,busy:false,onSave:()=>{},onUpload:()=>{},onTemplate:()=>{}})]})
  assert.match(markup,/<label/);assert.match(markup,/<bdi>/)
  if(language!=='english')assert.match(markup,/تنزيل قالب مفتاح الإجابة/)
  if(language==='arabic')assert.match(markup,/dir="rtl"/)
 })
}
test('logical responsive sizing supports narrow review controls',async()=>{
 const css=await readFile(new URL('../src/pages/staff/question-import.css',import.meta.url),'utf8')
 assert.match(css,/\.import-block select\{width:100%;box-sizing:border-box\}/)
 assert.match(css,/@media\(max-width:700px\).*answer-key-match fieldset\{flex-direction:column/)
 assert.match(css,/margin-inline-end/)
})

for(const mode of ['embedded_key','separate_key'])test(`${mode} success presents ready state with collapsed details`,()=>{
 const ready={...preview,import_mode:mode,key_errors:[],blocks:[{...preview.blocks[0],needs_classification:false,uncertain:false}],confirmation:{eligible:true,included:20,ready:20,unresolved:0,excluded:0,attention_count:0,blockers:[],subject_name:'Math'},summary:{...preview.summary,questions_detected:20,answers_matched:20},separate_answer_key:mode==='separate_key'?{...key,entries:[{...entries[0],status:'matched'}],summary:{...key.summary,matched_count:20,blocker_count:0}}:undefined,embedded_answer_key:mode==='embedded_key'?{...key,entries:[{...entries[0],status:'matched'}],summary:{...key.summary,matched_count:20,blocker_count:0}}:undefined}
 const markup=html(ImportReviewContent,{preview:ready,t,busy:false,subjects:[],onChange:()=>{},onConfirm:()=>{},onClassify:()=>{},onKeySave:()=>{},onKeyUpload:()=>{},onTemplate:()=>{}})
 assert.match(markup,/Your import is ready/);assert.match(markup,/Import Questions \(20\)/)
 assert.doesNotMatch(markup,/Confirmation status|Source blocks|Embedded answer reconciliation|Matching reason/)
 assert.doesNotMatch(markup,/<details[^>]*open/)
 assert.doesNotMatch(markup,/class="import-question answer-key-match"/)
})
test('additional backend blockers remain counted when every question is ready',()=>{
 const blocked={...preview,confirmation:{eligible:false,included:20,ready:20,unresolved:0,additional_issues:1,attention_count:1,blockers:[{code:'document_review',count:1,message:'Check the highlighted document content against your Word file, then confirm that you have reviewed it.'}]}}
 const markup=html(ImportReviewContent,{preview:blocked,t,busy:false,subjects:[],onChange:()=>{},onConfirm:()=>{}})
 assert.match(markup,/Items needing attention: 1/);assert.match(markup,/1 Additional issues/);assert.match(markup,/Check the highlighted document/)
 assert.match(markup,/<button disabled="">Import Questions/)
})
test('uncertain classification does not pretend the user already chose Questions',()=>{
 const markup=html(Blocks,{preview,t,busy:false,onClassify:()=>{}})
 assert.match(markup,/Choose an option/);assert.doesNotMatch(markup,/value="questions" selected/)
})

test('matching summary counts questions once when embedded and separate sources agree',()=>{
 const both={...preview,embedded_answer_key:{...key,entries:[{...entries[0],status:'matched'}],summary:{...key.summary,blocker_count:0}},separate_answer_key:{...key,entries:[{...entries[0],id:'other',status:'matched'}],summary:{...key.summary,blocker_count:0}},summary:{...preview.summary,questions_detected:1}}
 assert.match(panel({preview:both}),/1 \/ 1 Answers matched/)
 assert.doesNotMatch(panel({preview:both}),/2 \/ 1 Answers matched/)
})
test('resolved equivalent duplicates do not request unnecessary manual attention',()=>{
 const d={...preview,separate_answer_key:{...key,entries:[{...entries[0],status:'duplicate',resolved:true}]}}
 assert.equal(answerKeyCollection(d,'needs_review').length,0)
 assert.equal(answerKeyCollection(d,'all').length,1)
})

test('stale import responses do not expose revision internals',()=>{
 for(const message of ['Delete the current server preview revision.','Remove the key from the current server preview revision.','Confirm the current server preview revision.'])assert.equal(importMessage(message),'This import has changed. Refresh it and try again.')
 assert.equal(importMessage('A genuine failure'),'A genuine failure')
})
