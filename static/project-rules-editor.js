// User-controlled project rules editor. AI is draft-only and always opt-in.
let rulesEditorState=null;
let rulesDraftTimer=null;
let rulesDraftWrites=Promise.resolve();
const rulesEditor=document.createElement('div');
rulesEditor.id='project-rules-editor';rulesEditor.className='modal-overlay';rulesEditor.inert=true;
rulesEditor.setAttribute('role','dialog');rulesEditor.setAttribute('aria-modal','true');rulesEditor.setAttribute('aria-hidden','true');rulesEditor.setAttribute('aria-labelledby','rules-editor-title');
rulesEditor.innerHTML='<section class="modal-container rules-editor-container"><header class="modal-header"><div><h3 id="rules-editor-title">AGENTS.md</h3><small id="rules-editor-path"></small></div><button type="button" class="btn btn-secondary" id="rules-editor-close">×</button></header><div class="rules-editor-note" id="rules-editor-note"></div><div class="rules-editor-toolbar"><button type="button" class="btn btn-secondary" id="rules-edit-tab"></button><button type="button" class="btn btn-secondary" id="rules-preview-tab"></button><button type="button" class="btn btn-secondary" id="rules-ai-authorize"></button></div><div class="rules-editor-body"><textarea id="rules-editor-text" spellcheck="false" aria-label="AGENTS.md"></textarea><div id="rules-editor-preview" class="markdown-preview" hidden></div><pre id="rules-editor-comparison" hidden></pre></div><footer class="rules-editor-footer"><span id="rules-editor-status" role="status"></span><button type="button" class="btn btn-secondary" id="rules-reload" hidden></button><button type="button" class="btn btn-secondary" id="rules-use-ai" hidden></button><button type="button" class="btn btn-primary" id="rules-editor-save"></button></footer></section>';
document.body.append(rulesEditor);
const rulesText=document.getElementById('rules-editor-text'),rulesPreview=document.getElementById('rules-editor-preview'),rulesStatus=document.getElementById('rules-editor-status'),rulesCompare=document.getElementById('rules-editor-comparison');
const rulesSave=document.getElementById('rules-editor-save'),rulesAi=document.getElementById('rules-ai-authorize'),rulesReload=document.getElementById('rules-reload'),rulesUseAi=document.getElementById('rules-use-ai');
function rulesDraftKey(state){return '@project-rules:'+state.project;}
function setRulesBusy(state,busy){if(state!==rulesEditorState)return;state.busy=busy;rulesSave.disabled=busy;rulesAi.disabled=busy;rulesText.disabled=busy;}
function queueRulesDraft(){clearTimeout(rulesDraftTimer);rulesDraftTimer=setTimeout(()=>persistRulesDraft(),450);rulesStatus.textContent=uiText('未保存','Unsaved');}
function persistRulesDraft(){
  const state=rulesEditorState;if(!state?.ready||rulesText.value===state.original)return Promise.resolve(true);
  const draft={snapshot:{skillContent:rulesText.value,openaiYaml:'',category:'',openaiForm:{}},version:state.version,at:Date.now()};
  rulesDraftWrites=rulesDraftWrites.then(async()=>{try{const r=await window.pywebview.api.save_editor_draft(rulesDraftKey(state),draft);if(r.error)throw new Error(r.error);return true;}catch(e){rulesStatus.textContent=e.message;return false;}});
  return rulesDraftWrites;
}
async function openProjectRulesEditor(project){
  if(rulesEditorState&&!await closeProjectRulesEditor())return;
  const state={project,version:null,original:'',ready:false,busy:true,proposal:null};rulesEditorState=state;
  document.getElementById('rules-editor-title').textContent=uiText('编辑项目开发规约 · AGENTS.md','Edit project rules · AGENTS.md');
  document.getElementById('rules-editor-path').textContent=project;
  document.getElementById('rules-editor-note').textContent=uiText('此文件仅由你手动保存；AI 自动优化不会修改它。授权 AI 起草后仍需审阅并手动保存。固定规约请写在 SkillHub 自动维护区块之外。','Only your manual Save writes this file. Automatic AI optimization is disabled. Authorized AI produces drafts for review and manual saving. Keep fixed rules outside the SkillHub-managed section.');
  document.getElementById('rules-edit-tab').textContent=uiText('编辑','Edit');document.getElementById('rules-preview-tab').textContent=uiText('预览','Preview');
  document.getElementById('rules-editor-close').setAttribute('aria-label',uiText('关闭规约编辑器','Close rules editor'));
  rulesSave.textContent=uiText('保存规约','Save rules');rulesAi.textContent=uiText('授权 AI 起草','Authorize AI draft');rulesReload.textContent=uiText('重新载入磁盘版本','Reload disk version');rulesUseAi.textContent=uiText('使用 AI 草稿（未保存）','Use AI draft (unsaved)');
  rulesCompare.hidden=true;rulesReload.hidden=true;rulesUseAi.hidden=true;rulesPreview.hidden=true;rulesText.hidden=false;rulesText.value='';rulesStatus.textContent=uiText('加载中…','Loading…');setRulesBusy(state,true);activateModal(rulesEditor,rulesText);
  try{
    const r=await window.pywebview.api.get_project_rules_editor_data(project);if(state!==rulesEditorState)return;if(r.error)throw new Error(r.error);
    state.project=r.project_path;state.version=r.version;state.original=r.content;state.ready=true;rulesText.value=r.content;state.original=rulesText.value;
    rulesStatus.textContent=r.exists?uiText('手动编辑','Manual editing'):uiText('尚未创建，保存后创建','Not created; Save creates the file');
    const saved=await window.pywebview.api.load_editor_draft(rulesDraftKey(state));
    if(state!==rulesEditorState)return;
    if(saved.draft&&saved.draft.snapshot.skillContent!==state.original&&await showCustomDialog({title:uiText('恢复项目规约草稿？','Restore project rules draft?'),message:uiText('原文件保持不变，保存前会检查版本冲突。','The original stays unchanged; saving checks for version conflicts.')})){
      if(state!==rulesEditorState)return;rulesText.value=saved.draft.snapshot.skillContent;state.version=saved.draft.version;rulesStatus.textContent=uiText('草稿已恢复，尚未保存','Draft restored; not saved');
    }
  }catch(e){rulesStatus.textContent=e.message;}finally{if(state===rulesEditorState){setRulesBusy(state,false);rulesSave.disabled=!state.ready;rulesAi.disabled=!state.ready;rulesText.focus();}}
}
async function closeProjectRulesEditor(){
  const state=rulesEditorState;if(!state)return true;
  if(state.busy){showToast(uiText('请等待当前操作完成','Wait for the current operation'),'info');return false;}
  if(state.ready&&rulesText.value!==state.original){
    if(!await showCustomDialog({title:uiText('保留草稿并关闭？','Keep draft and close?'),message:uiText('修改尚未保存到 AGENTS.md，下次打开可恢复草稿。','Changes are not saved to AGENTS.md. The draft can be restored next time.'),confirmText:uiText('保留草稿并关闭','Keep draft and close')}))return false;
    if(!await persistRulesDraft())return false;
  }
  clearTimeout(rulesDraftTimer);deactivateModal(rulesEditor);rulesEditorState=null;return true;
}
async function saveProjectRulesFromEditor(){
  const state=rulesEditorState;if(!state?.ready||state.busy)return;
  setRulesBusy(state,true);clearTimeout(rulesDraftTimer);
  try{
    await rulesDraftWrites;
    const r=await window.pywebview.api.save_project_rules(state.project,rulesText.value,state.version);
    if(r.conflict){state.conflict=r.current;rulesReload.hidden=false;rulesCompare.hidden=false;rulesCompare.textContent=uiText('磁盘当前版本：\n','Current disk version:\n')+r.current.content;}
    if(r.error)throw new Error(r.error);
    state.version=r.version;state.original=r.content;state.proposal=null;rulesUseAi.hidden=true;rulesCompare.hidden=true;rulesReload.hidden=true;
    const clear=await window.pywebview.api.clear_editor_draft(rulesDraftKey(state));
    rulesStatus.textContent=clear.error?uiText('文件已保存，旧草稿未能清除','Saved; old draft could not be cleared'):uiText('已保存','Saved');
    await fetchProjects();if(currentProjectPath===state.project)refreshCurrentProject();
  }catch(e){rulesStatus.textContent=e.message;}finally{setRulesBusy(state,false);}
}
async function authorizeRulesAiDraft(){
  const state=rulesEditorState;if(!state?.ready||state.busy)return;
  const instruction=await showCustomDialog({title:uiText('本次希望 AI 修改什么？','What should AI change this time?'),message:uiText('请输入具体要求，不会自动保存到文件。','Enter a specific instruction. No file is saved automatically.'),isPrompt:true,confirmText:uiText('下一步','Next')});
  if(typeof instruction!=='string'||!instruction.trim()||state!==rulesEditorState)return;
  if(!await showCustomDialog({title:uiText('授权本次 AI 起草？','Authorize this AI drafting request?'),message:uiText('将把编辑区全文和本次要求发送给已配置的 AI 服务。AI 仅返回草稿，你审阅并点击保存后才会修改 AGENTS.md。','The editor text and instruction will be sent to your configured AI service. AI only returns a draft; AGENTS.md changes only after you review and Save.'),confirmText:uiText('授权本次请求','Authorize this request')}))return;
  if(state!==rulesEditorState)return;
  await persistRulesDraft();setRulesBusy(state,true);rulesStatus.textContent=uiText('AI 正在起草，不会写入文件…','AI is drafting; no file will be written…');
  try{
    const grant=await window.pywebview.api.authorize_project_rules_ai(state.project,rulesText.value,instruction,state.version);if(grant.error)throw new Error(grant.error);
    const r=await window.pywebview.api.draft_project_rules_ai(grant.token);if(r.error)throw new Error(r.error);
    state.proposal=r.content;rulesCompare.textContent=r.diff||uiText('内容没有变化','No changes');rulesCompare.hidden=false;rulesText.hidden=true;rulesPreview.hidden=true;rulesUseAi.hidden=false;rulesStatus.textContent=uiText('AI 草稿待审阅，文件未修改','Review the AI draft; file unchanged');
  }catch(e){rulesStatus.textContent=e.message;}finally{setRulesBusy(state,false);}
}
rulesText.addEventListener('input',queueRulesDraft);
document.getElementById('rules-editor-close').onclick=closeProjectRulesEditor;
rulesSave.onclick=saveProjectRulesFromEditor;rulesAi.onclick=authorizeRulesAiDraft;
rulesUseAi.onclick=()=>{if(rulesEditorState?.proposal&&!rulesEditorState.busy){rulesText.value=rulesEditorState.proposal;rulesUseAi.hidden=true;rulesText.hidden=false;rulesPreview.hidden=true;rulesCompare.hidden=true;queueRulesDraft();}};
rulesReload.onclick=async()=>{const state=rulesEditorState;if(!state||state.busy)return;if(!await showCustomDialog({title:uiText('重新载入并替换编辑区？','Reload and replace editor text?'),message:uiText('未保存内容先保留为草稿。','Unsaved text is preserved as a draft first.')}))return;if(!await persistRulesDraft())return;const r=await window.pywebview.api.get_project_rules_editor_data(state.project);if(r.error){rulesStatus.textContent=r.error;return;}state.original=r.content;state.version=r.version;rulesText.value=r.content;state.original=rulesText.value;rulesCompare.hidden=true;rulesReload.hidden=true;rulesStatus.textContent=uiText('已重新载入','Reloaded');};
document.getElementById('rules-edit-tab').onclick=()=>{rulesText.hidden=false;rulesPreview.hidden=true;rulesCompare.hidden=true;};
document.getElementById('rules-preview-tab').onclick=()=>{rulesPreview.innerHTML=renderMarkdown(rulesText.value);rulesPreview.hidden=false;rulesText.hidden=true;rulesCompare.hidden=true;};
document.addEventListener('keydown',e=>{if((e.ctrlKey||e.metaKey)&&e.key.toLowerCase()==='s'&&rulesEditorState){e.preventDefault();if(!document.getElementById('dialog-modal').classList.contains('active'))saveProjectRulesFromEditor();}});
window.addEventListener('beforeunload',()=>{if(rulesEditorState)persistRulesDraft();});
