const test=require('node:test');
const assert=require('node:assert/strict');
const vm=require('node:vm');const fs=require('node:fs');const path=require('node:path');
class Element {
  constructor(){this.children=[];this.attributes={};this.style={};this.value='';this.scrollTop=0;this.classList={toggle(){},contains(){return false;}};}
  append(...items){this.children.push(...items);} prepend(...items){this.children.unshift(...items);}
  replaceChildren(){this.children=[];} setAttribute(k,v){this.attributes[k]=v;} addEventListener(){}
}
function deferred(){let resolve;const promise=new Promise(r=>resolve=r);return{resolve,promise};}
function setup(api={}){
  const elements=new Map();const el=id=>{if(!elements.has(id))elements.set(id,new Element());return elements.get(id);};
  const notices=[];
  const c=vm.createContext({Date,Map,Set,setTimeout(){},crypto:{randomUUID:()=> 'new'},currentLanguage:'zh',currentSessionId:'A',currentProjectPath:'',
    hasAiKey:true,aiIsLoading:false,currentAgentRunId:null,currentAgentApprovalId:null,
    aiChatHistory:[{role:'user',content:'A request'}],allSessions:[{id:'A',title:'A title',summary:'Alpha summary',msg_count:1},{id:'B',title:'B title',summary:'Beta summary',msg_count:1}],
    document:{getElementById:el,createElement:()=>new Element(),querySelector:()=>new Element(),addEventListener(){}},
    window:{innerWidth:1280,addEventListener(){},pywebview:{api:{chat_save_session:async id=>({ok:true,metadata:{id,title:id+' title',summary:id+' summary',msg_count:1}}),...api}}},
    aiSessionList:el('ai-session-list'),aiChatInput:el('ai-chat-input'),aiSendBtn:el('ai-send-btn'),aiSkillPreview:el('ai-skill-preview'),agentResumeButton:el('agent-resume'),
    renderChatHistory(){},resetAgentRunPanel(){},resizeAgentChatInput(){},updateAgentDialogControls(){},
    agentStatusLabel:s=>s,showToast:(...args)=>notices.push(args),showCustomDialog:async()=>false,copyAgentText(){}});
  for(const file of ['agent-workspace.js','session-controller.js'])vm.runInContext(fs.readFileSync(path.join(__dirname,'../static',file),'utf8'),c);
  return{c,el,notices};
}
test('session search includes summary and rows have separate title preview and metadata',()=>{
  const {c,el}=setup();el('session-search').value='Beta';c.renderSessionList();
  const rows=c.aiSessionList.children.filter(e=>e.className?.startsWith('ai-session-item'));
  assert.equal(rows.length,1);const open=rows[0].children[0];
  assert.equal(open.children[0].textContent,'B title');
  assert.equal(open.children[1].textContent,'Beta summary');
  assert.match(open.children[2].children[0].textContent,/1/);
});
test('AI summary completion updates its captured conversation while another one is open',async()=>{
  const wait=deferred();const {c,el}=setup({chat_summarize_session:()=>wait.promise});
  const summarizing=c.summarizeCurrentAgentSession();await new Promise(r=>setImmediate(r));
  c.currentSessionId='B';c.aiChatHistory=[{role:'user',content:'B request'}];
  wait.resolve({ok:true,metadata:{id:'A',title:'A summarized',summary:'A decision',msg_count:1}});
  await summarizing;c.renderAgentSessionOverview();
  assert.equal(c.allSessions[0].title,'A summarized');
  assert.equal(el('agent-session-heading').textContent,'B title');
  assert.equal(c.aiChatHistory[0].content,'B request');
});
test('failed AI summary retains existing title and summary and clears busy state',async()=>{
  const {c,el}=setup({chat_summarize_session:async()=>({error:'provider unavailable'})});
  await c.summarizeCurrentAgentSession();
  assert.equal(c.allSessions[0].title,'A title');assert.equal(c.allSessions[0].summary,'A summary');
  assert.equal(el('agent-summary-generate').disabled,false);
});
test('rename applies to its captured conversation without changing the current one',async()=>{
  const wait=deferred();const {c,el}=setup({chat_rename_session:()=>wait.promise});c.showCustomDialog=async()=> 'Renamed A';
  const renaming=c.renameCurrentAgentSession();await new Promise(r=>setImmediate(r));
  c.currentSessionId='B';c.aiChatHistory=[{role:'user',content:'B'}];
  wait.resolve({ok:true,metadata:{id:'A',title:'Renamed A',summary:'A summary',msg_count:1}});await renaming;
  c.renderAgentSessionOverview();assert.equal(el('agent-session-heading').textContent,'B title');
});
test('a task in another conversation preserves the composed message instead of sending it',async()=>{
  let calls=0;const {c}=setup({agent_start_async:async()=>{calls++;}});
  vm.runInContext("activeAgentJobs.set('run-A',{sid:'A'})",c);c.currentSessionId='B';c.aiChatInput.value='Pending request';
  await c.sendAIMessage();assert.equal(calls,0);assert.equal(c.aiChatInput.value,'Pending request');
});
test('long conversation history initially bounds rendered rows and can load more',()=>{
  const {c}=setup();c.allSessions=Array.from({length:150},(_,i)=>({id:String(i),title:'Conversation '+i,summary:'Summary'}));
  c.renderSessionList();assert.equal(c.aiSessionList.children.filter(e=>e.className?.startsWith('ai-session-item')).length,60);
  c.aiSessionList.children.find(e=>e.className==='session-more').onclick();
  assert.equal(c.aiSessionList.children.filter(e=>e.className?.startsWith('ai-session-item')).length,120);
});
test('an updated conversation moves ahead of older rows without waiting for a reload',()=>{
  const {c}=setup();c.allSessions=[{id:'A',title:'Old',updated_at:'2026-09-01T10:00:00'},{id:'B',title:'Recent',updated_at:'2026-10-01T10:00:00'}];
  c.renderSessionList();
  const rows=c.aiSessionList.children.filter(e=>e.className?.startsWith('ai-session-item'));
  assert.equal(rows[0].children[0].children[0].textContent,'Recent');
});
