// Workspace tools: recoverable editing, filtering and durable result panels.
const listPreferences = new Map();
let listPreferenceKey=null;
let listPage=0,listPageSignature="";
let editorVersion=null, editorSaveBusy=false, draftTimer=null;
let toolBusy=false, toolKind='';
const toolModal=document.createElement('div');
toolModal.id='workspace-tool-modal';toolModal.className='modal-overlay';
toolModal.setAttribute('role','dialog');toolModal.setAttribute('aria-modal','true');
toolModal.setAttribute('aria-labelledby','workspace-tool-title');toolModal.setAttribute('aria-hidden','true');toolModal.inert=true;
toolModal.innerHTML='<section class="modal-container workspace-tool-container"><header class="modal-header"><h3 id="workspace-tool-title"></h3><button type="button" id="workspace-tool-close" class="btn btn-secondary">×</button></header><div class="workspace-tool-actions"></div><div class="workspace-tool-body"></div><footer class="workspace-tool-footer" role="status"></footer></section>';
document.body.append(toolModal);
const toolBody=toolModal.querySelector('.workspace-tool-body'),toolActions=toolModal.querySelector('.workspace-tool-actions'),toolFooter=toolModal.querySelector('footer');
document.getElementById('workspace-tool-close').onclick=closeWorkspaceTool;
function closeWorkspaceTool(){if(toolBusy){showToast(uiText('请等待本项操作完成','Wait for the current operation'),'info');return;}deactivateModal(toolModal);}
function toolButton(label,action,parent=toolActions){const b=document.createElement('button');b.className='btn btn-secondary';b.type='button';b.textContent=label;b.onclick=async()=>{try{await action();}catch(e){showToast(e.message,'error');}};parent.append(b);return b;}
function openWorkspaceTool(title,kind){if(toolBusy)return false;toolKind=kind;document.getElementById('workspace-tool-title').textContent=title;toolBody.replaceChildren();toolActions.replaceChildren();toolFooter.textContent='';activateModal(toolModal);return true;}
function textBlock(text,parent=toolBody){const el=document.createElement('pre');el.className='tool-detail';el.textContent=text;parent.append(el);return el;}

async function openTrash(){
  if(!openWorkspaceTool(uiText('回收站','Trash'),'trash'))return;
  const items=await window.pywebview.api.list_deleted_skills();
  const selected=new Set();
  toolButton(uiText('全选可恢复项','Select restorable'),()=>{items.filter(i=>!i.conflict).forEach(i=>selected.add(i.token));draw();});
  toolButton(uiText('恢复所选','Restore selected'),()=>operate(false));
  toolButton(uiText('永久删除所选','Delete selected permanently'),()=>operate(true));
  toolButton(uiText('清空回收站','Empty trash'),async()=>{items.forEach(i=>selected.add(i.token));draw();await operate(true);});
  function draw(){toolBody.replaceChildren();for(const item of items){
    const row=document.createElement('label');row.className='tool-row';const check=document.createElement('input');check.type='checkbox';check.checked=selected.has(item.token);
    check.onchange=()=>check.checked?selected.add(item.token):selected.delete(item.token);
    const name=document.createElement('span');name.textContent=item.filename;
    const note=document.createElement('small');note.textContent=`${item.deleted_at} · ${item.source} · ${item.conflict?uiText('同名文件已存在，恢复不会覆盖','Name conflict; restore will not overwrite'):uiText('可恢复','Restorable')}`;
    row.append(check,name,note);toolBody.append(row);
  }if(!items.length)textBlock(uiText('回收站为空','Trash is empty'));toolFooter.textContent=uiText('共 ','Total ')+items.length;}
  async function operate(purge){
    if(toolBusy||!selected.size)return;
    let plan;
    if(purge){plan=await window.pywebview.api.preview_purge_trash([...selected]);
      if(!await showCustomDialog({title:uiText('永久删除所选文件？','Permanently delete selected files?'),message:plan.items.map(i=>i.filename).join('\n'),confirmText:uiText('永久删除，无法恢复','Delete permanently'),emoji:'⚠️'}))return;}
    toolBusy=true;const results=[];
    try{
      if(purge){const r=await window.pywebview.api.purge_trash([...selected],plan.token);if(r.error)throw new Error(r.error);results.push(...r.removed.map(n=>n+' ✓'),...r.errors.map(e=>e.filename+': '+e.error));}
      else for(const token of selected){const r=await window.pywebview.api.restore_deleted_skill(token);results.push((items.find(i=>i.token===token)?.filename||token)+': '+(r.error||r.warning||uiText('已恢复','Restored')));}
      await fetchSkills();
    }finally{toolBusy=false;}
    await openTrash();toolFooter.textContent=results.join('\n');
  }draw();
}

function workspaceFilterSkills(items){
  const key=currentProjectPath||'library';
  const sort=document.getElementById('skill-sort');
  if(!sort)return items;
  if(listPreferenceKey!==key){
    if(listPreferenceKey!==null)listPreferences.set(listPreferenceKey,{sort:sort.value,query:searchInput.value,category:activeCategoryFilter});
    const pref=listPreferences.get(key)||{};sort.value=pref.sort||'name';searchInput.value=pref.query||'';activeCategoryFilter=pref.category||null;listPreferenceKey=key;
  }
  return [...items].sort(sort.value==='modified'?(a,b)=>(b.modified_at||0)-(a.modified_at||0):(a,b)=>(a.display_title||a.title||a.filename).localeCompare(b.display_title||b.title||b.filename,currentLanguage));
}
function paginateSkillRows(items){
  const signature=JSON.stringify([currentProjectPath,searchInput.value,activeCategoryFilter,document.getElementById('skill-sort').value,items.length]);
  if(signature!==listPageSignature){listPage=0;listPageSignature=signature;}
  const size=100,pages=Math.max(1,Math.ceil(items.length/size));listPage=Math.min(listPage,pages-1);
  document.getElementById('skill-page-prev').disabled=listPage===0;
  document.getElementById('skill-page-next').disabled=listPage>=pages-1;
  document.getElementById('skill-page-number').textContent=items.length>size?`${listPage+1} / ${pages}`:'';
  document.getElementById('skill-pages').hidden=items.length<=size;
  return items.slice(listPage*size,(listPage+1)*size);
}

async function showStorageHealth(){
  try{const health=await window.pywebview.api.storage_health();for(const issue of health.issues||[]){
    showToast(uiText('本地数据需要恢复：','Local data needs recovery: ')+issue.kind,'error',{duration:15000,actionLabel:uiText('恢复备份','Restore backup'),onAction:async()=>{
      if(!await showCustomDialog({title:uiText('恢复最近有效备份？','Restore the last valid backup?'),message:uiText('损坏原文件会保留；备份之后的修改可能需要重新输入。','The damaged original is retained. Changes after the backup may need to be entered again.')}))return;
      const result=await window.pywebview.api.recover_storage(issue.kind);if(result.error)throw new Error(result.error);location.reload();
    }});
  }}catch(error){showToast(error.message,'error');}
}
async function recoverConfiguration(){const r=await window.pywebview.api.recover_config();if(r.error)throw new Error(r.error);location.reload();}

function draftKey(filename=editingFilename){return 'skillhub.draft.'+encodeURIComponent(skillsDirPath.textContent+'|'+filename);}
let draftWriteChain=Promise.resolve();
function retainEditorDraft(){
  if(!editingFilename||isViewingSkill||editorInitialSnapshot===null)return Promise.resolve(true);
  const filename=editingFilename;
  const draft={snapshot:JSON.parse(getEditorSnapshot()),version:editorVersion,at:Date.now()};
  try{localStorage.setItem(draftKey(filename),JSON.stringify(draft));}catch(_){}
  draftWriteChain=draftWriteChain.then(async()=>{
    try{const r=await window.pywebview.api.save_editor_draft(filename,draft);if(r.error)throw new Error(r.error);return true;}
    catch(e){showToast(uiText('草稿未能保存：','Draft could not be saved: ')+e.message,'error');return false;}
  });
  return draftWriteChain;
}
async function clearEditorDraft(){
  clearTimeout(draftTimer);await draftWriteChain;
  try{localStorage.removeItem(draftKey());const r=await window.pywebview.api.clear_editor_draft(editingFilename);if(r.error)throw new Error(r.error);}
  catch(e){showToast(uiText('内容已保存，但旧草稿未清除：','Saved, but old draft was not cleared: ')+e.message,'warning');}
}
function queueEditorDraft(){clearTimeout(draftTimer);draftTimer=setTimeout(retainEditorDraft,450);}
async function restoreEditorDraft(){
  let draft;try{const r=await window.pywebview.api.load_editor_draft(editingFilename);if(r.error)throw new Error(r.error);draft=r.draft||JSON.parse(localStorage.getItem(draftKey())||'null');}catch(e){showToast(e.message,'error');return;}
  if(!draft||JSON.stringify(draft.snapshot)===getEditorSnapshot())return;
  if(!await showCustomDialog({title:uiText('恢复未保存草稿？','Restore unsaved draft?'),message:new Date(draft.at).toLocaleString(),confirmText:uiText('恢复草稿','Restore draft')}))return;
  const v=draft.snapshot;const formChanged=JSON.stringify(v.openaiForm||{})!==JSON.stringify(editorOpenaiForm);editorSkillContent=v.skillContent;editorOpenaiYamlContent=v.openaiYaml;editorOpenaiForm=v.openaiForm||{};
  editorOpenaiFormDirty=editorOpenaiYamlSupported&&formChanged;editorOpenaiYamlDirty=editorOpenaiYamlSupported&&v.openaiYaml!==editorOpenaiYamlInitialContent;editorOpenaiYamlCreateRequested=editorOpenaiYamlSupported&&Boolean(v.createOpenaiYaml);
  editorVersion=draft.version;markdownTextarea.value=editorSkillContent;populateSkillCategoryOptions(v.category);populateOpenaiForm(editorOpenaiForm);updateEditorDirtyState();
}
async function resolveEditorConflict(result){
  retainEditorDraft();
  if(!openWorkspaceTool(uiText('文件已变化 · 草稿已保留','File changed · draft retained'),'conflict'))return;
  textBlock(uiText('磁盘版本','Disk version'));textBlock(result.current?.skill_content||uiText('文件已删除','File removed'));
  textBlock(uiText('你的草稿','Your draft'));textBlock(getEditorContentWithCategory());
  if(editorOpenaiYamlSupported){textBlock('agents/openai.yaml — '+uiText('磁盘 / 草稿','Disk / draft'));textBlock((result.current?.openai_yaml_content||'')+'\n────────\n'+editorOpenaiYamlContent);}
  if(result.diff)textBlock(result.diff);
  toolButton(uiText('复制草稿','Copy draft'),()=>copyAgentText(getEditorContentWithCategory()));
  toolButton(uiText('另存草稿','Export draft'),async()=>{const r=await window.pywebview.api.export_editor_draft(editingFilename,{skill_content:getEditorContentWithCategory(),openai_yaml_content:editorOpenaiYamlContent});if(r.error)throw new Error(r.error);toolFooter.textContent=uiText('草稿已另存至：','Draft exported to: ')+r.path;});
  toolButton(uiText('重新载入磁盘版本','Reload disk version'),async()=>{const name=editingFilename;closeWorkspaceTool();await openEditorModal(name);});
  toolButton(uiText('明确覆盖此版本','Overwrite this version'),async()=>{
    if(!result.current?.version){showToast(uiText('原文件已删除，请另存草稿','Original removed; save draft separately'),'warning');return;}
    if(!await showCustomDialog({title:uiText('用草稿覆盖所示磁盘版本？','Overwrite the displayed version?'),message:uiText('若文件再次变化，仍会拦截保存。','Further external changes will still block this save.'),emoji:'⚠️'}))return;
    editorVersion=result.current.version;closeWorkspaceTool();await handleSaveSkill();
  });
}

let inspectionQueue=[];
async function openInspectionQueue(items){
  if(!openWorkspaceTool(uiText('技能体检队列','Skill inspection queue'),'inspection'))return;
  inspectionQueue=items.map(i=>({...i,status:'pending',selected:false,preview:null,error:''}));
  toolButton(uiText('检查全部 / 重试失败','Inspect all / retry failed'),()=>inspectAll());
  toolButton(uiText('选择低风险项','Select low-risk'),()=>{inspectionQueue.forEach(i=>i.selected=Boolean(i.preview&&!i.preview.has_high_risk&&!i.preview.ai_used&&!i.preview.error));drawQueue();});
  toolButton(uiText('应用所选低风险项','Apply selected low-risk'),()=>applySelected());
  toolButton(uiText('保留所选原样','Keep selected unchanged'),()=>keepSelected());drawQueue();
}
function drawQueue(){
  toolBody.replaceChildren();
  for(const item of inspectionQueue){const row=document.createElement('div');row.className='tool-row';
    const check=document.createElement('input');check.type='checkbox';check.checked=item.selected;check.disabled=toolBusy||['done','skipped'].includes(item.status);check.onchange=()=>item.selected=check.checked;
    const title=document.createElement('span');title.textContent=item.filename;
    const status=document.createElement('small');status.textContent=item.error||({pending:uiText('待检查','Pending'),checking:uiText('检查中','Inspecting'),ready:uiText('待审阅','Review'),done:uiText('已完成','Completed'),skipped:uiText('已跳过','Skipped'),failed:uiText('失败，可重试','Failed; retry')}[item.status]||item.status);
    row.append(check,title,status);
    if(item.preview){toolButton(uiText('查看 / 审阅','Details / review'),()=>reviewQueueItem(item),row);}
    toolButton(uiText('跳过','Skip'),async()=>{if(toolBusy)return;item.status='skipped';item.selected=false;if(item.preview?.token)await window.pywebview.api.discard_skill_import(item.preview.token);drawQueue();},row);
    toolBody.append(row);
  }
  toolFooter.textContent=uiText('已完成 ','Completed ')+inspectionQueue.filter(i=>i.status==='done').length+' / '+inspectionQueue.length;
}
async function inspectAll(){if(toolBusy)return;toolBusy=true;
  try{for(const item of inspectionQueue.filter(i=>['pending','failed'].includes(i.status))){
    item.status='checking';drawQueue();try{item.preview=await window.pywebview.api.preview_unregistered_skill(item.filename);if(item.preview.error)throw new Error(item.preview.error);item.error='';item.status='ready';}catch(e){item.status='failed';item.error=e.message;}drawQueue();
  }}finally{toolBusy=false;drawQueue();}}
async function applyQueueItem(item,ai=false,risk=false){
  const r=await window.pywebview.api.apply_skill_import(item.preview.token,ai,risk);
  if(r.error)throw new Error(r.error);item.status='done';item.selected=false;item.preview=null;
}
async function applySelected(){if(toolBusy)return;
  const selected=inspectionQueue.filter(i=>i.selected&&i.status==='ready'&&!i.preview.has_high_risk&&!i.preview.ai_used);
  if(!selected.length)return;
  if(!await showCustomDialog({title:uiText('应用所选低风险项？','Apply selected low-risk items?'),message:selected.map(i=>i.filename).join('\n')}))return;
  toolBusy=true;try{for(const item of selected){try{await applyQueueItem(item);}catch(e){item.status='failed';item.error=e.message;}drawQueue();}}finally{toolBusy=false;drawQueue();await fetchSkills();}}
async function keepSelected(){if(toolBusy)return;toolBusy=true;try{for(const item of inspectionQueue.filter(i=>i.selected)){
    try{const r=await window.pywebview.api.acknowledge_unregistered_skill(item.filename);if(r?.error)throw new Error(r.error);if(item.preview?.token)await window.pywebview.api.discard_skill_import(item.preview.token);item.status='done';item.selected=false;}catch(e){item.status='failed';item.error=e.message;}
  }}finally{toolBusy=false;drawQueue();await fetchSkills();}}
async function reviewQueueItem(item){if(toolBusy||!item.preview)return;const preview=item.preview;
  const confirmed=await showCustomDialog({title:item.filename,message:formatImportPreview(preview),confirmText:uiText('应用','Apply')});if(!confirmed)return;
  let risk=false,ai=false;
  if(preview.has_high_risk){risk=Boolean(await showCustomDialog({title:uiText('确认高风险项','Confirm high-risk findings'),message:(preview.findings||[]).filter(f=>f.severity==='high').map(f=>currentLanguage==='zh'?f.message_zh:f.message_en).join('\n'),emoji:'⚠️'}));if(!risk)return;}
  if(preview.ai_used){ai=Boolean(await showCustomDialog({title:uiText('审阅 AI 改写','Review AI changes'),message:formatAiImportDiff(preview)}));if(!ai)return;}
  toolBusy=true;try{await applyQueueItem(item,ai,risk);}catch(e){item.status='failed';item.error=e.message;}finally{toolBusy=false;drawQueue();await fetchSkills();}
}

async function saveSyncResult(project,preview,result){
  const report={project,at:new Date().toISOString(),summary:result.summary||preview.summary,changes:preview.changes||[],error:result.error||''};
  try{localStorage.setItem('skillhub.lastSyncResult',JSON.stringify(report));}catch(_){}
  if(result.history_warning)showToast(result.history_warning,'warning');
  const stored=await window.pywebview.api.get_last_sync_result();
  await showSyncResult(stored.report?.transaction_id===result.transaction_id?stored.report:report);
}
async function showSyncResult(report){
  if(!report){const r=await window.pywebview.api.get_last_sync_result();if(r.error)throw new Error(r.error);report=r.report;}
  if(!openWorkspaceTool(uiText('最近同步结果','Latest sync result'),'sync'))return;
  if(!report){textBlock(uiText('暂无同步记录','No sync result yet'));return;}
  textBlock(report.project+'\n'+report.at);
  const labels={add:uiText('新增','Added'),adopt:uiText('纳管','Adopted'),modify:uiText('修改','Modified'),delete:uiText('移除','Removed'),preserve:uiText('保留','Preserved')};
  textBlock(Object.entries(report.summary||{}).map(([k,v])=>`${labels[k]||k}: ${v}`).join(' · '));
  if(report.error)textBlock(report.error);
  for(const change of report.changes)textBlock((change.action||'')+' · '+(change.path||'')+'\n'+(change.diff||change.reason||''));
}
async function clearAiCredential(){
  if(!await showCustomDialog({title:uiText('清除 API Key？','Clear API key?'),message:uiText('模型和接口地址保留。','Model and base URL are retained.')}))return;
  const r=await window.pywebview.api.save_ai_config('',deepseekModel,apiBase,true);if(r.error){showToast(r.error,'error');return;}
  hasAiKey=false;apiKeyHint='';document.getElementById('settings-apikey').value='';updateAIConfigurationIndicators();showToast(uiText('凭据已清除','Credential cleared'),'success');
}
function refreshWorkspaceSelectLabels(){
  const sort=document.getElementById('skill-sort');
  if(!sort)return;
  document.getElementById('skill-sort-label').textContent=uiText('排序','Sort');
  sort.setAttribute('aria-label',uiText('排列顺序','Sort order'));
  const orders={name:['名称升序','Name (A–Z)'],modified:['最新修改优先','Last modified (newest)']};
  for(const option of sort.options)option.textContent=uiText(...orders[option.value]);
  document.getElementById('skill-page-prev').setAttribute('aria-label',uiText('上一页','Previous page'));
  document.getElementById('skill-page-next').setAttribute('aria-label',uiText('下一页','Next page'));
}
function refreshWorkspaceLabels(){
  refreshWorkspaceSelectLabels();
  for(const root of [toolModal,document.querySelector('.workspace-filters'),aiSessionList.parentElement,agentResumeButton.parentElement,document.getElementById('settings-apikey').parentElement,editorModal.querySelector('.modal-header')]){
    root?.querySelectorAll('button').forEach(b=>{const pair=workspaceTranslations.get(b.textContent);if(pair)b.textContent=pair[currentLanguage==='zh'?0:1];});
  }
  const input=document.getElementById('session-search');if(input){input.placeholder=uiText('搜索会话','Search chats');input.setAttribute('aria-label',input.placeholder);}
}
function initWorkspaceTools(){
  const toolbar=document.createElement('div');toolbar.className='workspace-filters';
  const categoryRow=document.createElement('div');categoryRow.className='workspace-category-row';
  categoryFilterBar.before(categoryRow);categoryRow.append(categoryFilterBar,toolbar);
  const libraryActions=toolbar;
  const sortControl=document.createElement('label');sortControl.className='workspace-field workspace-sort';sortControl.htmlFor='skill-sort';
  sortControl.innerHTML='<span id="skill-sort-label"></span><select id="skill-sort" class="workspace-select"><option value="name"></option><option value="modified"></option></select>';
  document.querySelector('.toolbar-controls').append(sortControl);
  document.getElementById('skill-sort').onchange=renderSkillsGrid;
  const pages=document.createElement('span');pages.id='skill-pages';pages.hidden=true;document.querySelector('.skill-list-shell').after(pages);
  const previous=toolButton('‹',()=>{listPage--;renderSkillsGrid();},pages);previous.id='skill-page-prev';previous.setAttribute('aria-label','上一页 / Previous page');
  const pageNumber=document.createElement('span');pageNumber.id='skill-page-number';pages.append(pageNumber);
  const next=toolButton('›',()=>{listPage++;renderSkillsGrid();},pages);next.id='skill-page-next';next.setAttribute('aria-label','下一页 / Next page');
  toolButton(uiText('回收站','Trash'),openTrash,libraryActions);
  const search=document.createElement('input');search.id='session-search';search.type='search';search.placeholder=uiText('搜索会话','Search chats');search.setAttribute('aria-label',search.placeholder);search.oninput=renderSessionList;aiSessionList.before(search);
  const recover=toolButton(uiText('恢复历史备份','Restore history backup'),recoverChatHistory,aiSessionList.parentElement);recover.id='recover-chat-button';recover.hidden=true;
  const elapsed=document.createElement('span');elapsed.id='agent-elapsed';elapsed.setAttribute('role','status');agentResumeButton.after(elapsed);
  const stop=toolButton(uiText('停止','Stop'),stopAgentRun,agentResumeButton.parentElement);stop.id='agent-stop-button';stop.hidden=true;
  toolButton(uiText('清除凭据','Clear credential'),clearAiCredential,document.getElementById('settings-apikey').parentElement);
  editorModal.addEventListener('input',queueEditorDraft);editorModal.addEventListener('change',queueEditorDraft);
  document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'&&editingFilename){e.preventDefault();handleSaveSkill();}});
  window.addEventListener('beforeunload',retainEditorDraft);
  toolButton(uiText('比较已保存版本','Compare saved version'),async()=>{const r=await window.pywebview.api.get_skill_editor_data(editingFilename);if(r.error)throw new Error(r.error);await resolveEditorConflict({current:r});},editorModal.querySelector('.modal-header'));
}
initWorkspaceTools();
refreshWorkspaceLabels();
