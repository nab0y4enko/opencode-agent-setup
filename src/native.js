import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import { isDeepStrictEqual } from 'node:util';
import { parseConfig,readTarget } from './store.js';
import { baseline } from './policy.js';
export const executable=process.env.OPENCODE_AGENT_SETUP_BINARY??'opencode';
const sleep=ms=>new Promise(resolve=>setTimeout(resolve,ms));
export function run(args,{cwd=process.cwd()}={}){
 try{return execFileSync(executable,args,{cwd,env:{...process.env,PWD:cwd},encoding:'utf8',timeout:30000,maxBuffer:16*1024*1024,stdio:['ignore','pipe','pipe']}).trim();}
 catch(e){throw Error(`OpenCode command failed (${args[0]}). Run it directly for diagnostic details; no configuration was accepted.`,{cause:e});}
}
export function supportedVersion(s){return /^opencode v2\.1\.2$/.test(s.trim());}
export function api(operation,directory){
 const result=JSON.parse(run(['api',operation,'--param',`location[directory]=${path.resolve(directory)}`],{cwd:directory}));
 return result?.data??result;
}
export function normalizeModels(models){
 return models.filter(m=>m.enabled!==false).map(m=>({providerID:m.providerID,id:m.id,name:m.name,enabled:m.enabled,capabilities:m.capabilities,limit:m.limit,variants:(m.variants??[]).map(v=>({id:typeof v==='string'?v:v.id}))}));
}
export async function discover(directory=process.cwd()){
 const version=run(['--version']);let agents=[];
 for(let i=0;i<30;i++){agents=api('agent.list',directory);if(agents.some(a=>a.id==='build'))break;await sleep(150);}
 if(!agents.some(a=>a.id==='build'))throw Error('Native Build agent not loaded. Inspect OpenCode plugins/configuration before patching.');
 const models=normalizeModels(api('model.list',directory));
 const entries=JSON.parse(run(['debug','config'],{cwd:directory}));
 return {version,supported:supportedVersion(version),agents,models,sources:entries.map(e=>({type:e.type,path:e.path,keys:Object.keys(e.info??{})}))};
}
function normalizedModel(value){if(typeof value!=='string')return value;const [base,variant]=value.split('#'),pos=base.indexOf('/');return {providerID:base.slice(0,pos),model:base.slice(pos+1),...(variant?{variant}:{})};}
// Enumerate the distinct matching sets of the glob languages, rather than treating
// a wildcard as a literal resource. A product of the small glob automata covers
// every possible string, including overlaps introduced by later configuration.
function patternCells(patterns){
 patterns=patterns.map(p=>p.replaceAll('\\','/'));
 if(process.platform==='win32'){
  // ASCII folding is exact; fail closed rather than approximate Unicode regex /i.
  if(patterns.some(p=>/[^\x00-\x7f]/.test(p)))throw Error('Native permission validation cannot verify non-ASCII Windows patterns.');
  patterns=patterns.map(p=>p.toLowerCase());
 }
 const alphabet=[...new Set(patterns.join('').replace(/[?*]/g,'').split(''))];
 let code=0;while(alphabet.includes(String.fromCharCode(code)))code++;alphabet.push(String.fromCharCode(code));
 const closure=(pattern,positions)=>{const result=new Set(positions);for(const pos of result){if(pattern[pos]==='*')result.add(pos+1);if(pos===pattern.length-2&&pattern.endsWith(' *'))result.add(pattern.length);}return [...result].sort((a,b)=>a-b);};
 const stateKey=states=>states.map(s=>s.join(',')).join(';');
 const initial=patterns.map(p=>closure(p,[0])),queue=[initial],seen=new Set([stateKey(initial)]),cells=new Map();
 for(let cursor=0;cursor<queue.length;cursor++){
  const states=queue[cursor];
  const matches=states.map((s,i)=>s.includes(patterns[i].length));cells.set(matches.map(Number).join(''),matches);
  for(const char of alphabet){
   const next=states.map((positions,i)=>closure(patterns[i],positions.flatMap(pos=>patterns[i][pos]==='*'?[pos]:patterns[i][pos]==='?'||patterns[i][pos]===char?[pos+1]:[])));
   const key=stateKey(next);if(!seen.has(key)){seen.add(key);queue.push(next);}
   if(seen.size>20000)throw Error('Native permission validation exceeded its pattern complexity limit; configuration was not accepted.');
  }
 }
 return [...cells.values()];
}
function permissionsMatch(actual,expected){
 expected=expected.map(rule=>{
  if(!['external_directory','read','edit'].includes(rule.action))return rule;
  const home=os.homedir(),resource=rule.resource;
  if(resource==='~'||resource==='$HOME')return {...rule,resource:home};
  const relative=resource.startsWith('~/')?resource.slice(2):resource.startsWith('$HOME/')||resource.startsWith('$HOME\\')?resource.slice(6):undefined;
  return relative===undefined?rule:{...rule,resource:(path.posix.isAbsolute(home)?path.posix:path.win32).join(home,relative)};
 });
 const rules=[...expected,...actual];
 const actions=patternCells(rules.map(r=>r.action)),resources=patternCells(rules.map(r=>r.resource));
 for(const action of actions)for(const resource of resources){
  let wanted,effective='ask';
  for(let i=0;i<rules.length;i++)if(action[i]&&resource[i]){if(i<expected.length)wanted=rules[i].effect;else effective=rules[i].effect;}
  if(wanted!==undefined&&wanted!==effective)return false;
 }
 return true;
}
function runtimeMatches(actual,keys,expected){
 const field=keys.at(-1);
 if(expected===undefined)return actual?.[field]===undefined;
 if(field==='model'){
  const ref=normalizedModel(expected);
  return actual?.model?.providerID===ref.providerID&&actual?.model?.id===ref.model&&actual?.model?.variant===ref.variant;
 }
 if(field==='permissions')return permissionsMatch(actual?.permissions??[],expected);
 if(field==='request')return !!actual?.request&&isDeepStrictEqual(actual.request.headers??{},expected.headers??{})&&isDeepStrictEqual(actual.request.body??{},expected.body??{});
 if(field==='disabled')return expected?!actual:!!actual;
 return isDeepStrictEqual(actual?.[field],expected);
}
function inheritedAgent(docs,id){
 let result=baseline.find(a=>a.id===id);
 if(id==='plan'&&result)result={...result,permissions:result.permissions.map(rule=>rule.resource.endsWith('/.opencode/plan/*')?{...rule,resource:path.join(os.homedir(),'.opencode/plan/*')}:rule)};
 const permissions=docs.flatMap(doc=>doc.info?.permissions??[]);
 if(result)result={...result,permissions:[...(result.permissions??[]),...permissions]};
 for(const doc of docs){const agent=doc.info?.agents?.[id];if(!agent)continue;
  if(agent.disabled){result=undefined;continue;}
  if(!result)result={permissions,request:{settings:{},headers:{},body:{}}};
  const request=agent.request===undefined?result.request:{...result.request,headers:{...result.request?.headers,...agent.request.headers},body:{...result.request?.body,...agent.request.body}};
  result={...result,...agent,request,...(agent.permissions?{permissions:[...(result?.permissions??[]),...agent.permissions]}:{})};
 }
 return result;
}
function decodedMatches(expected,actual){
 if(typeof expected==='string'&&/^\{(?:env|file):[^}]+\}$/.test(expected))return typeof actual==='string';
 if(expected&&typeof expected==='object'&&!Array.isArray(expected))return actual&&Object.entries(expected).every(([key,value])=>decodedMatches(value,actual[key]));
 return isDeepStrictEqual(expected,actual);
}
function hasMarkdownAgent(docs,id){
 return docs.some(doc=>doc.type==='directory'&&['agents','agent','modes','mode'].some(sub=>fs.existsSync(path.join(doc.path,sub,`${id}.md`))));
}
const hasReference=value=>typeof value==='string'&&/\{(?:env|file):[^}]+\}/.test(value);
function referenceSourceMatches(expected,actual,keys,fields){
 if(hasReference(expected)){
  if(keys.at(-1)==='model'&&actual?.providerID&&actual?.model)actual=`${actual.providerID}/${actual.model}${actual.variant?`#${actual.variant}`:''}`;
  if(typeof actual!=='string')return false;
  const pattern=expected.split(/\{(?:env|file):[^}]+\}/g).map(part=>part.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('[\\s\\S]*');
  if(!new RegExp(`^${pattern}$`).test(actual))return false;
  fields.add(keys[2]);return true;
 }
 if(expected&&typeof expected==='object'){
  if(!actual||typeof actual!=='object'||Array.isArray(expected)!==Array.isArray(actual)||Object.keys(expected).length!==Object.keys(actual).length)return false;
  return Object.entries(expected).every(([key,value])=>Object.hasOwn(actual,key)&&referenceSourceMatches(value,actual[key],[...keys,key],fields));
 }
 return isDeepStrictEqual(expected,actual);
}
export async function validateNative(file,changes=[]){
 const directory=path.dirname(file),text=readTarget(file),obj=text===null?{}:parseConfig(text);
 const agentChanges=changes.filter(c=>c.path[0]==='agents');
 for(let i=0;i<30;i++){
  const docs=api('config.get',directory);
  const doc=docs.find(e=>e.type==='document'&&e.path===path.resolve(file));
  const valid=text===null?!doc:!!doc;
  if(valid){
   let matches=true;const unverifiable=new Set(),referenceFields=new Set();
   const agents=api('agent.list',directory);
   const restoredMatches=(change,agent,keys,expected)=>{
    if(runtimeMatches(agent,keys,expected))return true;
    if(change.restoration&&hasMarkdownAgent(docs,keys[1])){unverifiable.add(keys[1]);return true;}
    return false;
   };
   for(const change of changes.filter(c=>c.restoration&&c.path[0]!=='agents')){
    const expected=change.path.reduce((o,k)=>o?.[k],obj),actual=change.path.reduce((o,k)=>o?.[k],doc?.info);
    if(!decodedMatches(expected,actual)){matches=false;break;}
   }
   for(const change of agentChanges){
    const keys=change.path;
    let expected=keys.reduce((o,k)=>o?.[k],obj),actual=keys.reduce((o,k)=>o?.[k],doc?.info);
    if(keys.at(-1)==='model'&&!hasReference(expected))expected=normalizedModel(expected);
    const decodedExpected=keys.length===2&&expected?.model&&!hasReference(expected.model)?{...expected,model:normalizedModel(expected.model)}:expected;
    if(!isDeepStrictEqual(decodedExpected,actual)){
     const fields=new Set();
     if(!change.restoration||!referenceSourceMatches(decodedExpected,actual,keys,fields)||!fields.size){matches=false;break;}
     for(const field of fields)referenceFields.add(JSON.stringify([keys[1],field]));
     unverifiable.add(`native env/file references in ${keys.join('.')}`);
    }
    const agent=agents.find(a=>a.id===keys[1]);
    if(obj.agents?.[keys[1]]?.disabled){if(agent)matches=false;continue;}
    if(expected===undefined){
     const inherited=inheritedAgent(docs,keys[1]);
     if(!inherited){if(agent){if(change.restoration&&hasMarkdownAgent(docs,keys[1]))unverifiable.add(keys[1]);else matches=false;}}
     else if(keys.length===2){
      for(const field of Object.keys(change.previousValue??{}))if(!restoredMatches(change,agent,['agents',keys[1],field],inherited[field]))matches=false;
     }else if(!restoredMatches(change,agent,keys,inherited[keys.at(-1)]))matches=false;
    }else if(keys.length===2){
     for(const field of Object.keys(expected)){
      const effective=field==='request'||referenceFields.has(JSON.stringify([keys[1],field]))?inheritedAgent(docs,keys[1])?.[field]:expected[field];
      if(!runtimeMatches(agent,[...keys,field],effective))matches=false;
     }
    }else if(!runtimeMatches(agent,keys,keys.at(-1)==='request'||referenceFields.has(JSON.stringify([keys[1],keys.at(-1)]))?inheritedAgent(docs,keys[1])?.[keys.at(-1)]:expected))matches=false;
    if(!matches)break;
   }
   if(obj.default_agent&&agents[0]?.id!==obj.default_agent)matches=false;
   if(changes.some(c=>c.path[0]==='default_agent'&&c.value===undefined)){
    const inherited=docs.map(d=>d.info?.default_agent).filter(Boolean).at(-1)??'build';
    if(agents[0]?.id!==inherited)matches=false;
   }
   const rawModels=api('model.list',directory);
   const models=normalizeModels(rawModels);
   for(const id of Object.keys(obj.agents??{})){
    if(obj.agents[id].disabled)continue;
    const ref=referenceFields.has(JSON.stringify([id,'model']))?inheritedAgent(docs,id)?.model:obj.agents[id].model;if(!ref)continue;
    const normalized=normalizedModel(ref);
    const model=models.find(m=>m.providerID===normalized.providerID&&m.id===normalized.model);
    if(!model||(normalized.variant&&!model.variants.some(v=>v.id===normalized.variant)))matches=false;
   }
   for(const provider of Object.keys(obj.providers??{})){
    if(!doc?.info?.providers?.[provider])matches=false;
    for(const id of Object.keys(obj.providers[provider].models??{}))if(!models.some(m=>m.providerID===provider&&m.id===id))matches=false;
   }
   if(matches&&changes.some(c=>c.path[0]==='providers'&&c.path[1]==='omlx')){
    const local=rawModels.find(m=>m.providerID==='omlx');
    if(local?.settings?.baseURL){
     const url=new URL(local.settings.baseURL);
     if(!['127.0.0.1','localhost','[::1]'].includes(url.hostname))throw Error('Unexpected non-local oMLX endpoint; native validation rejected.');
     await localModels(local.settings.baseURL,local.settings.apiKey);
    }
   }
   if(matches&&agents.some(a=>a.id==='build')&&Object.keys(obj.agents??{}).every(id=>obj.agents[id].disabled||agents.some(a=>a.id===id))){
    if(unverifiable.size){const error=Error(`Native restoration validation unavailable: ${[...unverifiable].map(item=>item.startsWith('native env/file references')?item:`Markdown agent inheritance for ${item}`).join('; ')} cannot be independently verified from config.get.`);error.code='NATIVE_RESTORATION_UNVERIFIABLE';throw error;}
    return;
   }
  }
  await sleep(150);
 }
 throw Error('Native validation failed: effective settings are shadowed, a model is unavailable, or configuration was rejected. Rolled back where safe.');
}
export function validateLocalEndpoint(endpoint){
 const url=new URL(endpoint);
 if(!['127.0.0.1','localhost','[::1]'].includes(url.hostname)||!['http:','https:'].includes(url.protocol)||url.username||url.password)throw Error('Local provider must use a loopback URL without embedded credentials.');
 return url;
}
export function proposedLocalProvider(endpoint,modelId,envName){
 validateLocalEndpoint(endpoint);
 if(!/^[A-Za-z_][A-Za-z0-9_]*$/.test(envName))throw Error('Invalid environment variable name');
 if(!modelId||modelId.includes('#'))throw Error('Invalid model ID');
 return [{path:['providers','omlx'],value:{name:'oMLX local',package:'@opencode/ai/providers/openai-compatible',settings:{baseURL:endpoint.replace(/\/$/,''),apiKey:`{env:${envName}}`},models:{[modelId]:{name:modelId,capabilities:{tools:true,input:['text'],output:['text']},limit:{context:262144,output:8192}}}}}];
}
export async function localModels(endpoint,apiKey){
 validateLocalEndpoint(endpoint);
 const response=await fetch(endpoint.replace(/\/$/,'')+'/models',{redirect:'error',headers:apiKey?{Authorization:`Bearer ${apiKey}`}:{},signal:AbortSignal.timeout(10000)});
 if(!response.ok)throw Error(`Local model discovery returned HTTP ${response.status}; check the selected API key before continuing.`);
 const payload=await response.json();if(!Array.isArray(payload.data))throw Error('Invalid local model inventory');
 return payload.data.filter(m=>typeof m.id==='string').map(m=>({id:m.id}));
}
export function overrideWarnings(file,sources){
 const warnings=[];
 for(const name of ['OPENCODE_CONFIG','OPENCODE_CONFIG_CONTENT','OPENCODE_CONFIG_DIR'])if(process.env[name])warnings.push(`${name} is set; effective settings may differ.`);
 for(const source of sources){if(source.path&&source.path!==file)warnings.push(`Additional ${source.type} source: ${source.path}`);}
 const roots=new Set([path.dirname(file),...sources.filter(s=>s.type==='directory').map(s=>s.path)]);
 for(const root of roots)for(const sub of ['agents','agent','modes','mode']){
  const dir=path.join(root,sub);if(fs.existsSync(dir)&&fs.readdirSync(dir).length)warnings.push(`Agent files in ${dir} may override JSON settings; reset does not delete those files.`);
 }
 return warnings;
}
