import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { readFile } from 'node:fs/promises'

const server = await createServer({server:{middlewareMode:true,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]}})
const {processWordImport,confirmImportToBank,loadBankQuestions,ImportAttention,ImportSummary,ImportSuccess,reviewNavigationReducer,initialReviewNavigation,importReviewPage} = await server.ssrLoadModule('/src/pages/staff/QuestionsPage.jsx')
const {WordImportFields,ImportCards,importWorkflowCopy} = await server.ssrLoadModule('/src/pages/staff/ImportWorkflow.jsx')
await server.close()
const t = text => text
const html = (Component,props) => renderToStaticMarkup(React.createElement(Component,props))
const subjects = [{id:5,name:'Seeroh'}]
const question = {id:'q60',source_number:60,text:'Question requiring correction',included:true,readiness:'error',errors:['Every option requires bounded, non-empty text.'],warnings:[],options:[]}
const preview = {import_session_id:'review-id',revision:2,metadata:{subject:5},summary:{questions_detected:60,ready_count:59,error_count:1,review_count:0,answers_matched:60},confirmation:{eligible:false,attention_count:1,blockers:[{code:'unresolved',count:1}]},sections:[{id:'section',source_title:'Seeroh',questions:[question]}]}
function documents(mode='embedded_key') {
  const data = new FormData()
  data.set('subject','5');data.set('import_mode',mode)
  data.set('file',new File(['questions'],'Questions.docx'))
  if (mode === 'separate_key') data.set('answer_key_file',new File(['answers'],'Answers.docx'))
  return data
}

test('embedded form explicitly selects subject before mode and requires only questions document', () => {
  const markup = html(WordImportFields,{subjects,t,mode:'embedded_key',busy:false,onModeChange:()=>{}})
  assert.ok(markup.indexOf('name="subject"') < markup.indexOf('name="import_mode"'))
  assert.match(markup,/select name="subject" required=""/)
  assert.match(markup,/<input(?=[^>]*required="")(?=[^>]*type="file")(?=[^>]*accept=".docx")[^>]*name="file"/)
  assert.doesNotMatch(markup,/answer_key_file/)
  assert.match(markup,/Process Questions/)
})
test('separate mode collects both required documents in the same form', () => {
  const markup = html(WordImportFields,{subjects,t,mode:'separate_key',busy:false,onModeChange:()=>{}})
  assert.match(markup,/name="file"/)
  assert.match(markup,/<input(?=[^>]*required="")[^>]*name="answer_key_file"/)
  assert.match(markup,/\.docx,.xlsx,.csv/)
  assert.doesNotMatch(markup,/session|Unfinished/)
})
test('empty subjects prevent processing and labels retain Arabic', () => {
  const markup = html(WordImportFields,{subjects:[],t:text=>importWorkflowCopy[text]||text,mode:'separate_key',busy:false,onModeChange:()=>{}})
  assert.match(markup,/disabled=""/)
  assert.match(markup,/معالجة الأسئلة/)
  assert.match(markup,/مستند الأسئلة/)
})
test('embedded processing navigates to review and does not confirm automatically', async () => {
  const paths = [], calls = []
  const result = await processWordImport({formData:documents(),subjects,institutionId:7,onReview:path=>paths.push(path),fetcher:async(path,options)=>{calls.push([path,options]);return preview}})
  assert.equal(result,preview)
  assert.deepEqual(paths,['/app/questions/import/word/review-id'])
  assert.equal(calls.length,1)
  assert.equal(calls[0][0],'questions/import/docx/preview/?institution=7')
  assert.equal(calls[0][1].body.get('subject'),'5')
  assert.equal(calls[0][1].body.get('import_mode'),'embedded_key')
})
test('separate processing matches 60 answers and navigates to review despite one genuine error', async () => {
  const calls = [], paths = []
  const result = await processWordImport({formData:documents('separate_key'),subjects,institutionId:7,onReview:path=>paths.push(path),fetcher:async(path,options)=>{
    calls.push([path,options]);assert.equal(paths.length,0)
    return calls.length === 1 ? {...preview,revision:1} : preview
  }})
  assert.equal(result.summary.answers_matched,60)
  assert.equal(result.confirmation.eligible,false)
  assert.deepEqual(paths,['/app/questions/import/word/review-id'])
  assert.equal(calls.length,2)
  assert.equal(calls[1][0],'questions/import/docx/review-id/answer-key/?institution=7')
  assert.equal(calls[1][1].body.get('revision'),'1')
  assert.equal(calls[1][1].body.get('file').name,'Answers.docx')
  assert.equal(calls[0][1].body.get('answer_key_file'),null)
})
test('missing answer file or foreign/unselected subject is rejected before creating a preview', async () => {
  for (const scenario of ['answer','foreign','subject','mode']) {
    const data = documents('separate_key');let requests = 0
    if (scenario === 'answer') data.delete('answer_key_file')
    if (scenario === 'foreign') data.set('subject','99')
    if (scenario === 'subject') data.delete('subject')
    if (scenario === 'mode') data.delete('import_mode')
    await assert.rejects(processWordImport({formData:data,subjects,institutionId:7,fetcher:async()=>{requests++}}))
    assert.equal(requests,0)
  }
})
test('failed answer-key upload preserves the existing preview for recovery', async () => {
  const failure = Object.assign(new Error('Invalid key'),{status:400,data:{detail:'Invalid answer key.'}})
  await assert.rejects(processWordImport({formData:documents('separate_key'),subjects,institutionId:7,fetcher:async path=>{if(path.includes('answer-key'))throw failure;return preview}}), error=>error===failure && error.preview===preview)
})
test('cancelled processing cannot navigate or upload the second file', async () => {
  const controller = new AbortController();let calls=0, navigation=0
  await assert.rejects(processWordImport({formData:documents('separate_key'),subjects,institutionId:7,signal:controller.signal,onReview:()=>navigation++,fetcher:async()=>{calls++;controller.abort();return preview}}),{name:'AbortError'})
  assert.equal(calls,1);assert.equal(navigation,0)
})
test('one affected question is identified with its real reason and exact editor action', () => {
  const markup = html(ImportAttention,{preview,t,busy:false,onInspect:()=>{}}).replace(/<!--.*?-->/g,'')
  assert.match(markup,/Question 60/)
  assert.match(markup,/Every option requires bounded, non-empty text/)
  assert.match(markup,/exclude it before importing/)
  const state = reviewNavigationReducer(initialReviewNavigation,{type:'question',questionId:'q60'})
  assert.deepEqual(importReviewPage(preview,state).visible.map(row=>row.id),['q60'])
  const summary = html(ImportSummary,{preview,t}).replace(/<!--.*?-->/g,'')
  assert.match(summary,/60 Questions detected/)
  assert.match(summary,/59 Ready/)
  assert.match(summary,/1 Needs attention/)
})
test('confirmation returns to the bank and refetches its real list only after success', async () => {
  const calls=[], navigation=[], receipt={imported_count:60};let refreshed
  await confirmImportToBank({preview:{...preview,revision:3},institutionId:7,fetcher:async(path,options)=>{calls.push([path,options]);return receipt},onComplete:value=>{
    assert.equal(value,receipt);navigation.push('/app/questions')
    refreshed=loadBankQuestions(7,undefined,async path=>{calls.push([path]);return {results:[{id:1,subject:5,text:'Imported question'}],next:null}})
  }})
  assert.deepEqual(navigation,['/app/questions'])
  assert.equal(calls[0][0],'questions/import/docx/review-id/confirm/?institution=7')
  assert.deepEqual(calls[0][1].body,{revision:3})
  assert.equal((await refreshed)[0].text,'Imported question')
  assert.equal(calls[1][0],'questions/?institution=7')
  assert.match(html(ImportSuccess,{count:60}),/60 questions imported successfully/)
})
test('rejected confirmation never navigates or reports success', async () => {
  let completed=false
  await assert.rejects(confirmImportToBank({preview,institutionId:7,onComplete:()=>{completed=true},fetcher:async()=>{throw new Error('Blocked by validation')}}))
  assert.equal(completed,false)
})
test('only incomplete imports appear in collapsed secondary recovery', () => {
  const imports=[{import_session_id:'old',filename:'Old.docx',status:'completed'},{import_session_id:'resume',filename:'Questions.docx',status:'unfinished',questions_detected:60,summary:preview.summary}]
  const markup=html(ImportCards,{imports,t,busy:false,onContinue:()=>{},onDelete:()=>{}})
  assert.match(markup,/Resume previous import/);assert.match(markup,/Continue import/)
  assert.doesNotMatch(markup,/Old.docx|Unfinished|<details[^>]* open/)
  assert.equal(html(ImportCards,{imports:[imports[0]],t}), '')
})
test('page wiring refreshes the bank on finalization rather than showing a receipt-only page', async () => {
  const source=await readFile(new URL('../src/pages/staff/QuestionsPage.jsx',import.meta.url),'utf8')
  assert.match(source,/onComplete:returnToBank/)
  assert.match(source,/setSuccess\(receipt\?\.imported_count/)
  assert.match(source,/setRevision\(v=>v\+1\)/)
  assert.match(source,/\[institutionId,revision\]/)
  assert.match(source,/data.status === 'completed'\) returnToBank\(data\)/)
})
