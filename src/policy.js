import fs from 'node:fs';
import { createTwoFilesPatch } from 'diff';
export const baseline=JSON.parse(fs.readFileSync(new URL('../data/builtin-2.1.2.json',import.meta.url),'utf8'));
export const customIds=['orchestrator','cloud-reviewer'];
export const order=['orchestrator','build','plan','general','explore','scout','compaction','title','summary','cloud-reviewer'];
import {enhancement} from './prompts.js';
export {enhancement} from './prompts.js';
export function suggestedCategory(id){return ['general','explore','scout','title'].includes(id)?'local Qwen':'OpenAI';}
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
   put('description',id==='orchestrator'?'Cloud planning and review; delegates bounded execution to local workers.':'Difficult reasoning and read-only cloud review.');
   const allow=(action,resource='*')=>({action,resource,effect:'allow'});
   // Start custom roles with a deny-all policy, then expose only their needed tools.
   put('permissions',[deny('*'),...['read','glob','grep','list','lsp','question'].map(a=>allow(a)),
    ...(id==='orchestrator'?[...['general','explore'].map(a=>allow('subagent',a)),...['build','cloud-reviewer'].map(a=>allow('subagent',a))]:[]),
    ...['*.env','*.env.*'].map(resource=>({action:'read',resource,effect:'ask'})),
    {action:'read',resource:'*.env.example',effect:'allow'},deny('edit'),deny('shell')]);
  }
  if(id==='orchestrator'&&prompt==='enhance')put('steps',8);
  if(prompt==='restore')put('system',undefined);
  else if(prompt==='custom')put('system',choice.text);
  else if(prompt==='enhance'){
   const original=choice.baseSystem??baseline.find(a=>a.id===id)?.system??'';
   const addition=enhancement(id);
   if(addition)put('system',[original,addition].filter(Boolean).join('\n\n'));
  }else if(customIds.includes(id)&&!choice.existing)put('system',enhancement(id));
  if(id==='build'&&prompt==='enhance'){
   put('mode','all');
   put('permissions',[deny('subagent'),...['general','explore'].map(resource=>({action:'subagent',resource,effect:'allow'})),{action:'subagent',resource:'cloud-reviewer',effect:'allow'},{action:'subagent',resource:'orchestrator',effect:'deny'},{action:'subagent',resource:'build',effect:'deny'}]);
  }
  if(id==='general'&&prompt==='enhance'){put('permissions',[deny('subagent')]);put('steps',24);}
  if(id==='explore'&&prompt==='enhance')put('steps',12);
  if(id==='plan'&&prompt==='enhance')put('permissions',[deny('edit'),deny('shell'),deny('subagent'),{action:'subagent',resource:'explore',effect:'allow'}]);
 }
 return changes;
}
export function promptDiff(id,before,after){return createTwoFilesPatch(`${id}: current agent system`,`${id}: proposed agent system`,before||'',after||'');}
