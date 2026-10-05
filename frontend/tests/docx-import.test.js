import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { createServer } from 'vite'
import { readFile } from 'node:fs/promises'

const server = await createServer({ server:{middlewareMode:true,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]} })
const { QuestionBank, questionBankGroups, loadBankQuestions, CompletedImport, ImportSummary, ImportReview, ImportReviewContent, ReviewQuestion, canConfirmImport, filterImportQuestions, initialReviewNavigation, reviewNavigationReducer, importReviewPage, ImportConfirmation, importConfirmationCounts, importError, SubjectSelector, CreateSubjectForm, createImportSubject, subjectCreationError } = await server.ssrLoadModule('/src/pages/staff/QuestionsPage.jsx')
const { default:QuestionMedia } = await server.ssrLoadModule('/src/components/common/QuestionMedia.jsx')
const { LanguageModeProvider } = await server.ssrLoadModule('/src/context/LanguageModeContext.jsx')
const { default:QuestionsPage } = await server.ssrLoadModule('/src/pages/staff/QuestionsPage.jsx')
await server.close()
const media = {id:'ab12-1234',url:'/api/v1/questions/media/ab12-1234/?institution=7',alt_text:'Source image'}
const question = {id:'s1q1',source_number:1,text:'R_(1) authored source',options:[{label:'A',text:'Yes'},{label:'B',text:'No'}],correct_answer:'A',question_type:'multiple_choice',included:true,reviewed:false,readiness:'ready',warnings:[],errors:[],media:[media],equations:[{status:'converted',representation:'R_(1)'}],original:{text:'Original wording'}}
const preview = {import_session_id:'abc',revision:1,metadata:{subject:2},subject_id:2,subject_name:'Chosen subject',confirmation:{eligible:true,status:'eligible',ready:1,included:1,excluded:0,unresolved:0,errors:0,review:0,subject_id:2,subject_name:'Chosen subject',blockers:[]},key_errors:[],sections:[{id:'s1',source_title:'1.0 Source section',source_order:1,questions:[question]}],summary:{questions_detected:1,ready_count:1,review_count:0,error_count:0,answers_matched:1,answers_missing:0,media_detected:1,equations_detected:1}}
const t = s=>s
const html=(component,props)=>renderToStaticMarkup(React.createElement(component,props))

test('Word and CSV import entry and upload state are retained',async()=>{
 const source=await readFile(new URL('../src/pages/staff/QuestionsPage.jsx',import.meta.url),'utf8')
 assert.match(source,/setKind\('csv'\)/);assert.match(source,/setKind\('docx'\)/);assert.match(source,/questions\/import\/docx\/preview\//);assert.match(source,/questions\/import\//);assert.match(source,/Processing…/);assert.match(source,/accept=.*\.docx/)
})
test('summary renders all operational counts',()=>{const markup=html(ImportSummary,{preview,t});for(const text of ['Questions detected','Ready','Needs review','Errors','Answers matched','Missing answers','Images','Equations'])assert.ok(markup.includes(text))})
test('review groups source sections and limits rendering to ten questions',()=>{
 const many={...preview,sections:[{...preview.sections[0],questions:Array.from({length:30},(_,i)=>({...question,id:'q'+i,source_number:i+1}))}]}
 const markup=html(ImportReview,{preview:many,t,busy:false,onChange:()=>{},onConfirm:()=>{},subjects:[]})
 assert.match(markup,/1.0 Source section/);assert.equal((markup.match(/class="import-question"/g)||[]).length,10);assert.match(markup,/Needs review/)
})
test('issue filter selects ready, review and error questions',()=>{
 const section={questions:[question,{...question,id:'2',readiness:'needs_review'},{...question,id:'3',readiness:'error'}]}
 assert.equal(filterImportQuestions(section,'all').length,3)
 for(const value of ['ready','needs_review','error'])assert.equal(filterImportQuestions(section,value)[0].readiness,value)
})
test('review fields support editing, exclusion, source and modified presentation',()=>{
 const markup=html(ReviewQuestion,{question:{...question,modified:true},t,onSave:()=>{},busy:false})
 for(const text of ['Question text','Options','Correct answer','Question type','Include question','Save review','Source preview','Modified','Original wording'])assert.ok(markup.includes(text))
 assert.match(markup,/type="checkbox" checked/);assert.match(markup,/R_\(1\)/)
})
test('image uses private API and unsafe source is not rendered',()=>{
 assert.match(html(QuestionMedia,{media:[media]}),/alt="Source image"/)
 assert.doesNotMatch(html(QuestionMedia,{media:[{...media,url:'https://evil.test/image'}]}),/<img/)
 assert.match(html(QuestionMedia,{media:[media],mode:'quick'}),/\/api\/v1\/quick-exam\/media/)
})
test('equation fallback displays warning and escaped source',()=>{
 const markup=html(ReviewQuestion,{question:{...question,equations:[{status:'needs_review',source_xml:'<m:nary />'}]},t,onSave:()=>{},busy:false})
 assert.match(markup,/Equation content requires manual review/);assert.match(markup,/Complete equation replacement/);assert.match(markup,/&lt;m:nary/)
})
test('confirmation uses only server eligibility and fails closed without a contract',()=>{
 assert.equal(canConfirmImport(preview),true);assert.equal(canConfirmImport(preview,true),false)
 assert.equal(canConfirmImport({...preview,confirmation:undefined}),false)
 assert.equal(canConfirmImport({...preview,confirmation:{...preview.confirmation,eligible:false}}),false)
 assert.equal(canConfirmImport({...preview,metadata:{},sections:[]}),true)
})

test('confirmation disabled state renders server blockers',()=>{
 const data={...preview,subject_id:null,subject_name:null,confirmation:{...preview.confirmation,eligible:false,subject_id:null,subject_name:null,blockers:[{code:'subject_required',message:'Select or create a subject before importing.'}]}}
 const markup=html(ImportReview,{preview:data,t,busy:false,onChange:()=>{},onConfirm:()=>{},subjects:[]})
 assert.match(markup,/<button disabled="">Import Questions/)
 assert.match(markup,/Select or create a subject before importing/);assert.match(markup,/Required/)
})

test('subject selector never defaults and preserves the exact persisted selection',()=>{
 const subjects=[{id:1,name:'Arbitrary first'},{id:2,name:'Chosen subject'}]
 const empty=html(SubjectSelector,{preview:{...preview,subject_id:null,subject_name:null},subjects,t,busy:false})
 assert.match(empty,/<option value="" selected="">Select a subject/)
 assert.doesNotMatch(empty,/<option value="[12]" selected/)
 assert.match(html(SubjectSelector,{preview,subjects,t}),/<option value="2" selected="">Chosen subject/)
 assert.match(html(SubjectSelector,{preview,subjects:[],t}),/<option value="2" selected="">Chosen subject/)
})

test('subject selection immediately saves explicit IDs and clearing resets dependent topic',()=>{
 const changes=[]
 const element=SubjectSelector({preview:{...preview,metadata:{subject:2,topic:9}},subjects:[],t,busy:true,onChange:value=>changes.push(value)})
 const select=React.Children.toArray(element.props.children).find(child=>child.type==='select')
 assert.equal(select.props.disabled,true)
 select.props.onChange({target:{value:'3'}})
 select.props.onChange({target:{value:''}})
 assert.deepEqual(changes,[{metadata:{subject:3,topic:null}},{metadata:{subject:null,topic:null}}])
 assert.equal(preview.subject_id,2)
})

test('a saved unavailable subject is explained rather than presented as an arbitrary default',()=>{
 const data={...preview,confirmation:{...preview.confirmation,subject_name:null,eligible:false,blockers:[{code:'metadata_invalid',message:'Import metadata requires correction.',details:{subject:['Invalid subject.']}}]}}
 const markup=html(ImportConfirmation,{preview:data,t,busy:false})
 assert.match(markup,/Selected subject is unavailable/);assert.match(markup,/Invalid subject/);assert.match(markup,/<button disabled="">Import Questions/)
})

test('nested backend validation messages remain visible',()=>{
 assert.match(importError({status:400,data:{subject:['Invalid subject.'],options:{0:{text:['Required text.']}}}},t),/Invalid subject/)
 assert.match(importError({status:400,data:{options:{0:{text:['Required text.']}}}},t),/Required text/)
})

test('success is drafts with bank return and no auto approval',async()=>{
 const source=await readFile(new URL('../src/pages/staff/QuestionsPage.jsx',import.meta.url),'utf8');assert.match(source,/questions imported as drafts/);assert.match(source,/View Question Bank/);assert.doesNotMatch(source,/\/approve\//)
})
test('responsive styles and interface RTL preserve source direction',async()=>{
 const css=await readFile(new URL('../src/pages/staff/question-import.css',import.meta.url),'utf8');assert.match(css,/@media\(max-width:700px\)/);assert.match(css,/margin-inline/)
 const markup=html(ReviewQuestion,{question,t,onSave:()=>{},busy:false});assert.match(markup,/dir="auto"/)
 const source=await readFile(new URL('../src/pages/staff/QuestionsPage.jsx',import.meta.url),'utf8');assert.match(source,/dir=\{direction\}/);assert.match(source,/label\(text, copy\[text\]/)
})

// Source-free fixture matches the verified pilot distribution across nine sections.
const distribution = [[26,2,0],[14,1,5],[17,3,0],[20,0,0],[20,0,0],[0,0,20],[15,5,0],[20,0,0],[0,0,3]]
function pilotPreview() {
 const sections=distribution.map(([ready,review,error],s)=>({id:`s${s+1}`,source_title:`Section ${s+1}`,source_order:s+1,
  questions:Array.from({length:ready+review+error},(_,i)=>({...question,id:`s${s+1}q${i+1}`,source_number:i+1,text:`Section ${s+1} question ${i+1}`,
   readiness:i<ready?'ready':i<ready+review?'needs_review':'error',errors:i>=ready+review?['A valid correct answer is required.']:[],correct_answer:i>=ready+review?'': 'A'}))}))
 return {...preview,sections,confirmation:{...preview.confirmation,eligible:false,status:'blocked',ready:132,included:171,excluded:0,unresolved:39,errors:28,review:11,blockers:[{code:'unresolved',count:39,message:'Correct, review or exclude every unresolved included question.'}]},summary:{...preview.summary,questions_detected:171,ready_count:132,review_count:11,error_count:28}}
}
function accessibleIds(data, navigation) {
 const first=importReviewPage(data,navigation)
 return Array.from({length:first.pageCount},(_,page)=>importReviewPage(data,{...navigation,page}).visible).flat().map(q=>q.id)
}
function reviewHtml(data,navigation) {
 return html(ImportReviewContent,{preview:data,navigation,t,busy:false,onChange:()=>{},onConfirm:()=>{},subjects:[]})
}
test('all status collections match summary across every section and pagination boundary',()=>{
 const data=pilotPreview()
 for(const [filter,count] of [['all',171],['ready',132],['needs_review',11],['error',28]]) {
  const navigation={...initialReviewNavigation,filter}
  const collection=importReviewPage(data,navigation)
  assert.equal(collection.total,count)
  const ids=accessibleIds(data,navigation)
  assert.equal(ids.length,count);assert.equal(new Set(ids).size,count)
  assert.deepEqual(ids,filterImportQuestions(data,filter).map(q=>q.id))
 }
})
test('all sections is the visible default and status labels use backend readiness names',()=>{
 const markup=reviewHtml(pilotPreview(),initialReviewNavigation)
 assert.match(markup,/aria-current="page">All sections/)
 assert.match(markup,/Questions<!-- -->|Questions:/)
 assert.match(markup,/1\u201310 of 171/)
 assert.match(markup,/value="needs_review"/);assert.match(markup,/value="error"/)
 assert.doesNotMatch(markup,/Search questions[^>]*hidden/)
})
test('all eleven review items render on two pages with collection total and section grouping',()=>{
 const data=pilotPreview();const navigation={...initialReviewNavigation,filter:'needs_review'}
 const first=reviewHtml(data,navigation),last=reviewHtml(data,{...navigation,page:1})
 assert.match(first,/1\u201310 of 11/);assert.match(first,/Page 1 of 2/)
 assert.match(last,/11\u201311 of 11/);assert.match(last,/Page 2 of 2/)
 assert.equal((first.match(/class="import-question"/g)||[]).length,10)
 assert.equal((last.match(/class="import-question"/g)||[]).length,1)
 assert.match(first,/<h3><bdi>Section 1/);assert.match(last,/<h3><bdi>Section 7/)
})
test('all 28 error questions render text options validation and editable answer fields',()=>{
 const data=pilotPreview();const navigation={...initialReviewNavigation,filter:'error'}
 let rendered=0
 for(let page=0;page<3;page++) {
  const markup=reviewHtml(data,{...navigation,page})
  rendered+=(markup.match(/class="import-question"/g)||[]).length
  assert.match(markup,/of 28/);assert.match(markup,/A valid correct answer is required/)
  assert.match(markup,/Question text/);assert.match(markup,/Yes/);assert.match(markup,/Correct answer/);assert.match(markup,/Save review/)
 }
 assert.equal(rendered,28)
 assert.match(reviewHtml(data,{...navigation,page:2}),/Section 9 question 3/)
})
test('status section and search changes reset navigation safely',()=>{
 for(const [type,value] of [['filter','error'],['sectionId','s6'],['search','question 20']]) {
  const next=reviewNavigationReducer({...initialReviewNavigation,page:17},{type,value})
  assert.equal(next.page,0);assert.equal(next[type],value)
 }
 assert.equal(reviewNavigationReducer({...initialReviewNavigation,page:2},{type:'resetPage'}).page,0)
})
test('section and status filters compose with visibly selected section and accurate counts',()=>{
 const data=pilotPreview(),navigation={...initialReviewNavigation,filter:'error',sectionId:'s6'}
 assert.equal(importReviewPage(data,navigation).total,20)
 assert.match(reviewHtml(data,navigation),/aria-current="page"><bdi>Section 6/)
 assert.match(reviewHtml(data,navigation),/1\u201310 of 20/)
 assert.equal(importReviewPage(data,{...navigation,filter:'needs_review'}).total,0)
 assert.match(reviewHtml(data,{...navigation,filter:'needs_review'}),/0\u20130 of 0/)
 assert.match(reviewHtml(data,{...navigation,filter:'needs_review'}),/No questions found/)
})
test('search and status compose across sections before pagination',()=>{
 const data=pilotPreview(),navigation={...initialReviewNavigation,filter:'error',search:'section 9'}
 assert.equal(importReviewPage(data,navigation).total,3)
 assert.equal(importReviewPage(data,{...navigation,sectionId:'s6'}).total,0)
 assert.match(reviewHtml(data,navigation),/value="section 9"/)
 assert.match(reviewHtml(data,navigation),/1\u20133 of 3/)
 assert.equal(importReviewPage(data,{...navigation,search:'yes'}).total,28)
})
test('server resolution updates summary and collection and resets or clamps the old page',()=>{
 const data=pilotPreview(),target=data.sections[6].questions[19]
 target.readiness='ready';target.reviewed=true
 data.summary.ready_count=133;data.summary.review_count=10;data.revision++
 const previous={...initialReviewNavigation,filter:'needs_review',page:1}
 const clamped=importReviewPage(data,previous)
 assert.equal(clamped.page,0);assert.equal(clamped.total,10);assert.equal(clamped.pageCount,1)
 assert.equal(importReviewPage(data,{...initialReviewNavigation,filter:'ready'}).total,133)
 assert.ok(!accessibleIds(data,previous).includes(target.id))
 assert.match(reviewHtml(data,previous),/1\u201310 of 10/)
 assert.match(reviewHtml(data,previous),/Page 1 of 1/)
})
test('exclusion updates included count without hiding the item or contradicting parsed status totals',()=>{
 const data=pilotPreview();const target=data.sections[5].questions[0];target.included=false
 const navigation={...initialReviewNavigation,filter:'error',sectionId:'s6'}
 assert.equal(importReviewPage(data,{...navigation,sectionId:'all'}).total,data.summary.error_count)
 assert.ok(accessibleIds(data,navigation).includes(target.id))
 const markup=reviewHtml(data,navigation)
 assert.match(markup,/Included questions: 170 \/ 171/);assert.match(markup,/Excluded/)
 assert.equal(canConfirmImport(data),false)
})

test('confirmation shows dynamic included readiness excludes errors and explains missing subject',()=>{
 const data=pilotPreview()
 for(const section of data.sections)for(const q of section.questions)q.readiness='ready'
 for(const q of data.sections[5].questions){q.included=false;q.readiness='error'}
 data.confirmation={...preview.confirmation,ready:151,included:151,excluded:20}
 assert.equal(importConfirmationCounts(data),data.confirmation)
 assert.equal(canConfirmImport(data),true)
 const markup=html(ImportConfirmation,{preview:data,t,busy:false,onConfirm:()=>{},onAttention:()=>{}})
 assert.match(markup,/151 Ready to import/);assert.match(markup,/20 Excluded/);assert.match(markup,/No issues found/);assert.doesNotMatch(markup,/Unresolved/)
 assert.doesNotMatch(markup,/<button disabled="">Import Questions/)
 const noSubject={...data,subject_id:null,subject_name:null,confirmation:{...data.confirmation,eligible:false,status:'blocked',subject_id:null,subject_name:null,blockers:[{code:'subject_required',message:'Select or create a subject before importing.'}]}}
 assert.match(html(ImportConfirmation,{preview:noSubject,t,busy:false}),/Select or create a subject before importing/)
 assert.equal(canConfirmImport(noSubject),false)
})
test('confirmation attention links reset other filters and target only included blockers',()=>{
 const data=pilotPreview();data.sections[5].questions[0].included=false
 data.confirmation={...data.confirmation,errors:27,unresolved:38,excluded:1,included:170}
 const counts=importConfirmationCounts(data);assert.equal(counts.errors,27);assert.equal(counts.review,11)
 const markup=html(ImportConfirmation,{preview:data,t,busy:false,onAttention:()=>{}})
 assert.match(markup,/Review included errors.*27/);assert.match(markup,/Review included warnings.*11/)
 const nav=reviewNavigationReducer({...initialReviewNavigation,sectionId:'s1',search:'hidden',page:4},{type:'attention',filter:'error'})
 assert.equal(nav.sectionId,'all');assert.equal(nav.search,'');assert.equal(nav.page,0);assert.equal(nav.includedOnly,true)
 assert.equal(importReviewPage(data,nav).total,27)
})
test('stable review route reload fetches server session and upload navigates to opaque ID',async()=>{
 const source=await readFile(new URL('../src/pages/staff/QuestionsPage.jsx',import.meta.url),'utf8')
 const routes=await readFile(new URL('../src/App.jsx',import.meta.url),'utf8')
 assert.match(routes,/questions\/import\/word\/:sessionId/)
 assert.match(source,/useParams\(\)/);assert.match(source,/questions\/import\/docx\/\$\{sessionId\}/)
 assert.match(source,/navigate\(`\/app\/questions\/import\/word\/\$\{result.import_session_id\}/)
 assert.match(source,/setPreview\(data\)/);assert.match(source,/data.status === 'completed'/)
 assert.match(source,/Resume Imports/);assert.match(source,/recent_imports/)
 assert.doesNotMatch(source,/localStorage|sessionStorage/)
})
test('expired retrieval has explicit localized error and completed reload cannot invoke confirm automatically',async()=>{
 assert.equal(importError({status:400,data:{detail:'This import session has expired. Upload the document again.'}},t),'This import session has expired. Upload the document again.')
 const source=await readFile(new URL('../src/pages/staff/QuestionsPage.jsx',import.meta.url),'utf8')
 assert.match(source,/This import session is unavailable/)
 const recovery=source.slice(source.indexOf('if (sessionId) staffApiFetch'),source.indexOf('function returnToBank'))
 assert.doesNotMatch(recovery,/method:.*POST|confirm\//)
 assert.match(source,/setSuccess\(data\)/)
})


test('inline subject creation stays in review and uses current required name/code fields',()=>{
 const review=html(ImportReview,{preview,t,busy:false,onChange:()=>{},onCreateSubject:()=>{},subjects:[]})
 assert.match(review,/\+ Create new subject/)
 const form=html(CreateSubjectForm,{t,busy:false,onCreate:()=>{},onCancel:()=>{}})
 for(const label of ['Create new subject','Subject name','Subject code','Create &amp; Select','Cancel'])assert.ok(form.includes(label))
 assert.equal((form.match(/<input/g)||[]).length,2)
 assert.equal((form.match(/required=""/g)||[]).length,2)
 assert.match(form,/maxLength="160"/);assert.match(form,/maxLength="64"/)
 assert.match(form,/dir="auto"/);assert.doesNotMatch(form,/<a /)
 assert.match(html(CreateSubjectForm,{t,busy:true}),/<fieldset disabled=""/)
})

test('Create and Select calls normal Subject POST then revision PATCH and returns only server selection',async()=>{
 const subject={id:7,institution:3,name:'Real subject',code:'REAL'},updated={...preview,subject_id:7,subject_name:'Real subject'}
 const events=[]
 const result=await createImportSubject({preview,institutionId:3,fields:{name:'Real subject',code:'REAL',institution:99},
  onCreated:item=>events.push(['option',item]),fetch:async(path,options)=>{events.push([path,options]);return path==='subjects/'?subject:updated}})
 assert.equal(events[0][0],'subjects/');assert.equal(events[0][1].method,'POST')
 assert.deepEqual(events[0][1].body,{institution:3,name:'Real subject',code:'REAL'})
 assert.deepEqual(events[1],['option',subject])
 assert.equal(events[2][0],'questions/import/docx/abc/');assert.equal(events[2][1].method,'PATCH')
 assert.deepEqual(events[2][1].body,{revision:1,metadata:{subject:7,topic:null}})
 assert.equal(result.preview,updated);assert.equal(preview.subject_id,2)
 assert.equal(canConfirmImport(result.preview),true)
})

test('failed subject creation shows duplicate validation without PATCH or review mutation',async()=>{
 const failure=Object.assign(new Error('Duplicate'),{status:400,data:{code:['A subject with this code already exists in this institution.']}})
 let requests=0,options=0
 await assert.rejects(createImportSubject({preview,institutionId:3,fields:{name:'Duplicate',code:'DUP'},onCreated:()=>options++,fetch:async()=>{requests++;throw failure}}),error=>error===failure)
 assert.equal(requests,1);assert.equal(options,0);assert.equal(preview.subject_id,2)
 assert.match(subjectCreationError(failure,t),/already exists/)
})

test('created subject remains available if metadata PATCH fails without silently selecting it',async()=>{
 const subject={id:7,name:'Created subject'},failure=Object.assign(new Error('Stale'),{status:400,data:{detail:'The preview changed. Reload before saving.'}})
 const options=[];let requests=0
 await assert.rejects(createImportSubject({preview,institutionId:3,fields:{name:'Created subject',code:'NEW'},onCreated:item=>options.push(item),fetch:async()=>{if(++requests===1)return subject;throw failure}}),error=>error.createdSubject===subject)
 assert.deepEqual(options,[subject]);assert.equal(requests,2);assert.equal(preview.subject_id,2)
 assert.match(subjectCreationError(failure,t),/Subject created, but selection could not be saved/)
 assert.match(subjectCreationError(failure,t),/Reload before saving/)
})

test('leaving the session or workspace prevents follow-up selection after subject POST',async()=>{
 const source=await readFile(new URL('../src/pages/staff/QuestionsPage.jsx',import.meta.url),'utf8')
 assert.match(source,/setSubjects\(\[\]\);setRecent\(\[\]\)/)
 assert.match(source,/subjectRequest.current\?\.abort\(\),\[institutionId,sessionId\]/)
 const controller=new AbortController();let requests=0,options=0
 await assert.rejects(createImportSubject({preview,institutionId:3,fields:{name:'Subject',code:'S'},signal:controller.signal,onCreated:()=>options++,fetch:async()=>{requests++;controller.abort();return {id:7}}}),{name:'AbortError'})
 assert.equal(requests,1);assert.equal(options,0);assert.equal(preview.subject_id,2)
})

test('review expiry uses actual persisted deadline and explains saved changes without a countdown',()=>{
 const markup=html(ImportReview,{preview:{...preview,expires_at:'2026-10-11T10:00:00Z'},t,busy:false,subjects:[]})
 assert.match(markup,/Saved changes can be resumed until the review session expires/)
 assert.match(markup,/Review session expires/);assert.doesNotMatch(markup,/countdown|seconds remaining/)
})

const bankItem=(id,section,sectionOrder,documentOrder,number,extras={})=>({id,subject:2,text:`electrode ${id}`,status:'draft',question_type:'multiple_choice',source:'DOCX',options:[{id:1,text:'Answer',is_correct:true}],media:[],source_metadata:{section_title:section,section_order:sectionOrder,document_order:documentOrder,question_number:number,...extras}})
test('bank groups and orders sections and document positions independently of source numbers',()=>{
 const items=[bankItem(1,'Later',20,22,1),bankItem(2,'First',1,9,1),bankItem(3,'First',1,3,7)]
 const groups=questionBankGroups(items)
 assert.deepEqual(groups.map(g=>g.title),['First','Later'])
 assert.deepEqual(groups[0].questions.map(q=>q.id),[3,2])
 const markup=html(QuestionBank,{questions:items,subjects:[{id:2,name:'Mathematics',code:'MATH'}],t})
 assert.match(markup,/Multiple choice/);assert.match(markup,/Draft/);assert.match(markup,/Mathematics/);assert.match(markup,/MATH/);assert.match(markup,/>Q7</)
 assert.ok(markup.indexOf('Q7')<markup.indexOf('electrode 3'))
 assert.equal(items[2].text,'electrode 3')
})
test('bank filtering preserves groups and separates document and subject identities',()=>{
 const items=[bankItem(1,'Same',1,1,1,{import_session_id:'a'}),bankItem(2,'Same',1,2,2,{import_session_id:'b'}),{...bankItem(3,'Same',1,3,3),subject:3},{...bankItem(4,'Same',1,4,4),status:'approved'}]
 assert.equal(questionBankGroups(items,{subject:2,status:'draft',search:'electrode',section:'Same'}).length,2)
 assert.equal(questionBankGroups(items,{search:'absent'}).length,0)
})
test('manual questions have no fabricated number and section directions render once',()=>{
 const items=[bankItem(1,'Reading',1,2,1,{section_directions:'Read carefully.'}),bankItem(2,'Reading',1,3,2,{section_directions:'Read carefully.'}),{id:3,subject:2,text:'Manual',status:'draft',question_type:'true_false',options:[],media:[]}]
 const markup=html(QuestionBank,{questions:items,subjects:[{id:2,name:'English',code:'ENG'}],t})
 assert.equal((markup.match(/Read carefully\./g)||[]).length,1)
 assert.match(markup,/Other questions/);assert.match(markup,/Manual/);assert.doesNotMatch(markup,/Qundefined/)
})
test('bank consumes every server page and keeps institution context',async()=>{
 const paths=[]
 const items=await loadBankQuestions(7,null,async path=>{paths.push(path);return paths.length===1?{results:[{id:1}],next:'http://server/api/v1/questions/?page=2'}:{results:[{id:2}],next:null}})
 assert.deepEqual(items.map(q=>q.id),[1,2]);assert.match(paths[1],/institution=7/)
})
test('completed history renders detected excluded and imported counts',()=>{
 const markup=html(CompletedImport,{receipt:{original_parsed_count:9,excluded_count:2,imported_count:7},t})
 assert.match(markup,/9 Questions detected/);assert.match(markup,/2 Excluded/);assert.match(markup,/7 Imported/)
})
