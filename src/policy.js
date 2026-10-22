import fs from 'node:fs';
import { createTwoFilesPatch } from 'diff';
export const baseline=JSON.parse(fs.readFileSync(new URL('../data/builtin-2.1.2.json',import.meta.url),'utf8'));
export const customIds=['orchestrator','cloud-reviewer'];
export const order=['orchestrator','build','plan','general','explore','scout','compaction','title','summary','cloud-reviewer'];
const worker=`Work only within the assigned scope. Make the smallest correct change and follow project instructions. Run the assigned tests to terminal completion in this foreground assignment. Retain the exit status, test counts and artifact paths. Do not start detached test jobs, poll another worker, or call a build with zero tests a passing test run. Return a concise summary: changes, validation evidence, unresolved issues. If blocked, return the concrete blocker and evidence; do not repeatedly retry unchanged failures or delegate recursively.`;
const explore=`Search only as broadly as the assigned question requires. Return the answer, relevant file paths and line references, and remaining uncertainty. Avoid dumping files or lengthy search transcripts. Do not implement fixes.`;
const coordinator=`You are a coordination agent. Plan the work and delegate bounded exploration to Explore and scoped implementation or tests to General. Use cloud-reviewer, if configured, for difficult reasoning, ambiguous requirements, security-sensitive decisions or a concrete worker failure requiring deeper analysis. Give each worker its objective, owned paths, acceptance criteria and validation requirements. Start a fresh child session for each independent assignment. Use each agent's configured model; do not override it silently. Parallel writers must have disjoint file scopes. Review the diff and relevant evidence without repeating completed exploration. For test runs, dispatch one foreground subagent (background=false) and provide one final review; do not request intermediate monitoring turns or launch duplicate tests. Do not edit source files or execute shell commands directly. A worker's summary is a claim: verify the relevant artifacts, but do not redo its entire investigation. If the configured model is unavailable, report the blocker; do not silently switch to paid cloud inference.`;
const reviewer=`Review the assigned question or diff and worker evidence. Inspect the relevant artifacts and identify actionable correctness, design or security issues. Return findings with file references and a recommendation. Do not modify files, execute shell commands, delegate, or repeat the worker's entire investigation.`;
export function enhancement(id){
 if(id==='orchestrator')return coordinator;
 if(id==='cloud-reviewer')return reviewer;
 if(id==='general')return worker;
 if(id==='explore'||id==='scout')return explore;
 if(id==='build')return `Delegate bounded exploration to Explore and scoped implementation or test execution to General when doing so avoids duplicating context. Keep difficult implementation and final review here. Give workers clear ownership and acceptance criteria. Use foreground dispatch for tests; review final evidence once and do not poll. Do not silently override configured worker models.`;
 if(id==='plan')return `Delegate only read-only research to Explore or Scout if available. Do not delegate implementation or commands that change the workspace. Return a plan grounded in file references, acceptance criteria and unresolved risks.`;
 return '';
}
export function suggestedCategory(id){return ['general','explore','scout','title','summary'].includes(id)?'local Qwen':'OpenAI';}
export function selectModel(selection,models){
 const [base,variant,...rest]=selection.split('#');
 const m=models.find(m=>`${m.providerID}/${m.id}`===base&&m.enabled!==false);
 if(!m||rest.length)throw Error(`Model is not available: ${base}. Connect the provider first.`);
 if(variant&&!m.variants?.some(v=>(typeof v==='string'?v:v.id)===variant))throw Error(`Unsupported variant: ${variant}`);
 if(!base.includes('/')||selection.endsWith('#'))throw Error('Invalid model selection');
 return selection;
}
const deny=(action)=>({action,resource:'*',effect:'deny'});
export function buildOverrides(choices){
 const changes=[];
 for(const choice of choices){
  const {id,model,prompt='native'}=choice;
  if(!baseline.some(a=>a.id===id)&&!customIds.includes(id))throw Error(`Unsupported agent: ${id}`);
  const put=(key,value)=>changes.push({path:['agents',id,key],value});
  if(model===null)put('model',undefined);else if(model)put('model',model);
  if(customIds.includes(id)&&(!choice.existing||prompt==='enhance')){
   put('mode',id==='orchestrator'?'primary':'subagent');
   put('description',id==='orchestrator'?'Coordinates Qwen workers and reviews final evidence.':'Difficult reasoning and read-only cloud review.');
   const allow=(action,resource='*')=>({action,resource,effect:'allow'});
   // Start custom roles with a deny-all policy, then expose only their needed tools.
   put('permissions',[deny('*'),...['read','glob','grep','list','lsp','question'].map(a=>allow(a)),
    ...(id==='orchestrator'?['general','explore','cloud-reviewer'].map(a=>allow('subagent',a)):[]),
    ...['*.env','*.env.*'].map(resource=>({action:'read',resource,effect:'ask'})),
    {action:'read',resource:'*.env.example',effect:'allow'},deny('edit'),deny('shell')]);
  }
  if(prompt==='restore')put('system',undefined);
  else if(prompt==='custom')put('system',choice.text);
  else if(prompt==='enhance'){
   const original=choice.baseSystem??baseline.find(a=>a.id===id)?.system??'';
   const addition=enhancement(id);
   if(addition)put('system',[original,addition].filter(Boolean).join('\n\n'));
  }else if(customIds.includes(id)&&!choice.existing)put('system',enhancement(id));
  if(id==='general'&&prompt==='enhance'){put('permissions',[deny('subagent')]);put('steps',24);}
  if(id==='explore'&&prompt==='enhance')put('steps',12);
  if(id==='plan'&&prompt==='enhance')put('permissions',[deny('edit'),deny('shell'),deny('subagent'),{action:'subagent',resource:'explore',effect:'allow'}]);
 }
 return changes;
}
export function promptDiff(id,before,after){return createTwoFilesPatch(`${id}: current agent system`,`${id}: proposed agent system`,before||'',after||'');}
