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
  const title = messages.find(m=>m.role==='user')?.content?.slice(0,30) || uiText('新会话','New Chat');
  try {
    const r = await window.pywebview.api.chat_save_session(sid,title,messages);
    if (r?.error) throw new Error(r.error);
    const existing = allSessions.find(s=>s.id===sid);
    if (existing) Object.assign(existing,{title,msg_count:messages.length});
    else allSessions.unshift({id:sid,title,msg_count:messages.length});
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
function renderSessionList() {
  aiSessionList.replaceChildren();
  const query = (document.getElementById('session-search')?.value || '').toLowerCase();
  for (const s of allSessions.filter(s=>(s.title||'').toLowerCase().includes(query))) {
    const row = document.createElement('div'); row.className='ai-session-item'+(s.id===currentSessionId?' active':'');
    const open = document.createElement('button');open.className='session-open';
    open.textContent=(unreadSessions.has(s.id)?'● ':'')+(s.title||uiText('新会话','New Chat'));
    open.onclick=()=>switchToSession(s.id);
    const del=document.createElement('button');del.className='ai-session-del';del.textContent='×';
    del.setAttribute('aria-label',uiText('删除会话','Delete chat'));del.onclick=()=>deleteSession(s.id);
    row.append(open,del);aiSessionList.append(row);
  }
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
  allSessions.unshift({id:currentSessionId,title:uiText('新会话','New Chat'),msg_count:0});
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
  aiIsLoading=Boolean(job);aiSendBtn.disabled=aiIsLoading||sessionTransition;
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
      if(currentSessionId===sid){renderAgentRun(r);updateAgentProgressControls();}
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
