const test=require('node:test');
const assert=require('node:assert/strict');
const fs=require('node:fs');const vm=require('node:vm');const crypto=require('node:crypto');
const path=require('node:path');
const source=fs.readFileSync(path.join(__dirname,'../static/session-controller.js'),'utf8');
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return{promise,resolve};}
function harness(api={}){
 const noop=()=>{};const elements=new Map();const el=id=>{if(!elements.has(id))elements.set(id,{hidden:false,textContent:'',disabled:false,value:'',style:{}});return elements.get(id);};
 const c=vm.createContext({crypto,Date,Map,Set,setTimeout:noop,currentLanguage:'zh',currentSessionId:'A',aiChatHistory:[{role:'user',content:'A'}],allSessions:[],
  window:{pywebview:{api}},document:{getElementById:el,createElement:()=>({append:noop,setAttribute:noop})},aiSessionList:{replaceChildren:noop,append:noop},
  aiSkillPreview:{style:{}},aiGeneratedSkill:null,aiIsLoading:false,currentAgentRunId:null,currentAgentApprovalId:null,currentProjectPath:'',
  renderChatHistory:noop,resetAgentRunPanel:noop,showToast:noop,showCustomDialog:async()=>false,copyAgentText:async()=>{},
  aiSendBtn:{disabled:false},agentResumeButton:{hidden:false},aiChatInput:{value:'',focus:noop},resizeAgentChatInput:noop,renderAgentRun:noop,
  fetchSkills:async()=>{},fetchProjects:async()=>{}});
 vm.runInContext(source,c);return c;
}
test('out-of-order session load cannot replace the latest selection',async()=>{
 const requests={};const c=harness({chat_load_session:id=>(requests[id]=deferred()).promise,agent_list_tasks:async()=>[]});
 const b=c.switchToSession('B',false),d=c.switchToSession('C',false);
 requests.C.resolve({session:{messages:[{role:'user',content:'C'}]}});await d;
 requests.B.resolve({session:{messages:[{role:'user',content:'B'}]}});await b;
 assert.equal(c.currentSessionId,'C');assert.equal(c.aiChatHistory[0].content,'C');
});
test('failed save keeps conversation when discard was not explicitly chosen',async()=>{
 const c=harness({chat_save_session:async()=>({error:'disk full'})});
 await c.switchToSession('B');assert.equal(c.currentSessionId,'A');assert.equal(c.aiChatHistory[0].content,'A');
});
test('failed deletion does not remove a visible session',async()=>{
 const c=harness({chat_delete_session:async()=>({error:'disk full'})});c.showCustomDialog=async()=>true;
 c.allSessions=[{id:'A',title:'A'}];await c.deleteSession('A');assert.equal(c.allSessions.length,1);assert.equal(c.currentSessionId,'A');
});
test('save completion updates the captured session summary',async()=>{
 const request=deferred();const c=harness({chat_save_session:()=>request.promise});c.allSessions=[{id:'A',title:'old'},{id:'B',title:'B'}];
 const save=c.saveCurrentSession();c.currentSessionId='B';request.resolve({ok:true});await save;
 assert.equal(c.allSessions[0].title,'A');assert.equal(c.allSessions[1].title,'B');
});
test('background completion in A never replaces B messages',async()=>{
 const request=deferred();const c=harness({agent_poll:()=>request.promise,chat_load_session:async()=>({session:{messages:[{role:'assistant',content:'Answer A'}]}}),chat_list_sessions:async()=>[]});
 c.currentSessionId='B';c.aiChatHistory=[{role:'user',content:'B'}];c.watchAgentRun('run-a','A');request.resolve({status:'completed',final_answer:'Answer A',busy:false});
 await new Promise(r=>setImmediate(r));assert.equal(c.aiChatHistory[0].content,'B');
});
test('generation in flight prevents losing its owning view',async()=>{
 const c=harness({});c.aiIsLoading=true;await c.createNewSession();assert.equal(c.currentSessionId,'A');
});

test('initial history loading cannot undo a newer new-chat action',async()=>{
 const request=deferred();const c=harness({chat_list_sessions:()=>request.promise});
 const loading=c.loadSessionList(true);await c.createNewSession(false);const newId=c.currentSessionId;
 request.resolve([{id:'old',title:'Old',msg_count:1}]);await loading;
 assert.equal(c.currentSessionId,newId);assert.equal(c.aiChatHistory.length,0);assert.ok(c.allSessions.some(s=>s.id===newId));
});

test('sending while a new chat is still saving cannot target the old chat',async()=>{
 const saved=deferred();let started=0;const c=harness({chat_save_session:()=>saved.promise,agent_start_async:async()=>{started++;return{error:'unexpected'};}});
 c.aiChatInput.value='new question';const transition=c.createNewSession();await c.sendAIMessage();
 assert.equal(started,0);assert.equal(c.aiChatInput.value,'new question');assert.equal(c.aiChatInput.disabled,true);
 saved.resolve({ok:true});await transition;assert.notEqual(c.currentSessionId,'A');assert.equal(c.aiChatInput.disabled,false);
});
