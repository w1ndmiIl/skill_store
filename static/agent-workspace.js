// Conversation presentation is separate from task execution and approval state.
const sessionSummaryRequests = new Set();
function sessionDisplayTitle(session) {
  const title = String(session?.title || '').replace(/\s+/g, ' ').trim();
  return title || (currentLanguage === 'zh' ? '新会话' : 'New Chat');
}
function sessionCalendarGroup(session) {
  const date = new Date(session.updated_at || session.created_at || '');
  if (!Number.isFinite(date.getTime())) return currentLanguage === 'zh' ? '新会话' : 'New';
  const now = new Date();
  const days = Math.round((Date.UTC(now.getFullYear(), now.getMonth(), now.getDate()) - Date.UTC(date.getFullYear(), date.getMonth(), date.getDate())) / 86400000);
  return (currentLanguage === 'zh' ? ['今天', '昨天', '最近 7 天', '更早'] : ['Today', 'Yesterday', 'Last 7 days', 'Earlier'])[days <= 0 ? 0 : days === 1 ? 1 : days < 7 ? 2 : 3];
}
function sessionShortTime(session) {
  const date = new Date(session.updated_at || session.created_at || '');
  if (!Number.isFinite(date.getTime())) return '';
  const now = new Date();
  return date.toLocaleDateString() === now.toLocaleDateString()
    ? date.toLocaleTimeString(currentLanguage === 'zh' ? 'zh-CN' : 'en-GB', {hour:'2-digit',minute:'2-digit'})
    : `${date.getMonth() + 1}/${date.getDate()}`;
}
function sessionLiveStatus(session) {
  const job = [...activeAgentJobs.values()].find(j => j.sid === session.id && !j.finishing);
  if (job) return job.stopping ? 'cancelled' : 'running';
  return session.last_status || '';
}
function renderAgentSessionOverview() {
  const heading = document.getElementById('agent-session-heading');
  if (!heading) return;
  const session = allSessions.find(s => s.id === currentSessionId) || {};
  const title = sessionDisplayTitle(session);
  heading.textContent = title; heading.title = title;
  const meta = document.getElementById('agent-session-meta');
  const count = aiChatHistory.filter(m => m.role === 'user' || m.role === 'assistant').length;
  meta.textContent = count ? `${count} ${currentLanguage === 'zh' ? '条消息' : 'messages'}${sessionShortTime(session) ? ' · ' + sessionShortTime(session) : ''}` : (currentLanguage === 'zh' ? '开始一个新的 Skill 任务' : 'Start a new Skill task');
  const status = sessionLiveStatus({...session, id: currentSessionId});
  const badge = document.getElementById('agent-session-status');
  badge.hidden = !status; badge.className = `conversation-status ${status}`;
  badge.textContent = status ? agentStatusLabel(status) : '';
  const summary = document.getElementById('agent-summary-content');
  summary.textContent = session.summary || (count ? (session.preview || (currentLanguage === 'zh' ? '保存会话后更新摘要。' : 'The summary updates after saving.')) : (currentLanguage === 'zh' ? '开始对话后，会自动整理需求与最新进展。' : 'Your goal and progress will appear here as the conversation grows.'));
  document.getElementById('agent-conversation-summary').hidden = !count;
  const summarize = document.getElementById('agent-summary-generate');
  summarize.disabled = !count || sessionSummaryRequests.has(currentSessionId) || Boolean([...activeAgentJobs.values()].find(j => j.sid === currentSessionId));
  summarize.textContent = sessionSummaryRequests.has(currentSessionId) ? (currentLanguage === 'zh' ? '正在生成…' : 'Summarizing…') : (currentLanguage === 'zh' ? '生成 AI 摘要' : 'Generate AI summary');
  summarize.title = currentLanguage === 'zh' ? '会话内容将发送至已配置的 AI 服务，用于生成标题和摘要。' : 'Conversation content is sent to your configured AI service to generate a title and summary.';
  document.getElementById('agent-session-rename').disabled = !count;
}
function applySessionMetadata(sid, metadata) {
  if (!metadata) return;
  const existing = allSessions.find(s => s.id === sid);
  if (existing) Object.assign(existing, metadata);
  else allSessions.unshift({...metadata, id:sid});
  renderSessionList();
  if (sid === currentSessionId) renderAgentSessionOverview();
}
async function renameCurrentAgentSession() {
  const sid = currentSessionId;
  if (!sid || !aiChatHistory.length || !await saveCurrentSession()) return;
  const name = await showCustomDialog({title:uiText('重命名会话','Rename conversation'),message:uiText('输入一个便于查找的标题（最多 60 个字符）。','Enter a helpful title (up to 60 characters).'),isPrompt:true,
    placeholder:sessionDisplayTitle(allSessions.find(s=>s.id===sid)),confirmText:uiText('保存标题','Save title')});
  if (typeof name !== 'string' || !name.trim()) return;
  try {
    const r = await window.pywebview.api.chat_rename_session(sid, name.trim());
    if (r.error) throw new Error(r.error);
    applySessionMetadata(sid, r.metadata);
    if(sid!==currentSessionId)showToast(uiText('会话标题已更新','Conversation renamed'),'success');
  } catch(e) {showToast(e.message,'error');}
}
async function summarizeCurrentAgentSession() {
  const sid = currentSessionId;
  if (!sid || !aiChatHistory.length || sessionSummaryRequests.has(sid)) return;
  if (!hasAiKey) {showToast(uiText('请先在设置中配置 AI 服务；当前自动摘要仍可使用。','Configure an AI service first; the local overview remains available.'),'warning');return;}
  if (!await saveCurrentSession()) return;
  sessionSummaryRequests.add(sid); renderAgentSessionOverview();
  try {
    const r = await window.pywebview.api.chat_summarize_session(sid);
    if (r.error) throw new Error(r.error);
    applySessionMetadata(sid, r.metadata);
    if(sid!==currentSessionId)showToast(uiText('后台会话摘要已更新','Background conversation summary updated'),'success');
  } catch(e) {showToast(e.message,'error');}
  finally {sessionSummaryRequests.delete(sid);if(currentSessionId===sid)renderAgentSessionOverview();}
}
function toggleAgentSessionPanel(force) {
  const container = document.querySelector('.ai-modal-container');
  if (!container) return;
  container.classList.toggle('session-panel-open', force === undefined ? !container.classList.contains('session-panel-open') : force);
}
function refreshAgentWorkspaceLabels() {
  const set = (id, zh, en) => {const el=document.getElementById(id);if(el)el.textContent=currentLanguage==='zh'?zh:en;};
  set('agent-summary-label','对话摘要','Conversation summary');
  set('agent-run-eyebrow','本次任务','Current task');
  set('agent-jump-latest','回到最新消息 ↓','Jump to latest ↓');
  const rename=document.getElementById('agent-session-rename');
  if(rename){rename.title=currentLanguage==='zh'?'重命名会话':'Rename conversation';rename.setAttribute('aria-label',rename.title);}
  const history=document.getElementById('agent-history-toggle');
  if(history){history.title=currentLanguage==='zh'?'会话列表':'Conversations';history.setAttribute('aria-label',history.title);}
  const input=document.getElementById('session-search');
  if(input){input.placeholder=currentLanguage==='zh'?'搜索标题或摘要…':'Search titles or summaries…';input.setAttribute('aria-label',input.placeholder);}
  renderAgentSessionOverview();
}
function friendlyAgentTool(name) {
  const labels={search_skills:['搜索技能','Search Skills'],inspect_skill:['阅读技能正文','Read Skill'],audit_skill_library:['检查技能库','Audit library'],draft_skill_change:['预览技能修改','Preview changes'],apply_skill_change:['保存技能修改','Save changes'],preview_project_sync:['预览项目同步','Preview sync'],apply_project_sync:['应用项目同步','Apply sync'],web_research:['检索资料','Research'],preview_remote_skill_install:['预览远程技能','Preview remote Skill'],apply_remote_skill_install:['安装远程技能','Install remote Skill'],preview_remote_skill_collection:['预览技能集合','Preview collection'],apply_remote_skill_collection:['安装技能集合','Install collection'],search_skillhub_catalog:['搜索官方目录','Search catalog'],preview_skillhub_catalog_install:['预览目录安装','Preview catalog install'],apply_skillhub_catalog_install:['应用目录安装','Apply catalog install']};
  return labels[name]?.[currentLanguage==='zh'?0:1]||name;
}
function updateAgentLatestButton() {
  const button=document.getElementById('agent-jump-latest');
  if(button)button.hidden=aiChatMessages.scrollHeight-aiChatMessages.clientHeight-aiChatMessages.scrollTop<100;
}
function scrollToAgentLatest() {
  aiChatMessages.scrollTop=aiChatMessages.scrollHeight;
  updateAgentLatestButton();
}
if(typeof document!=='undefined')document.addEventListener('DOMContentLoaded',()=>{
  document.getElementById('ai-chat-messages')?.addEventListener('scroll',updateAgentLatestButton,{passive:true});
});
if(typeof window!=='undefined' && typeof window.addEventListener==='function'){
  let wasNarrow=window.innerWidth<=820;
  window.addEventListener('resize',()=>{
    const narrow=window.innerWidth<=820;
    if(narrow && !wasNarrow){agentPanelCollapsed=true;updateAgentDialogControls();}
    wasNarrow=narrow;
  });
}
if (typeof module !== 'undefined') module.exports = {sessionDisplayTitle,sessionCalendarGroup,sessionShortTime};
