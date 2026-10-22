import { execFileSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import { parseConfig,readTarget } from './store.js';
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
function matchesPattern(pattern,value){
 const regex='^'+pattern.split('*').map(x=>x.replace(/[.*+?^${}()|[\]\\]/g,'\\$&')).join('.*')+'$';
 return new RegExp(regex).test(value);
}
function effectivePermission(rules,action,resource){
 let effect;
 for(const r of rules)if(matchesPattern(r.action,action)&&matchesPattern(r.resource,resource))effect=r.effect;
 return effect;
}
function runtimeMatches(actual,keys,expected){
 if(expected===undefined)return true; // removals are checked against the decoded source document
 const field=keys.at(-1);
 if(field==='model'){
  const ref=normalizedModel(expected);
  return actual?.model?.providerID===ref.providerID&&actual?.model?.id===ref.model&&actual?.model?.variant===ref.variant;
 }
 if(field==='permissions')return expected.every(r=>r.action==='*'
  ?actual?.permissions?.some(a=>JSON.stringify(a)===JSON.stringify(r))
  :effectivePermission(actual?.permissions??[],r.action,r.resource)===r.effect);
 if(field==='disabled')return expected?!actual:!!actual;
 return JSON.stringify(actual?.[field])===JSON.stringify(expected);
}
export async function validateNative(file,changes=[]){
 const directory=path.dirname(file),text=readTarget(file),obj=text===null?{}:parseConfig(text);
 const expectedKeys=changes.filter(c=>c.path[0]==='agents').map(c=>c.path);
 for(let i=0;i<30;i++){
  const docs=api('config.get',directory);
  const doc=docs.find(e=>e.type==='document'&&e.path===path.resolve(file));
  const valid=text===null?!doc:!!doc;
  if(valid){
   let matches=true;
   const agents=api('agent.list',directory);
   for(const keys of expectedKeys){
    let expected=keys.reduce((o,k)=>o?.[k],obj),actual=keys.reduce((o,k)=>o?.[k],doc?.info);
    if(keys.at(-1)==='model')expected=normalizedModel(expected);
    if(JSON.stringify(expected)!==JSON.stringify(actual)||!runtimeMatches(agents.find(a=>a.id===keys[1]),keys,expected)){matches=false;break;}
   }
   if(obj.default_agent&&agents[0]?.id!==obj.default_agent)matches=false;
   const rawModels=api('model.list',directory);
   const models=normalizeModels(rawModels);
   for(const id of Object.keys(obj.agents??{})){
    const ref=obj.agents[id].model;if(!ref)continue;
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
   if(matches&&agents.some(a=>a.id==='build')&&Object.keys(obj.agents??{}).every(id=>obj.agents[id].disabled||agents.some(a=>a.id===id)))return;
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
