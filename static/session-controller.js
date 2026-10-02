// Session ownership, save errors and background progress are handled together.
let sessionRequestId = 0;
let sessionListRequestId = 0;
let sessionTransition = false;
function setSessionTransition(value){
  sessionTransition=value;
  aiChatInput.disabled=value;
  aiSendBtn.disabled=value||aiIsLoading;
}
const activeAgentJobs = new Map();
const unreadSessions = new Set();
const workspaceTranslations=new Map();
const uiText=(zh,en)=>{workspaceTranslations.set(zh,[zh,en]);workspaceTranslations.set(en,[zh,en]);return currentLanguage==='zh'?zh:en;};

async function confirmSessionLeave() {
  // Generation uses the legacy synchronous endpoint; retain its owning view.
  if (aiIsLoading && !activeAgentJobs.has(currentAgentRunId)) {
    showToast(uiText('请等待当前生成结束', 'Wait for generation to finish'), 'warning');
    return false;
  }
  if (await saveCurrentSession()) return true;
  const choice = await showCustomDialog({title:uiText('会话尚未保存','Chat not saved'),
    message:uiText('内容仍保留。重试保存，或先复制对话。','Your messages are retained. Retry saving or copy the conversation.'),
    confirmText:uiText('重试保存','Retry'),secondaryText:uiText('复制对话','Copy'),secondaryValue:'copy'});
  if (choice === true) return saveCurrentSession();
  if (choice === 'copy') {
    await copyAgentText(aiChatHistory.map(m=>`${m.role}: ${m.content}`).join('\n\n'));
    return false;
  }
  return Boolean(await showCustomDialog({title:uiText('放弃并切换？','Discard and leave?'),
    message:uiText('仅在确认不需要这些未保存消息时继续。','Continue only if you no longer need these unsaved messages.'),
    confirmText:uiText('放弃并切换','Discard and leave'),emoji:'⚠️'}));
}
async function saveCurrentSession() {
  const sid = currentSessionId;
  if (!sid || aiChatHistory.length === 0) return true;
  const messages = aiChatHistory.map(m=>({...m}));
  const title = ''; // Backend derives an overview while preserving custom titles.
  try {
    const r = await window.pywebview.api.chat_save_session(sid,title,messages);
    if (r?.error) throw new Error(r.error);
    const existing = allSessions.find(s=>s.id===sid);
    const metadata=r.metadata||{id:sid,title:messages.find(m=>m.role==='user')?.content?.slice(0,30)||uiText('新会话','New Chat'),msg_count:messages.length};
    if (existing) Object.assign(existing,metadata);
    else allSessions.unshift(metadata);
    renderSessionList();
    if(sid===currentSessionId && typeof renderAgentSessionOverview==='function')renderAgentSessionOverview();
    return true;
  } catch(e) { showToast(uiText('会话保存失败：','Chat save failed: ')+e.message,'error'); return false; }
}
async function loadSessionList(selectSession=false) {
  const intent=sessionRequestId,listRequest=++sessionListRequestId;
  try {
    const sessions = await window.pywebview.api.chat_list_sessions();
    if(listRequest!==sessionListRequestId)return;
    if (!Array.isArray(sessions)) throw new Error(sessions?.error || 'Invalid session list');
    if(currentSessionId && !sessions.some(s=>s.id===currentSessionId)) sessions.unshift({id:currentSessionId,title:aiChatHistory.find(m=>m.role==="user")?.content?.slice(0,30)||uiText("新会话","New Chat"),msg_count:aiChatHistory.length});
    allSessions = sessions;
    renderSessionList();
    if (selectSession && intent===sessionRequestId) {
      const preferred = sessions.find(s=>s.id===currentSessionId) || sessions[0];
      if (preferred) await switchToSession(preferred.id,false);
      else await createNewSession(false);
    }
  } catch(e) {
    showToast(uiText('历史读取失败，原数据已保留：','History could not be read; original retained: ')+e.message,'error');
    document.getElementById('recover-chat-button').hidden=false;
  }
}
let sessionListLimit = 60;
function renderSessionList() {
  const scroll=aiSessionList.scrollTop||0;
  aiSessionList.replaceChildren();
  const query=(document.getElementById('session-search')?.value||'').trim().toLocaleLowerCase();
  const filtered=allSessions.filter(s=>[s.title,s.summary,s.preview].filter(Boolean).join(' ').toLocaleLowerCase().includes(query));
  filtered.sort((a,b)=>(Date.parse(b.updated_at||b.created_at||'')||0)-(Date.parse(a.updated_at||a.created_at||'')||0));
  let group='';
  for(const s of filtered.slice(0,sessionListLimit)) {
    const label=typeof sessionCalendarGroup==='function'?sessionCalendarGroup(s):'';
    if(label && label!==group){const heading=document.createElement('div');heading.className='session-group-label';heading.textContent=label;aiSessionList.append(heading);group=label;}
    const row=document.createElement('div');row.className='ai-session-item'+(s.id===currentSessionId?' active':'');
    const open=document.createElement('button');open.type='button';open.className='session-open';
    const title=typeof sessionDisplayTitle==='function'?sessionDisplayTitle(s):(s.title||uiText('新会话','New Chat'));
    open.title=title;open.setAttribute('aria-label',title);if(s.id===currentSessionId)open.setAttribute('aria-current','true');
    const name=document.createElement('span');name.className='ai-session-item-title';name.textContent=title;
    if(unreadSessions.has(s.id)){const dot=document.createElement('span');dot.className='session-unread';dot.setAttribute('aria-label',uiText('未读','Unread'));name.prepend?.(dot);}
    const preview=document.createElement('span');preview.className='ai-session-item-preview';preview.textContent=s.summary||s.preview||uiText('开始新的 Skill 任务','Start a new Skill task');
    const meta=document.createElement('span');meta.className='ai-session-item-meta';
    const count=document.createElement('span');count.textContent=(s.msg_count||0)+' '+uiText('条消息','messages');meta.append(count);
    const status=typeof sessionLiveStatus==='function'?sessionLiveStatus(s):'';
    if(status){const badge=document.createElement('span');badge.className='conversation-status '+status;badge.textContent=typeof agentStatusLabel==='function'?agentStatusLabel(status):status;meta.append(badge);}
    const time=document.createElement('span');time.className='session-item-time';time.textContent=typeof sessionShortTime==='function'?sessionShortTime(s):'';meta.append(time);
    open.append(name,preview,meta);open.onclick=()=>switchToSession(s.id);
    const del=document.createElement('button');del.type='button';del.className='ai-session-del';del.textContent='×';
    del.setAttribute('aria-label',uiText('删除会话','Delete chat')+': '+title);del.onclick=()=>deleteSession(s.id);
    row.append(open,del);aiSessionList.append(row);
  }
  if(!filtered.length){const empty=document.createElement('div');empty.className='session-search-empty';empty.textContent=query?uiText('没有匹配的会话','No matching conversations'):uiText('新建会话，开始整理 Skill。','Start a conversation to work on Skills.');aiSessionList.append(empty);}
  if(filtered.length>sessionListLimit){const more=document.createElement('button');more.className='session-more';more.textContent=uiText('显示更多会话','Show more conversations');more.onclick=()=>{sessionListLimit+=60;renderSessionList();};aiSessionList.append(more);}
  const total=document.getElementById('ai-session-count');if(total)total.textContent=filtered.length+' '+uiText('个会话','conversations');
  aiSessionList.scrollTop=scroll;
  if(typeof renderAgentSessionOverview==='function')renderAgentSessionOverview();
}
async function switchToSession(sid,saveBeforeSwitch=true) {
  const request=++sessionRequestId;
  setSessionTransition(true);
  try {
  if(saveBeforeSwitch && !(await confirmSessionLeave())) return;
  if(request!==sessionRequestId) return;
  try {
    const r=await window.pywebview.api.chat_load_session(sid);
    if(request!==sessionRequestId) return;
    if(r.error) throw new Error(r.error);
    currentSessionId=sid;aiChatHistory=r.session.messages;
    if(r.metadata){const item=allSessions.find(s=>s.id===sid);if(item)Object.assign(item,r.metadata);else allSessions.unshift(r.metadata);}
    if(typeof toggleAgentSessionPanel==='function')toggleAgentSessionPanel(false);
    aiSkillPreview.style.display='none';aiGeneratedSkill=null;
    unreadSessions.delete(sid); aiIsLoading=false;
    renderSessionList();renderChatHistory();await loadAgentRunForSession();
  } catch(e){showToast(e.message,'error');}
  } finally { if(request===sessionRequestId)setSessionTransition(false); }
}
async function createNewSession(saveBeforeCreate=true) {
  const request=++sessionRequestId;
  setSessionTransition(true);
  try {
  if(saveBeforeCreate && !(await confirmSessionLeave())) return;
  if(request!==sessionRequestId) return;
  currentSessionId='s_'+crypto.randomUUID();aiChatHistory=[];
  aiSkillPreview.style.display='none';aiGeneratedSkill=null;aiIsLoading=false;
  currentAgentRunId=null;currentAgentApprovalId=null;
  const now=new Date().toISOString();
  allSessions.unshift({id:currentSessionId,title:uiText('新会话','New Chat'),msg_count:0,created_at:now,updated_at:now});
  renderSessionList();renderChatHistory();resetAgentRunPanel();updateAgentProgressControls();
  } finally { if(request===sessionRequestId)setSessionTransition(false); }
}
async function deleteSession(sid) {
  if([...activeAgentJobs.values()].some(j=>j.sid===sid)) {
    showToast(uiText('请先停止该会话的运行','Stop this chat task before deleting'),'warning');return;
  }
  if(!(await showCustomDialog({title:uiText('删除会话？','Delete chat?'),message:uiText('此操作将删除聊天记录。','This removes the chat history.'),emoji:'⚠️'})))return;
  try{
    const r=await window.pywebview.api.chat_delete_session(sid);if(r.error)throw new Error(r.error);
    allSessions=allSessions.filter(s=>s.id!==sid);
    if(currentSessionId===sid){++sessionRequestId;currentSessionId=null;aiChatHistory=[];
      if(allSessions.length)await switchToSession(allSessions[0].id,false);else await createNewSession(false);}
    renderSessionList();
  }catch(e){showToast(e.message,'error');}
}
async function loadAgentRunForSession(){
  const sid=currentSessionId,request=sessionRequestId;
  try{
    const tasks=await window.pywebview.api.agent_list_tasks();
    if(request!==sessionRequestId || sid!==currentSessionId)return;
    const task=tasks.find(t=>t.session_id===sid);
    if(!task){resetAgentRunPanel();updateAgentProgressControls();return;}
    const r=await window.pywebview.api.agent_poll(task.run_id);
    if(request!==sessionRequestId || sid!==currentSessionId)return;
    renderAgentRun(r);
    if(r.busy)watchAgentRun(task.run_id,sid);
    updateAgentProgressControls();
  }catch(e){showToast(e.message,'error');}
}
function updateAgentProgressControls(){
  const job=activeAgentJobs.get(currentAgentRunId);
  aiIsLoading=Boolean(job);const elsewhere=[...activeAgentJobs.values()].some(j=>j.sid!==currentSessionId&&!j.finishing);
  aiSendBtn.disabled=aiIsLoading||sessionTransition||elsewhere;
  const composer=document.getElementById('agent-composer-stop');if(composer){composer.hidden=!job;composer.disabled=Boolean(job?.stopping);composer.textContent=job?.stopping?uiText('正在停止…','Stopping…'):uiText('停止','Stop');}
  const hint=document.getElementById('ai-chat-input-hint');if(hint)hint.textContent=elsewhere?uiText('另一会话正在运行，可继续编辑，完成后发送。','Another conversation is running. Compose now and send when it finishes.'):uiText('Enter 发送 · Shift+Enter 换行','Enter to send · Shift+Enter for a new line');
  if(typeof renderAgentSessionOverview==='function')renderAgentSessionOverview();
  const button=document.getElementById('agent-stop-button');button.hidden=!job;
  button.disabled=Boolean(job?.stopping);
  button.textContent=job?.stopping?uiText('正在停止…','Stopping…'):uiText('停止','Stop');
  if(job)agentResumeButton.hidden=true;
  document.getElementById('agent-elapsed').textContent=job?uiText('已用时 ','Elapsed ')+Math.floor((Date.now()-job.started)/1000)+'s':'';
}
function watchAgentRun(runId,sid){
  if(activeAgentJobs.has(runId))return;
  const job={sid,started:Date.now(),stopping:false,failures:0};activeAgentJobs.set(runId,job);
  async function poll(){
    try{
      const r=await window.pywebview.api.agent_poll(runId);
      if(r.error||r.job_error){activeAgentJobs.delete(runId);updateAgentProgressControls();showToast(r.error||r.job_error,"error");return;}
      job.failures=0;
      if(currentSessionId===sid){renderAgentRun(r);const owner=allSessions.find(s=>s.id===sid);if(owner)owner.last_status=r.status;updateAgentProgressControls();}
      if(r.busy){setTimeout(poll,650);return;}
      job.finishing=true;
      if(r.final_answer){
        const session=await window.pywebview.api.chat_load_session(sid);
        if(currentSessionId===sid && session.session){aiChatHistory=session.session.messages;renderChatHistory();}
        else {unreadSessions.add(sid);showToast(uiText('后台会话已完成','Background chat completed'),'success');}
      }
      await loadSessionList(false);activeAgentJobs.delete(runId);updateAgentProgressControls();
      if(['completed','cancelled'].includes(r.status))await Promise.all([fetchSkills(),fetchProjects()]);
    }catch(e){job.failures++;if(job.failures===1)showToast(uiText("进度读取失败，正在重试：","Progress unavailable; retrying: ")+e.message,"warning");setTimeout(poll,Math.min(5000,job.failures*1000));}
  }
  updateAgentProgressControls();poll();
}
async function sendAIMessage(){
  const text=aiChatInput.value.trim();if(!text||aiIsLoading||sessionTransition)return;
  if([...activeAgentJobs.values()].some(j=>!j.finishing)){showToast(uiText('请等待当前任务结束，输入内容已保留。','Wait for the current task; your draft is retained.'),'info');return;}
  if(!currentSessionId)await createNewSession(false);
  ++sessionRequestId;
  const sid=currentSessionId;
  aiChatHistory.push({role:'user',content:text});aiChatInput.value='';resizeAgentChatInput();renderChatHistory();
  aiIsLoading=true;aiSendBtn.disabled=true;
  if(!(await saveCurrentSession())){aiIsLoading=false;aiSendBtn.disabled=false;return;}
  try{
    const r=await window.pywebview.api.agent_start_async(text,sid,currentProjectPath||'');
    if(r.error)throw new Error(r.error);
    if(currentSessionId===sid){currentAgentRunId=r.run_id;renderAgentRun(r);}
    watchAgentRun(r.run_id,sid);
  }catch(e){showToast(e.message,'error');}finally{updateAgentProgressControls();}
}
async function continueAgentRun(approvalId=''){
  const runId=currentAgentRunId,sid=currentSessionId;if(!runId||aiIsLoading||sessionTransition)return;
  try{const r=await window.pywebview.api.agent_continue_async(runId,approvalId);if(r.error)throw new Error(r.error);watchAgentRun(runId,sid);}
  catch(e){showToast(e.message,'error');}
}
async function approveAgentAction(){if(currentAgentApprovalId)return continueAgentRun(currentAgentApprovalId);}
async function resumeAgentRun(){return continueAgentRun();}
async function stopAgentRun(){
  const job=activeAgentJobs.get(currentAgentRunId);if(!job)return;
  const r=await window.pywebview.api.agent_stop(currentAgentRunId);
  if(r.error){showToast(r.error,'error');return;}
  job.stopping=true;updateAgentProgressControls();
  showToast(uiText('停止已请求；正在进行的操作结束后停止，已完成的修改会保留。','Stop requested; the current operation will finish and completed changes are retained.'),'info');
}
async function recoverChatHistory(){
  if(!await showCustomDialog({title:uiText('恢复历史备份？','Restore chat backup?'),message:uiText('当前文件会保留为损坏副本。','The current file will be preserved separately.')}))return;
  const r=await window.pywebview.api.chat_recover_sessions();if(r.error){showToast(r.error,'error');return;}
  document.getElementById('recover-chat-button').hidden=true;await loadSessionList(true);
}
