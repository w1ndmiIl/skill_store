const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../static/workspace-tools.js'),'utf8');
function extract(name){const pattern=new RegExp('^(?:async )?function '+name+'\\(', 'm');const start=pattern.exec(source).index;const next=/\n(?:async )?function \w+\(/.exec(source.slice(start+1));return source.slice(start,next?start+1+next.index:undefined);}
function setup(choices=[]){const calls=[];const c=vm.createContext({toolBusy:false,inspectionQueue:[],currentLanguage:'zh',
 uiText:(a,b)=>a,showCustomDialog:async()=>choices.shift(),drawQueue:()=>{},fetchSkills:async()=>{},formatImportPreview:()=>'',formatAiImportDiff:()=>'',
 window:{pywebview:{api:{apply_skill_import:async(...args)=>{calls.push(args);return{ok:true};}}}}});
 for(const name of ['applyQueueItem','applySelected','reviewQueueItem'])vm.runInContext(extract(name),c);return{c,calls};}
test('high-risk items cannot enter the bulk apply path',async()=>{const {c,calls}=setup([true]);c.inspectionQueue=[
 {filename:'safe',status:'ready',selected:true,preview:{token:'safe'}},
 {filename:'risk',status:'ready',selected:true,preview:{token:'risk',has_high_risk:true}},
 {filename:'ai',status:'ready',selected:true,preview:{token:'ai',ai_used:true}}];await c.applySelected();assert.deepEqual(calls,[['safe',false,false]]);});
test('declining separate high-risk confirmation prevents application',async()=>{const {c,calls}=setup([true,false]);await c.reviewQueueItem({filename:'risk',preview:{token:'r',has_high_risk:true,findings:[]}});assert.equal(calls.length,0);});
test('AI and high-risk decisions are forwarded independently',async()=>{const {c,calls}=setup([true,true,true]);await c.reviewQueueItem({filename:'both',preview:{token:'both',ai_used:true,has_high_risk:true,findings:[]}});assert.deepEqual(calls,[['both',true,true]]);});
test('failed item remains retryable while other bulk items complete',async()=>{const {c}=setup([true]);c.window.pywebview.api.apply_skill_import=async token=>token==='bad'?{error:'disk full'}:{ok:true};c.inspectionQueue=['bad','good'].map(token=>({filename:token,status:'ready',selected:true,preview:{token}}));await c.applySelected();assert.equal(c.inspectionQueue[0].status,'failed');assert.equal(c.inspectionQueue[1].status,'done');});
test('skipping an item acknowledges its inspected version before marking it skipped',async()=>{
 const calls=[];const c=vm.createContext({toolBusy:false,drawQueue:()=>{},fetchSkills:async()=>{},window:{pywebview:{api:{
  acknowledge_unregistered_skill:async(...args)=>{calls.push(['ack',...args]);return{ok:true};},
  discard_skill_import:async token=>{calls.push(['discard',token]);return{ok:true};}
 }}}});
 for(const name of ['acknowledgeQueueItem','skipQueueItem'])vm.runInContext(extract(name),c);
 const item={filename:'lab1031-server.md',hash:'inspected-hash',status:'pending',selected:true,preview:{token:'preview'}};
 await c.skipQueueItem(item);
 assert.deepEqual(calls,[['ack','lab1031-server.md','inspected-hash'],['discard','preview']]);
 assert.equal(item.status,'skipped');assert.equal(item.selected,false);assert.equal(item.preview,null);
});
test('failed skip remains visible and retryable',async()=>{
 const c=vm.createContext({toolBusy:false,drawQueue:()=>{},fetchSkills:async()=>{},window:{pywebview:{api:{
  acknowledge_unregistered_skill:async()=>({error:'skill changed'})
 }}}});
 for(const name of ['acknowledgeQueueItem','skipQueueItem'])vm.runInContext(extract(name),c);
 const item={filename:'lab1031-server.md',hash:'old-hash',status:'pending',selected:true};
 await c.skipQueueItem(item);
 assert.equal(item.status,'failed');assert.equal(item.error,'skill changed');
});
test('inspection queue renders a completed skip without another skip button',()=>{
 const body={children:[],replaceChildren(){this.children=[];},append(item){this.children.push(item);}};
 const footer={textContent:''};
 const c=vm.createContext({toolBusy:false,inspectionQueue:[{filename:'lab1031-server.md',status:'skipped',selected:false}],
  toolBody:body,toolFooter:footer,uiText:a=>a,
  document:{createElement:tag=>({tag,children:[],append(...items){this.children.push(...items);}})},
  toolButton:(label,action,parent)=>{parent.append({tag:'button',label,action});}
 });
 vm.runInContext(extract('drawQueue'),c);c.drawQueue();
 assert.equal(footer.textContent,'已完成 1 / 1');
 assert.equal(body.children[0].children.some(child=>child.tag==='button'&&child.label==='跳过'),false);
});
test('keeping selected items acknowledges their scanned hashes',async()=>{
 const calls=[];const c=vm.createContext({toolBusy:false,inspectionQueue:[],drawQueue:()=>{},fetchSkills:async()=>{},window:{pywebview:{api:{
  acknowledge_unregistered_skill:async(...args)=>{calls.push(args);return{ok:true};}
 }}}});
 for(const name of ['acknowledgeQueueItem','keepSelected'])vm.runInContext(extract(name),c);
 const item={filename:'sample.md',hash:'visible-hash',status:'pending',selected:true};c.inspectionQueue=[item];
 await c.keepSelected();
 assert.deepEqual(calls,[['sample.md','visible-hash']]);assert.equal(item.status,'done');
});
test('sorting retains all skills regardless of deployment status',()=>{const elements={'skill-state-filter':{value:'unpublished'},'skill-sort':{value:'name'}};
 const c=vm.createContext({listPreferenceKey:'library',listPreferences:new Map(),currentProjectPath:null,currentLanguage:'zh',searchInput:{value:''},activeCategoryFilter:null,document:{getElementById:id=>elements[id]}});vm.runInContext(extract('workspaceFilterSkills'),c);
 const filtered=c.workspaceFilterSkills([{filename:'new',title:'new'},{filename:'old',title:'old',codex_global_status:'outdated',global_target_states:[{enabled:true,status:'outdated'}]}]);assert.equal(filtered.length,2);assert.equal(filtered[0].filename,'new');});
test('pagination bounds DOM work and exposes the remaining rows',()=>{const e={};for(const id of ['skill-state-filter','skill-sort','skill-page-prev','skill-page-next','skill-page-number','skill-pages'])e[id]={value:''};const c=vm.createContext({listPage:0,listPageSignature:'',currentProjectPath:null,searchInput:{value:''},activeCategoryFilter:null,document:{getElementById:id=>e[id]}});vm.runInContext(extract('paginateSkillRows'),c);
 const rows=Array.from({length:2000},(_,i)=>i);assert.equal(c.paginateSkillRows(rows).length,100);c.listPage=1;assert.equal(c.paginateSkillRows(rows)[0],100);assert.equal(e['skill-page-number'].textContent,'2 / 20');});
test('session module loads before app bindings and all shipped scripts exist',()=>{const root=path.join(__dirname,'../static');const html=fs.readFileSync(path.join(root,'index.html'),'utf8');assert.ok(html.indexOf('src="session-controller.js"')<html.indexOf('src="app.js'));
 for(const match of html.matchAll(/<script src="([^"?]+)[^"]*"/g)){assert.ok(fs.existsSync(path.join(root,match[1])),match[1]);}});

test('restoring a single Markdown draft never enables unsupported metadata writes',async()=>{
 const draft={snapshot:{skillContent:'draft',openaiYaml:'',openaiForm:{},category:'',createOpenaiYaml:false},version:{},at:1};
 const c=vm.createContext({editingFilename:'demo.md',window:{pywebview:{api:{load_editor_draft:async()=>({draft})}}},localStorage:{getItem:()=>null},getEditorSnapshot:()=>JSON.stringify({skillContent:'original'}),showCustomDialog:async()=>true,uiText:a=>a,editorOpenaiForm:{},editorOpenaiYamlSupported:false,editorOpenaiYamlInitialContent:'',markdownTextarea:{},populateSkillCategoryOptions:()=>{},populateOpenaiForm:()=>{},updateEditorDirtyState:()=>{},showToast:()=>{}});
 vm.runInContext(extract('restoreEditorDraft'),c);await c.restoreEditorDraft();assert.equal(c.editorOpenaiYamlDirty,false);assert.equal(c.editorOpenaiFormDirty,false);assert.equal(c.editorOpenaiYamlCreateRequested,false);assert.equal(c.markdownTextarea.value,'draft');
});
test('a skill-body-only draft does not create untouched package metadata',async()=>{
 const draft={snapshot:{skillContent:'draft',openaiYaml:'interface: {}',openaiForm:{},category:'',createOpenaiYaml:false},version:{},at:1};
 const c=vm.createContext({editingFilename:'demo',window:{pywebview:{api:{load_editor_draft:async()=>({draft})}}},localStorage:{getItem:()=>null},getEditorSnapshot:()=>JSON.stringify({skillContent:'original'}),showCustomDialog:async()=>true,uiText:a=>a,editorOpenaiForm:{},editorOpenaiYamlSupported:true,editorOpenaiYamlInitialContent:'interface: {}',markdownTextarea:{},populateSkillCategoryOptions:()=>{},populateOpenaiForm:()=>{},updateEditorDirtyState:()=>{},showToast:()=>{}});
 vm.runInContext(extract('restoreEditorDraft'),c);await c.restoreEditorDraft();assert.equal(c.editorOpenaiYamlDirty,false);assert.equal(c.editorOpenaiFormDirty,false);assert.equal(c.editorOpenaiYamlCreateRequested,false);
});
