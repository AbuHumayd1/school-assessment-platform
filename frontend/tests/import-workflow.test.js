import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import {renderToStaticMarkup} from 'react-dom/server'
import {createServer} from 'vite'
import {readFile} from 'node:fs/promises'

const server=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}})
const {ImportModeChoice,ImportWorkflowHeading,ImportCards,sessionMode,manageImportAction,confirmKeyReplacement,importWorkflowCopy}=await server.ssrLoadModule('/src/pages/staff/ImportWorkflow.jsx')
const {ImportReviewContent}=await server.ssrLoadModule('/src/pages/staff/QuestionsPage.jsx')
const {default:AnswerKeyPanel}=await server.ssrLoadModule('/src/pages/staff/AnswerKeyPanel.jsx')
await server.close()
const t=s=>s
const html=(component,props)=>renderToStaticMarkup(React.createElement(component,props))
const preview={import_session_id:'session',import_mode:'embedded_key',revision:3,metadata:{subject:2},subject_id:2,summary:{questions_detected:0,ready_count:0,review_count:0,error_count:0},sections:[],key_errors:[],confirmation:{eligible:false,blockers:[{code:'unresolved',message:'Correct, review or exclude every unresolved included question.'}]}}
const key={source_document:{filename:'Answers.xlsx',file_type:'xlsx',sha256:'hash'},entries:[],parsed_entry_count:0,summary:{matched_count:0,needs_review_count:0,unmatched_count:0,conflict_count:0,questions_missing_answer:2}}
const item={import_session_id:'session',import_mode:'separate_key',revision:3,filename:'Questions.docx',subject_name:'Physics',questions_detected:151,summary:{ready_count:148,review_count:1,error_count:2,answers_matched:148,answers_missing:3},updated_at:'2026-10-04T10:00:00Z',status:'unfinished',answer_key_document:key.source_document}
const review=(mode,extra={})=>html(ImportReviewContent,{preview:{...preview,import_mode:mode,...extra},t,busy:false,subjects:[],onChange:()=>{},onConfirm:()=>{},onKeyUpload:()=>{},onKeySave:()=>{},onKeyRemove:()=>{},onDelete:()=>{}})

test('new Word imports require one explicit mode selection',()=>{
 const markup=html(ImportModeChoice,{t,busy:false})
 assert.match(markup,/How are answers provided/);assert.equal((markup.match(/type="radio"/g)||[]).length,2)
 assert.match(markup,/value="embedded_key"/);assert.match(markup,/value="separate_key"/)
 assert.equal((markup.match(/required=""/g)||[]).length,2);assert.doesNotMatch(markup,/checked=""/)
})
test('embedded and separate choices explain independent workflows',()=>{
 const markup=html(ImportModeChoice,{t,busy:false})
 assert.match(markup,/already contains its answer key/);assert.match(markup,/Choose both documents/)
})
test('persisted mode controls restored review without transient selection',()=>{
 assert.equal(sessionMode(preview),'embedded_key');assert.equal(sessionMode({...preview,import_mode:'separate_key'}),'separate_key')
 assert.equal(sessionMode({separate_answer_key:key}),'separate_key');assert.equal(sessionMode({}),'embedded_key')
})
test('embedded review hides separate upload and explains manual answer correction',()=>{
 const markup=review('embedded_key')
 assert.match(markup,/Embedded Answer Key/);assert.match(markup,/Review Questions/)
 assert.doesNotMatch(markup,/Upload Answer Key|Replace Answer Key|No answer key uploaded/)
 assert.match(markup,/Confirm Import/);assert.match(markup,/Search questions/)
})
test('separate review shows integrated key panel and server blocker',()=>{
 const markup=review('separate_key')
 assert.match(markup,/Separate Answer Key/);assert.match(markup,/Upload Answer Key/)
 assert.match(markup,/No answer key uploaded/);assert.match(markup,/Correct, review or exclude every unresolved/)
})
test('active key shows filename replacement and removal controls',()=>{
 const markup=review('separate_key',{separate_answer_key:key})
 assert.match(markup,/Answers.xlsx/);assert.match(markup,/Replace Answer Key/);assert.match(markup,/Remove Answer Key/)
})
test('cancelled key removal sends no request',async()=>{
 const result=await manageImportAction(preview,'remove_key',{confirm:message=>{assert.match(message,/Saved manual and embedded answers will be kept/);return false},fetcher:()=>assert.fail('No mutation')})
 assert.equal(result,null)
})
test('confirmed key removal uses current revision and authoritative result',async()=>{
 let sent
 const result=await manageImportAction(preview,'remove_key',{confirm:()=>true,fetcher:async(path,options)=>{sent=[path,options];return {...preview,import_mode:'separate_key',revision:4}}})
 assert.equal(sent[0],'questions/import/docx/session/answer-key/');assert.equal(sent[1].method,'DELETE');assert.deepEqual(sent[1].body,{revision:3})
 assert.equal(result.revision,4)
 const markup=html(AnswerKeyPanel,{preview:result,t,busy:false,onUpload:()=>{},onSave:()=>{},onRemove:()=>{}})
 assert.match(markup,/Upload Answer Key/);assert.match(markup,/No answer key uploaded/);assert.doesNotMatch(markup,/Remove Answer Key/)
})
test('replacement asks confirmation only when a key already exists',()=>{
 assert.equal(confirmKeyReplacement(preview,t,()=>assert.fail('No current key')),true)
 assert.equal(confirmKeyReplacement({...preview,separate_answer_key:key},t,message=>{assert.match(message,/Old automatic matches will be removed/);return false}),false)
})
test('delete confirmation explains Question Bank protection and cancellation',async()=>{
 const result=await manageImportAction(preview,'delete',{confirm:message=>{assert.match(message,/Delete this import/);assert.match(message,/No Question Bank questions will be deleted/);return false},fetcher:()=>assert.fail('No mutation')})
 assert.equal(result,null)
})
test('confirmed deletion returns success and uses session revision',async()=>{
 let sent
 const result=await manageImportAction(preview,'delete',{confirm:()=>true,fetcher:async(path,options)=>{sent=[path,options];return null}})
 assert.deepEqual(result,{deleted:true});assert.equal(sent[0],'questions/import/docx/session/');assert.deepEqual(sent[1].body,{revision:3})
})
test('secondary recovery shows useful counts subject and Continue without internal status',()=>{
 const markup=html(ImportCards,{imports:[item],t,busy:false,onContinue:()=>{},onDelete:()=>{}})
 for(const text of ['Questions.docx','Physics','151','148','Needs attention','Last updated','Continue import','Delete Import','Resume previous import'])assert.ok(markup.includes(text))
 assert.doesNotMatch(markup,/Unfinished|Import session|<details[^>]* open/)
})
test('completed imports are absent from recovery',()=>{
 const markup=html(ImportCards,{imports:[{...item,import_mode:'embedded_key',status:'completed'}],t,busy:false,onContinue:()=>{},onDelete:()=>{}})
 assert.equal(markup,'')
})
test('deleted item disappears from refreshed import collection',()=>{
 const markup=html(ImportCards,{imports:[],t,busy:false,onContinue:()=>{},onDelete:()=>{}})
 assert.equal(markup,'')
})
test('English bilingual and Arabic RTL structure preserve choice labels',()=>{
 for(const mode of ['english','bilingual','arabic']){
  const translate=s=>mode==='english'?s:mode==='arabic'?(importWorkflowCopy[s]||s):s+' / '+(importWorkflowCopy[s]||s)
  const markup=html('div',{dir:mode==='arabic'?'rtl':'ltr',children:React.createElement(ImportModeChoice,{t:translate,busy:false})})
  assert.match(markup,/name="import_mode"/)
  if(mode!=='english')assert.match(markup,/كيف تُقدَّم الإجابات/)
  if(mode!=='arabic')assert.match(markup,/How are answers provided/)
  if(mode==='arabic')assert.match(markup,/dir="rtl"/)
 }
})
test('mode survives question metadata saves and deletion refreshes the list',async()=>{
 const source=await readFile(new URL('../src/pages/staff/QuestionsPage.jsx',import.meta.url),'utf8')
 assert.match(source,/manageImportAction\(item,'delete'/);assert.match(source,/result\?\.deleted\)returnToBank/)
 assert.match(source,/onContinue=\{id=>navigate\(`\/app\/questions\/import\/word\/\$\{id\}`\)/)
 assert.match(source,/WordImportForm subjects=\{subjects\} t=\{t\}/);assert.match(source,/if\(result && apply\)setPreview/)
})
