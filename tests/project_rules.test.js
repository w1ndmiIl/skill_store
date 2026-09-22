const test=require('node:test');const assert=require('node:assert/strict');const fs=require('node:fs');const path=require('node:path');const vm=require('node:vm');
const source=fs.readFileSync(path.join(__dirname,'../static/app.js'),'utf8');
function extract(name){const start=source.indexOf('function '+name+'(');assert.ok(start>=0);const end=source.indexOf('\n}',start)+2;return source.slice(start,end);}
function element(){return{dataset:{},children:[],setAttribute(){},appendChild(child){this.children.push(...(child.fragment?child.children:[child]));},querySelectorAll(){return[];},querySelector(){return null;}};}
function harness(){
 const rules={filename:'@project-rules:AGENTS.md',title:'AGENTS.md',description:'当前项目的固定开发规约',project_rules:true,project_only:true,available:true};
 const c=vm.createContext({Map,Set,currentProjectPath:'A',currentLanguage:'zh',skills:[{filename:'normal.md',title:'Normal',description:'match',tags:[],category:'Work'}],projects:[{path:'A',project_rules:rules,project_skills:[]}],displaySkillsByFilename:new Map(),globalSkillTargetOptions:[],
 searchInput:{value:''},navSkillCount:{},activeCategoryFilter:null,workspaceFilterSkills:rows=>rows.slice().reverse(),paginateSkillRows:rows=>rows,
 document:{createElement:element,createDocumentFragment:()=>({...element(),fragment:true})},cardsGrid:element(),lucide:{createIcons(){}},
 getCanonicalCategory:s=>s.category,getLocalizedCategory:c=>c,getSmartEmojiAndTags:()=>({emoji:'📌',tags:[]}),getSkillListIcon:()=> 'pin',
 getProjectRowContext:()=>({activeProj:{},statusMap:{},managedSkills:new Set(),detachedSkills:new Set()}),
 getSkillRowState:()=>({statusHTML:'',isChecked:false,isPartiallyChecked:false}),tagTranslations:{zh:{}},escapeHtml:s=>String(s??''),locales:{zh:{btnEditSkill:'Edit'}}});
 vm.runInContext(extract('buildDisplaySkills'),c);vm.runInContext(extract('renderSkillsGrid'),c);return c;
}
test('project rules are first in the project and absent from the global library',()=>{const c=harness();assert.equal(c.buildDisplaySkills()[0].project_rules,true);assert.equal(c.skills.length,1);c.currentProjectPath=null;assert.equal(c.buildDisplaySkills().length,1);assert.equal(c.buildDisplaySkills()[0].filename,'normal.md');});
test('fixed rules remain first after sorting and never expose enable or delete controls',()=>{const c=harness();c.renderSkillsGrid();const row=c.cardsGrid.children[0];assert.equal(row.dataset.filename,'@project-rules:AGENTS.md');assert.ok(row.innerHTML.includes('当前项目的固定开发规约'));assert.ok(!row.innerHTML.includes('js-toggle-skill'));assert.ok(!row.innerHTML.includes('js-delete-skill'));assert.equal(c.navSkillCount.textContent,1);});
test('fixed rules stay visible with a nonmatching search and on later pages',()=>{const c=harness();c.searchInput.value='unmatched';c.paginateSkillRows=()=>[];c.renderSkillsGrid();assert.equal(c.cardsGrid.children.length,1);assert.equal(c.cardsGrid.children[0].dataset.filename,'@project-rules:AGENTS.md');});
