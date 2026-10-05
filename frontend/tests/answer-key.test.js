import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { readFile } from 'node:fs/promises'

const server=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}})
const {default:AnswerKeyPanel,answerKeyCollection,supportedAnswerKey,uploadAnswerKey,saveAnswerMatch,matchError,answerKeyCopy}=await server.ssrLoadModule('/src/pages/staff/AnswerKeyPanel.jsx')
const {ImportReviewContent,ReviewQuestion,canConfirmImport}=await server.ssrLoadModule('/src/pages/staff/QuestionsPage.jsx')
await server.close()
const t=s=>s
const question={id:'s1q1',source_number:1,text:'Question from One',options:[{label:'A',text:'Alpha'},{label:'B',text:'Beta'}],correct_answer:'B',answer_baseline:'A',question_type:'multiple_choice',included:true,reviewed:true,readiness:'ready',warnings:[],errors:[],media:[],equations:[],original:{text:'Original',correct_answer:'A'}}
const entries=['matched','conflict','ambiguous','invalid_answer','unmatched','duplicate','excluded'].map((status,index)=>({id:`k${index+1}`,question_number:1,answer:'B',section:'One',status,question_id:['matched','conflict','invalid_answer','duplicate'].includes(status)?'s1q1':undefined,candidate_ids:status==='ambiguous'?['s1q1','s2q1']:[],candidate_count:2}))
const preview={import_session_id:'session',revision:4,metadata:{subject:2},subject_id:2,subject_name:'Math',key_errors:[],summary:{questions_detected:2,ready_count:2,review_count:0,error_count:0,answers_matched:2,answers_missing:0,media_detected:0,equations_detected:0},sections:[{id:'s1',source_title:'One',source_order:1,questions:[question]},{id:'s2',source_title:'Two',source_order:2,questions:[{...question,id:'s2q1',text:'Second section'}]}],confirmation:{eligible:false,blockers:[{code:'answer_key_review',message:'Resolve or exclude every unresolved answer-key entry.',count:4}]},separate_answer_key:{source_document:{filename:'key.xlsx',file_type:'xlsx',sha256:'abc'},matching_revision:4,parsed_entry_count:7,entries,summary:{matched_count:1,needs_review_count:5,unmatched_count:1,conflict_count:1,blocker_count:4,questions_missing_answer:1}}}
const html=(component,props)=>renderToStaticMarkup(React.createElement(component,props))
const panel=props=>html(AnswerKeyPanel,{preview,t,busy:false,onUpload:()=>{},onSave:()=>{},initialFilter:'all',...props})

test('answer key upload and supported file types are visible',()=>{
 const markup=panel({preview:{...preview,separate_answer_key:undefined}})
 assert.match(markup,/Upload Answer Key/);assert.match(markup,/accept=".docx,.xlsx,.csv"/)
 assert.match(markup,/Questions are created only after confirmation/)
 for(const name of ['key.docx','key.xlsx','key.csv','KEY.CSV'])assert.equal(supportedAnswerKey({name,size:20}),true)
})
test('unsupported or oversized files are rejected before sending',async()=>{
 for(const file of [{name:'key.xlsm',size:1},{name:'key.pdf',size:1},{name:'key.csv',size:2*1024*1024+1}]){
  assert.equal(supportedAnswerKey(file),false)
  await assert.rejects(uploadAnswerKey(preview,file,{fetcher:()=>assert.fail('Must not send')}),/DOCX, XLSX or CSV/)
 }
})
test('summary shows server counts and missing-answer blocker',()=>{
 const markup=panel()
 for(const text of ['Answers matched','Answers need your attention','Resolve or exclude every unresolved answer-key entry.'])assert.ok(markup.includes(text))
 assert.match(markup,/key.xlsx/)
})
test('all entries remain accessible and status filters exactly match their collections',()=>{
 assert.equal(answerKeyCollection(preview).length,7)
 assert.equal(answerKeyCollection(preview,'matched').length,1)
 assert.equal(answerKeyCollection(preview,'needs_review').length,5)
 assert.equal(answerKeyCollection(preview,'unmatched').length,1)
 assert.equal(answerKeyCollection(preview,'conflict').length,1)
})
test('ambiguous candidates remain visible under relevant source sections',()=>{
 assert.equal(answerKeyCollection(preview,'needs_review','s2').length,1)
 assert.equal(answerKeyCollection(preview,'conflict','s1').length,1)
 assert.equal(answerKeyCollection(preview,'conflict','s2').length,0)
})
test('rows show section source number question options imported and existing answers',()=>{
 const markup=panel({initialFilter:'all'})
 for(const text of ['One','Q1','Question from One','Alpha','Beta','Existing answer','Reviewed answer','Imported answer','Intended question','Correct answer'])assert.ok(markup.includes(text))
 assert.match(markup,/Resolve conflict/);assert.match(markup,/Exclude key entry/);assert.match(markup,/Restore key entry/)
})
test('equivalent agreement and explicit manual resolution are visible',()=>{
 const key={...preview.separate_answer_key,entries:[{...entries[0],agreement:true,resolved:true}]}
 const markup=panel({preview:{...preview,separate_answer_key:key},initialFilter:'all'})
 assert.match(markup,/Agrees with the existing answer/);assert.match(markup,/Resolved by manual review/)
})
test('replacement is explicit and describes preservation rules',()=>{
 const markup=panel()
 assert.match(markup,/Replace Answer Key/);assert.match(markup,/removes old automatic matches and keeps saved manual answers/)
})
test('upload sends file and current revision with sheet and optional column mapping',async()=>{
 const file=new File(['number,answer\n1,B\n'],'key.csv'),signal=new AbortController().signal
 let sent
 const result=await uploadAnswerKey(preview,file,{sheet:'Two',columns:{number:0,answer:1},signal,fetcher:async(path,options)=>{sent=[path,options];return preview}})
 assert.equal(result,preview);assert.equal(sent[0],'questions/import/docx/session/answer-key/')
 assert.equal(sent[1].method,'POST');assert.equal(sent[1].body.get('revision'),'4');assert.equal(sent[1].body.get('sheet'),'Two')
 assert.deepEqual(JSON.parse(sent[1].body.get('columns')),{number:0,answer:1});assert.equal(sent[1].signal,signal)
})
test('manual correction and conflict resolution are server revision controlled',async()=>{
 let request
 await saveAnswerMatch(preview,'k2',{question_id:'s1q1',answer:'A'},{fetcher:async(path,options)=>{request=[path,options];return preview}})
 assert.equal(request[0],'questions/import/docx/session/answer-key/matches/k2/')
 assert.deepEqual(request[1].body,{revision:4,question_id:'s1q1',answer:'A'});assert.equal(request[1].method,'PATCH')
 assert.equal(preview.sections[0].questions[0].correct_answer,'B')
})
test('extra unmatched entries can be explicitly excluded',async()=>{
 let body
 await saveAnswerMatch(preview,'k5',{excluded:true},{fetcher:async(path,options)=>{body=options.body}})
 assert.deepEqual(body,{revision:4,excluded:true})
})
test('server errors survive with safe readable messages',()=>{
 assert.match(matchError({data:{answer:['The answer does not uniquely match the selected question options.']}},t),/does not uniquely match/)
 assert.match(matchError(new Error('Network failed'),t),/Network failed/)
})
test('question import review retains subject controls with integrated answer-key panel',()=>{
 const markup=html(ImportReviewContent,{preview,t,busy:false,onChange:()=>{},onConfirm:()=>{},onKeyUpload:()=>{},onKeySave:()=>{},subjects:[{id:2,name:'Math'}]})
 assert.match(markup,/Answer Key/);assert.match(markup,/Select a subject/);assert.match(markup,/Save metadata/);assert.match(markup,/Save review/)
 assert.equal(canConfirmImport(preview),false)
 assert.equal(canConfirmImport({...preview,confirmation:{eligible:true}}),true)
})
test('multiple-select question review keeps multiple correct options separate from text',()=>{
 const markup=html(ReviewQuestion,{question:{...question,question_type:'multiple_select',correct_answer:['A','B']},t,busy:false,onSave:()=>{}})
 assert.match(markup,/multiple=""/);assert.match(markup,/Multiple select/);assert.match(markup,/Question from One/)
})
test('recovery uses persisted preview and workspace changes abort key requests',async()=>{
 const source=await readFile(new URL('../src/pages/staff/QuestionsPage.jsx',import.meta.url),'utf8')
 assert.match(source,/keyRequest.current\?\.abort/);assert.match(source,/controller.signal.aborted/)
 assert.match(source,/setPreview\(result\)/);assert.match(source,/onKeyUpload=.*uploadAnswerKey/)
 assert.match(source,/questions\/import\/docx\/\$\{sessionId\}/)
})
test('large collections use all-entry filtering before ten-row pagination',()=>{
 const many={...preview,separate_answer_key:{...preview.separate_answer_key,entries:Array.from({length:31},(_,i)=>({...entries[0],id:`k${i}`}))}}
 assert.equal(answerKeyCollection(many,'matched').length,31)
 const markup=panel({preview:many})
 assert.equal((markup.match(/class="import-question answer-key-match"/g)||[]).length,10)
 assert.match(markup,/Next/)
})
test('source content is escaped and Arabic labels remain available',()=>{
 const key={...preview.separate_answer_key,entries:[{...entries[0],answer:'<script>bad</script>'}]}
 const markup=panel({preview:{...preview,separate_answer_key:key},initialFilter:'all'})
 assert.match(markup,/&lt;script&gt;/);assert.doesNotMatch(markup,/<script>/)
 assert.notEqual(answerKeyCopy['Answer Key'],'Answer Key');assert.notEqual(answerKeyCopy['Resolve conflict'],'Resolve conflict')
})
