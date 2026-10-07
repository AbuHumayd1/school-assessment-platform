import test from 'node:test'
import assert from 'node:assert/strict'
import React from 'react'
import { createServer } from 'vite'

const exam = { id:11, status:'draft', candidate_access:'specific_candidates', delivery_mode:'quick_exam', quick_access_configured:true, has_attempt_history:false }
async function controller(run) {
  const f={cells:[],calls:[],downloads:[],cleanups:[],location:{key:'pilot'},credentials:{count:273,assigned_count:300,generated_count:273,needed_count:27,generatable_count:27,reset_needed_count:0,results:[]},configuration:{exam_code:'PILOT-ACCESS',enabled:true},blob:new Blob(['Candidate Name,Candidate ID,Exam Code,PIN\nA,PILOT000,PILOT-ACCESS,TESTPIN\n'],{type:'text/csv'})}
  globalThis.__pilotAccess=f
  const oldDocument=globalThis.document,oldCreate=URL.createObjectURL
  URL.createObjectURL=blob=>{f.downloads.push(blob);return 'blob:pilot-fixture'}
  globalThis.document={body:{appendChild(){}},createElement(){return{click(){f.clicked=true},remove(){}}}}
  const server=await createServer({server:{middlewareMode:true,hmr:false},appType:'custom',optimizeDeps:{noDiscovery:true,include:[]},plugins:[{name:'pilot-access-controller',enforce:'pre',
    resolveId(id){if(id.startsWith('pilot-fixture-'))return '\0'+id},
    load(id){
      if(id==='\0pilot-fixture-hooks')return `export * from 'react';
        export function useState(initial){const f=globalThis.__pilotAccess,i=f.cursor++;if(!(i in f.cells))f.cells[i]=typeof initial==='function'?initial():initial;return[f.cells[i],next=>f.cells[i]=typeof next==='function'?next(f.cells[i]):next]}
        export function useRef(initial){const f=globalThis.__pilotAccess,i=f.cursor++;if(!(i in f.cells))f.cells[i]={current:initial};return f.cells[i]}
        export function useReducer(reducer,initial){const[s,set]=useState(initial);return[s,event=>set(previous=>reducer(previous,event))]}
        export function useEffect(fn,deps){const f=globalThis.__pilotAccess,i=f.cursor++,old=f.cells[i];if(!old||deps.some((v,n)=>v!==old[n])){f.cells[i]=deps;const cleanup=fn();if(cleanup)f.cleanups.push(cleanup)}}`
      if(id==='\0pilot-fixture-router')return `export {Link} from 'react-router-dom';export function useLocation(){return globalThis.__pilotAccess.location}`
      if(id==='\0pilot-fixture-read')return `export * from '/src/pages/staff/exam-ui.jsx';export function useOwnerRead(key){const f=globalThis.__pilotAccess;return{data:key.includes(':config:')?f.configuration:key.includes(':credentials:')?f.credentials:{count:300,eligible_count:300,results:[]}}}`
      if(id==='\0pilot-fixture-service')return `export * from '/src/services/assessments.js';export async function examRequest(institution,path,options){const f=globalThis.__pilotAccess;f.calls.push({institution,path,options});if(f.pending)await f.pending;if(f.failure)throw f.failure;return options?.responseType==='blob'?f.blob:{}}`
    },
    transform(source,id){if(id.endsWith('/src/pages/staff/ExamAccess.jsx'))return source.replace("from 'react'","from 'pilot-fixture-hooks'").replace("from 'react-router-dom'","from 'pilot-fixture-router'").replace("from './exam-ui.jsx'","from 'pilot-fixture-read'").replace("from '../../services/assessments.js'","from 'pilot-fixture-service'")},
  }]})
  try{
    const {default:Access}=await server.ssrLoadModule('/src/pages/staff/ExamAccess.jsx')
    function walk(node){return node&&typeof node==='object'?[node,...React.Children.toArray(node.props?.children).flatMap(walk)]:[]}
    function draw(extra={}){f.cursor=0;return walk(Access({institutionId:7,exam,t:value=>value,direction:'ltr',onUpdate(){f.updated=true},...extra}))}
    await run(f,draw)
  }finally{globalThis.document=oldDocument;URL.createObjectURL=oldCreate;delete globalThis.__pilotAccess;await server.close()}
}
const generation=nodes=>nodes.find(n=>n.props?.children?.[0]==='Generate credentials for')

test('Access shows separate eligibility counts and generates only 27 missing credentials as one download',async()=>controller(async(f,draw)=>{
  let nodes=draw();nodes=draw()
  const text=nodes.flatMap(n=>React.Children.toArray(n.props?.children)).filter(v=>typeof v==='string').join(' ')
  assert.match(text,/Candidate eligibility/);assert.match(text,/candidates assigned/);assert.doesNotMatch(text,/Remove direct/)
  const button=generation(nodes);assert.equal(button.props.children[2],27);assert.equal(button.props.disabled,false)
  let resolve;f.pending=new Promise(done=>resolve=done)
  const work=button.props.onClick();await button.props.onClick();resolve();await work
  assert.equal(f.calls.length,1)
  assert.equal(f.calls[0].path,'11/quick-access/credentials/generate-sheet/')
  assert.deepEqual(f.calls[0].options,{method:'POST',body:{expected_count:27},responseType:'blob'})
  assert.deepEqual(f.downloads,[f.blob]);assert.equal(f.clicked,true)
  nodes=draw();assert.equal(generation(nodes).props.disabled,true)
  const download=nodes.find(n=>n.props?.children==='Download credential sheet')
  download.props.onClick();assert.equal(f.calls.length,1);assert.equal(f.downloads.length,2)
  f.location={key:'next-exam'};nodes=draw({institutionId:8,exam:{...exam,id:12}})
  assert.ok(!nodes.some(n=>n.props?.children==='Download credential sheet'))
}))

test('saved Quick delivery only configures its exam code and never generates credentials implicitly',async()=>controller(async(f,draw)=>{
  const quick={...exam,candidate_access:'access_code',quick_access_configured:false}
  f.configuration=null
  let nodes=draw({exam:quick});nodes=draw({exam:quick})
  assert.ok(!nodes.some(n=>n.type==='input'&&n.props.type==='radio'))
  assert.equal(f.calls.length,0)
  nodes.find(n=>n.type==='input'&&n.props.maxLength===32).props.onChange({target:{value:'PILOT-NEW'}})
  nodes=draw({exam:quick});await nodes.find(n=>n.type==='form').props.onSubmit({preventDefault(){}})
  assert.equal(f.calls[0].path,'11/quick-access/')
  assert.deepEqual(f.calls[0].options.body,{exam_code:'PILOT-NEW',enabled:true})
  assert.ok(f.calls.every(c=>!c.path.includes('credentials')))
}))

test('locked exams group eligibility and zero missing credentials disable bulk generation',async()=>controller(async(f,draw)=>{
  let nodes=draw({exam:{...exam,status:'scheduled'}});nodes=draw({exam:{...exam,status:'scheduled'}})
  assert.equal(generation(nodes).props.disabled,true)
  f.credentials={...f.credentials,generatable_count:0}
  assert.equal(generation(draw()).props.disabled,true)
  nodes=draw({exam:{...exam,candidate_access:'assigned_group',quick_access_configured:false,delivery_mode:'account_login'}})
  assert.ok(!nodes.some(n=>n.type==='input'&&n.props.type==='radio'))
  assert.equal(generation(nodes),undefined)
}))

test('late generation after leaving Access cannot reveal or download credentials',async()=>controller(async(f,draw)=>{
  draw();const nodes=draw();let resolve;f.pending=new Promise(done=>resolve=done)
  const work=generation(nodes).props.onClick()
  f.cleanups.forEach(fn=>fn());resolve();await work
  assert.deepEqual(f.downloads,[]);assert.equal(f.updated,undefined)
}))

test('download failure retains the sheet for retry without issuing another PIN',async()=>controller(async(f,draw)=>{
  draw();let nodes=draw()
  globalThis.document.createElement=()=>{throw Error('Download blocked')}
  await generation(nodes).props.onClick()
  nodes=draw();assert.ok(nodes.some(n=>n.props?.role==='alert'))
  assert.ok(nodes.some(n=>n.props?.children==='Download credential sheet'))
  assert.equal(f.calls.length,1)
}))

test('Quick delivery survives tab changes and reopens without writes',async()=>controller(async(f,draw)=>{
  for(const key of ['access','questions','access-again','refresh']) {
    f.location={key};const nodes=draw()
    assert.ok(nodes.some(n=>n.type==='h3'&&n.props.children==='Quick Exam'))
    assert.ok(generation(nodes))
    assert.ok(!nodes.some(n=>n.type==='input'&&n.props.type==='radio'))
  }
  assert.equal(f.calls.length,0)
}))
