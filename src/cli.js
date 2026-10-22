import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { spawnSync } from 'node:child_process';
import { select, search, input, editor, confirm } from '@inquirer/prompts';
import { createTwoFilesPatch } from 'diff';
import { baseline,customIds,order,enhancement,buildOverrides,promptDiff,suggestedCategory,selectModel } from './policy.js';
import { readTarget,parseConfig,preview,apply,undo,undoPreview,resetChanges,redact,redactText } from './store.js';
import {privateCredential,writeCredential} from './credentials.js';
import { discover,validateNative,overrideWarnings,localModels,proposedLocalProvider,validateLocalEndpoint,executable } from './native.js';
import { openDatabase,loadTree,findRoot,listRoots,analyze,render,renderComparison } from './usage.js';
const help=`Native OpenCode agent setup (supported: 2.1.2). No ports are changed.

opencode-agent-setup                         Interactive wizard
opencode-agent-setup inspect                 Agent roles, models and config sources
opencode-agent-setup preview --choices FILE   Offline exact diff; no writes/inference
opencode-agent-setup apply --choices FILE     Validate model choices, preview and confirm
opencode-agent-setup undo                    Undo last tool transaction
opencode-agent-setup reset                   Remove agent overrides in selected JSON scope
opencode-agent-setup usage                   Token/model/agent report for the last session here
opencode-agent-setup plugin install|status|uninstall [--project]   Live /usage TUI panel + end-of-session report

Options: --config PATH (opencode.json or opencode.jsonc), --dry-run, --yes
Usage report: --session ID | --directory DIR (default: current directory) | --list,
  --compare ID, --json, --pricing FILE (per-million rates), --db PATH. Reads OpenCode's
  own session database read-only; no inference, no writes, no running service needed.
Choices JSON: [{"id":"general","model":"omlx/ACTUAL-ID","prompt":"enhance"}]
Prompt modes: native (keep), enhance, restore (remove system override), custom (+ text).
model:null removes the agent model override; omitted model leaves it unchanged.
--yes authorizes a reviewed apply/reset/undo without terminal confirmation.
Reset preserves providers, credentials and unrelated settings. Agent Markdown files and
higher-priority config require separate review and are never silently deleted.
`;
function argsOf(argv){
 const opts={command:'wizard'};const commands=['wizard','inspect','preview','apply','undo','reset','usage','plugin'];
 for(let i=0;i<argv.length;i++){
  const a=argv[i];if(commands.includes(a)&&i===0)opts.command=a;
  else if(['--config','--choices','--session','--directory','--db','--compare','--pricing','--limit'].includes(a)){if(!argv[i+1]||argv[i+1].startsWith('--'))throw Error(`Missing ${a} value`);opts[a.slice(2)]=argv[++i];}
  else if(['--help','--dry-run','--yes','--json','--list','--project'].includes(a))opts[a.slice(2)]=true;
  else if(opts.command==='plugin'&&['install','uninstall','status'].includes(a)&&!opts.action)opts.action=a;
  else throw Error(`Unknown argument: ${a}`);
 }return opts;
}
function targetPath(explicit){
 if(explicit){const p=path.resolve(explicit);if(!['opencode.json','opencode.jsonc'].includes(path.basename(p)))throw Error('Configuration filename must be opencode.json or opencode.jsonc');return p;}
 const root=path.join(process.env.XDG_CONFIG_HOME??path.join(os.homedir(),'.config'),'opencode');
 const json=path.join(root,'opencode.json'),jsonc=path.join(root,'opencode.jsonc');
 if(fs.existsSync(json)&&fs.existsSync(jsonc))throw Error('Both config formats exist; select an explicit --config path.');
 return fs.existsSync(jsonc)?jsonc:json;
}
async function approved(message,opts){if(opts['dry-run'])return false;if(opts.yes)return true;if(!process.stdin.isTTY)throw Error('Use a terminal for confirmation, or explicitly pass --yes after reviewing preview.');return confirm({message,default:false});}
function show(file,changes,currentAgents=baseline){
 const p=preview(file,changes);console.log(createTwoFilesPatch(file,file,redactText(p.before??''),redactText(p.after)));
 for(const c of changes.filter(c=>c.path[0]==='agents'&&c.path.at(-1)==='system')){
  const id=c.path[1],before=currentAgents.find(a=>a.id===id)?.system??'';
  const after=c.value??baseline.find(a=>a.id===id)?.system??'';
  console.log(promptDiff(id,before,after));
 }
 console.log('Preview only. Agent-specific system text is shown; dynamic harness reminders remain separate.');
 return p;
}
async function chooseModel(id,models){
 const category=suggestedCategory(id);
 const suggested=models.filter(m=>m.capabilities?.tools!==false).filter(m=>category==='local Qwen'?/qwen/i.test(m.id)&&/omlx|local|mlx/i.test(m.providerID):m.providerID==='openai'||m.providerID==='chatgpt');
 console.log(`Suggested policy: ${category}${['build','plan','cloud-reviewer'].includes(id)?', high effort for difficult work':', medium effort where supported'}. No automatic fallback.`);
 const action=await select({message:`${id}: model`,choices:[{name:'Keep current/native selection',value:'keep'},...(suggested.length?[{name:`Choose suggested ${category} models`,value:'suggested'}]:[]),{name:'Choose any available model',value:'all'},{name:'Remove model override (inherit)',value:'inherit'},{name:'Back to previous agent',value:'back'}]});
 if(action==='keep'||action==='back')return action;if(action==='inherit')return null;
 const choices=action==='suggested'?suggested:models;
 if(!choices.length)throw Error('No available models. Connect OpenAI or configure the local provider first.');
 const base=await search({message:'Select model (type to filter)',source:async(term='')=>choices.filter(m=>`${m.providerID}/${m.id} ${m.name}`.toLowerCase().includes(term.toLowerCase())).map(m=>({name:`${m.providerID}/${m.id}`,value:`${m.providerID}/${m.id}`}))});
 const model=choices.find(m=>`${m.providerID}/${m.id}`===base);
 const variant=await select({message:'Reasoning effort / variant',choices:[{name:'Model default',value:''},...(model.variants??[]).map(v=>({name:v.id,value:v.id}))]});
 return selectModel(base+(variant?'#'+variant:''),models);
}
async function wizard(opts,file,info){
 let localChanges=[],models=info.models,pendingCredential;
 console.log('Orchestrator is an optional CUSTOM primary agent. Build/Plan are native primary agents; General/Explore are native workers.');
 console.log('Native worker model choices are defaults; explicit session/UI selections can override them.');
 const profile=await select({message:'Orchestration profile',choices:[{name:'Add optional Orchestrator (coordinate/review, no direct edits)',value:'coordinator'},{name:'Keep native Build/Plan roles only',value:'native'}]});
 const reviewer=await confirm({message:'Add optional cloud-reviewer subagent for difficult reasoning?',default:profile==='coordinator'});
 while(true){
 const providerAction=await select({message:'Model providers',choices:[{name:'Continue with available/configured models',value:'current'},{name:'Connect OpenAI through native login, then refresh',value:'login'},{name:'Configure existing local oMLX endpoint, then discover Qwen',value:'local'}]});
 if(providerAction==='current')break;
 if(providerAction==='login'){
  const login=spawnSync(executable,['auth','login'],{stdio:'inherit'});if(login.status!==0)throw Error('Provider login did not complete.');models=[...(await discover()).models,...models.filter(m=>m.providerID==='omlx'&&localChanges.length)];
 }
 if(providerAction==='local'){
  const endpoint=await input({message:'Existing local API URL (port is preserved)',default:'http://127.0.0.1:8000/v1'});
  validateLocalEndpoint(endpoint);
  const source=await select({message:'Local API key source (never shown)',choices:[
   {name:'Reuse the key in existing oMLX settings',value:'settings'},
   {name:'Read from an environment variable',value:'env'},
   {name:'Read an existing private key file',value:'file'}]});
  let key;
  if(source==='settings')key=JSON.parse(fs.readFileSync(path.join(os.homedir(),'.omlx/settings.json'),'utf8')).auth?.api_key;
  else if(source==='env'){
   const env=await input({message:'Environment variable name',default:'OMLX_API_KEY'});key=process.env[env];
  }else{
   const keyPath=await input({message:'Absolute path to private API-key file'});
   if(!path.isAbsolute(keyPath))throw Error('Key file path must be absolute');key=readTarget(keyPath)?.trim();
  }
  pendingCredential=privateCredential(key);
  const available=await localModels(endpoint,key);
  const id=await select({message:'Choose the actual local Qwen model',choices:available.map(m=>({name:m.id,value:m.id}))});
  localChanges=proposedLocalProvider(endpoint,id,'OMLX_API_KEY')
  localChanges[0].value.settings.apiKey=`{file:${pendingCredential.file}}`;
  if(readTarget(file)&&parseConfig(readTarget(file)).providers?.omlx)throw Error('Existing omlx provider found. Edit it explicitly before using local setup; this wizard will not replace it silently.');
  console.log('Local model advertises 256K context/8K output in this configuration; reliability is not benchmarked. A private key file is created only after confirmation, so no service restart is needed.');
  models=[...models.filter(m=>!(m.providerID==='omlx'&&m.id===id)),{providerID:'omlx',id,variants:[],capabilities:{tools:true}}];
 }
 }
 const ids=order.filter(id=>info.agents.some(a=>a.id===id)||(id==='orchestrator'&&profile==='coordinator')||(id==='cloud-reviewer'&&reviewer));
 const chosen=new Map();
 for(let index=0;index<ids.length;index++){
  const id=ids[index],agent=info.agents.find(a=>a.id===id)??{id,mode:id==='orchestrator'?'primary':'subagent',description:'Optional custom role'};
  console.log(`\n[${index+1}/${ids.length}] ${id} — ${customIds.includes(id)?'custom':'built-in'} ${agent.mode}${agent.hidden?' (hidden system agent)':''}\n${agent.description??'Internal system role'}\nCurrent model: ${agent.model?JSON.stringify(agent.model):'native/inherited'}\nPermissions: ${JSON.stringify(agent.permissions??'custom deny-by-default policy')}`);
  const model=await chooseModel(id,models);
  if(model==='back'){index=Math.max(-1,index-2);continue;}
  let prompt='native',text;
  if(enhancement(id))prompt=await select({message:'System instructions',choices:[{name:'Keep current/native text',value:'native'},{name:'Preview minimal role enhancement',value:'enhance'},{name:'Restore native agent system text',value:'restore'},{name:'Write custom system text in editor',value:'custom'}]});
  if(prompt==='custom')text=await editor({message:'Edit full agent-specific system text',default:agent.system??'',waitForUserInput:true});
  const choice={id,existing:info.agents.some(a=>a.id===id),...(model!=='keep'?{model}:{}),prompt,...(text!==undefined?{text}:{})};
  const changes=buildOverrides([choice]);
  for(const c of changes.filter(c=>c.path.at(-1)==='system'))console.log(promptDiff(id,agent.system,c.value??baseline.find(a=>a.id===id)?.system));
  chosen.set(id,choice);
 }
 let changes=[...localChanges,...buildOverrides([...chosen.values()])];
 if(profile==='coordinator'&&await confirm({message:'Make custom Orchestrator the default primary agent?',default:true}))changes.push({path:['default_agent'],value:'orchestrator'});
 if(!changes.length){console.log('No changes selected.');return;}
 if(pendingCredential)console.log(`On apply, create a private local credential file: ${pendingCredential.file}. Reset/undo preserve credentials.`);
 const p=show(file,changes,info.agents);
 if(!await approved(`Apply these exact changes to ${file}?`,opts)){console.log('No configuration changes saved.');return;}
 let result;
 if(pendingCredential)writeCredential(pendingCredential);
 try{result=await apply(file,changes,{expected:p.before,validate:validateNative});}
 catch(error){
  // Preserve a reference after an interrupted/conflicted apply so recovery remains possible.
  if(pendingCredential&&!(readTarget(file)??'').includes(pendingCredential.file))fs.unlinkSync(pendingCredential.file);
  throw error;
 }
 console.log(result.changed?'Saved and validated. Use a fresh OpenCode session. Backups are private in the setup state directory.':'Already configured; no changes.');
}
const pluginSource=path.resolve(path.dirname(new URL(import.meta.url).pathname),'../plugin/agent-usage');
function pluginTarget(opts){
 const root=opts.project?path.join(process.cwd(),'.opencode'):path.join(process.env.XDG_CONFIG_HOME??path.join(os.homedir(),'.config'),'opencode');
 return path.join(root,'plugins','agent-usage');
}
function plugin(opts){
 const action=opts.action??'status';const target=pluginTarget(opts);
 const linked=()=>{try{return fs.lstatSync(target).isSymbolicLink()&&fs.realpathSync(target)===fs.realpathSync(pluginSource);}catch{return false;}};
 if(action==='status'){console.log(linked()?`installed: ${target} -> ${pluginSource}`:fs.existsSync(target)?`${target} exists but was not installed by this tool`:`not installed (${target})`);console.log('Restart OpenCode after install/uninstall. Open the live panel with /usage; the end-of-session report is written under '+path.join(process.env.XDG_STATE_HOME??path.join(os.homedir(),'.local/state'),'opencode-agent-setup','usage')+'.');return;}
 if(action==='install'){
  if(linked()){console.log(`already installed: ${target}`);return;}
  if(fs.existsSync(target)||(()=>{try{fs.lstatSync(target);return true;}catch{return false;}})())throw Error(`${target} exists and is not this tool's link; remove it first.`);
  fs.mkdirSync(path.dirname(target),{recursive:true});fs.symlinkSync(pluginSource,target,'dir');
  console.log(`installed: ${target} -> ${pluginSource}\nRestart OpenCode. Live panel: /usage. The plugin reads session data only; it makes no model requests.`);return;
 }
 if(action==='uninstall'){
  if(!linked()){if(fs.existsSync(target))throw Error(`${target} is not a link installed by this tool; not removing it.`);console.log('not installed');return;}
  fs.unlinkSync(target);console.log(`removed ${target}`);return;
 }
 throw Error(`Unknown plugin action: ${action}`);
}
function usage(opts){
 const db=openDatabase(opts.db);
 try{
  const directory=opts.directory?path.resolve(opts.directory):process.cwd();
  if(opts.list){
   const roots=listRoots(db,{directory,limit:Number(opts.limit??10)});
   if(!roots.length)throw Error(`No session found for ${directory}. Use --directory DIR or --session ID.`);
   for(const r of roots)console.log(`${r.id}  ${new Date(r.updated).toISOString()}  ${r.agent??'?'}  ${r.title}`);
   return;
  }
  const root=opts.session?{id:opts.session}:findRoot(db,{directory});
  if(!root)throw Error(`No session found for ${directory}. Use --directory DIR, --session ID, or --list.`);
  const pricing=opts.pricing?JSON.parse(fs.readFileSync(opts.pricing,'utf8')):{};
  const report=analyze(loadTree(db,root.id),{pricing});
  if(opts.json){console.log(JSON.stringify(opts.compare?[report,analyze(loadTree(db,opts.compare),{pricing})]:report,null,2));return;}
  console.log(render(report));
  if(opts.compare){const other=analyze(loadTree(db,opts.compare),{pricing});console.log('\n'+renderComparison([report,other]));}
 }finally{db.close();}
}
export async function main(argv=process.argv.slice(2)){
 const opts=argsOf(argv);if(opts.help){console.log(help);return;}
 if(opts.command==='usage'){usage(opts);return;}
 if(opts.command==='plugin'){plugin(opts);return;}
 if(opts.command==='wizard'&&!process.stdin.isTTY)throw Error('Interactive setup needs a terminal. Use --help or preview --choices FILE.');
 let file=targetPath(opts.config);
 if(opts.command==='preview'){
  if(!opts.choices)throw Error('--choices FILE is required');show(file,buildOverrides(JSON.parse(fs.readFileSync(opts.choices,'utf8'))));return;
 }
 console.log('Discovering native OpenCode agents/models (no inference)…');const info=await discover();
 if(opts.command==='inspect'){console.log(JSON.stringify({file,...redact(info),models:info.models.map(m=>({id:`${m.providerID}/${m.id}`,variants:m.variants})),warnings:overrideWarnings(file,info.sources)},null,2));return;}
 if(!info.supported)throw Error(`Unsupported version ${info.version}; inspect is available, writes are disabled.`);
 if(opts.command==='wizard'&&!opts.config){
  const scope=await select({message:'Configuration scope',choices:[{name:`Global — ${file}`,value:'global'},{name:`This project — ${process.cwd()}`,value:'project'}]});
  if(scope==='project'){
   const json=path.join(process.cwd(),'opencode.json'),jsonc=path.join(process.cwd(),'opencode.jsonc');
   if(fs.existsSync(json)&&fs.existsSync(jsonc))throw Error('Both project config formats exist; use --config explicitly.');
   file=fs.existsSync(jsonc)?jsonc:json;
  }
 }
 const warnings=overrideWarnings(file,info.sources);for(const w of warnings)console.log('Notice: '+w);
 if(opts.command==='wizard'){await wizard(opts,file,info);return;}
 if(opts.command==='undo'){
  const p=undoPreview(file);console.log(createTwoFilesPatch(file,file,redactText(p.before??''),redactText(p.after??'')));
  if(await approved('Undo this transaction?',opts)){await undo(file,{expected:p.before,validate:validateNative});console.log('Previous configuration restored.');}return;
 }
 let changes;
 if(opts.command==='reset'){
  const obj=parseConfig(readTarget(file)??'{}');let includeCustom=opts.yes;
  if(!opts.yes&&!opts['dry-run'])includeCustom=await confirm({message:'Also remove Orchestrator/cloud-reviewer overrides in this JSON file?',default:false});
  changes=resetChanges(obj,includeCustom);
 }else{
  if(!opts.choices)throw Error('--choices FILE is required');const choices=JSON.parse(fs.readFileSync(opts.choices,'utf8'));
  for(const c of choices)if(c.model)selectModel(c.model,info.models);
  changes=buildOverrides(choices.map(c=>({...c,existing:info.agents.some(a=>a.id===c.id)})));
 }
 const p=show(file,changes,info.agents);
 if(await approved('Apply these exact changes?',opts)){await apply(file,changes,{expected:p.before,validate:validateNative});console.log('Saved and native-validated. Start a fresh session.');}
}
