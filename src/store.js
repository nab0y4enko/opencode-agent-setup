import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import crypto from 'node:crypto';
import { parse, parseTree, modify, applyEdits, visit } from 'jsonc-parser';
import { createTwoFilesPatch } from 'diff';
import { baseline,customIds } from './policy.js';
export function parseConfig(text){
 const errors=[];const value=parse(text,errors,{allowTrailingComma:true,disallowComments:false});
 if(errors.length)throw Error(`Invalid JSONC configuration (offset ${errors[0].offset})`);
 if(!value||Array.isArray(value)||typeof value!=='object')throw Error('Configuration must be an object');
 const stack=[];visit(text,{onObjectBegin(){stack.push(new Set());},onObjectProperty(key){const keys=stack.at(-1);if(keys.has(key))throw Error(`Invalid duplicate key: ${key}`);keys.add(key);},onObjectEnd(){stack.pop();}});
 return value;
}
export function readTarget(file){
 try{const stat=fs.lstatSync(file);if(stat.isSymbolicLink())throw Error('Refusing symbolic link target');if(!stat.isFile())throw Error('Target is not a file');return fs.readFileSync(file,'utf8');}
 catch(e){if(e.code==='ENOENT')return null;throw e;}
}
export function preview(file,changes){
 const before=readTarget(file);let after=before??'{}\n';parseConfig(after);
 for(const c of changes) after=applyEdits(after,modify(after,c.path,c.value,{formattingOptions:{insertSpaces:true,tabSize:2,eol:'\n'}}));
 parseConfig(after);
 return {before,after,diff:createTwoFilesPatch(file,file,before??'',after)};
}
const equal=(a,b)=>JSON.stringify(a)===JSON.stringify(b);
const get=(obj,keys)=>keys.reduce((o,k)=>o?.[k],obj);
function atomic(file,text){
 const tmp=file+'.'+crypto.randomUUID()+'.tmp';
 try{fs.writeFileSync(tmp,text,{mode:0o600,flag:'wx'});const fd=fs.openSync(tmp,'r');try{fs.fsyncSync(fd);}finally{fs.closeSync(fd);}fs.renameSync(tmp,file);}finally{if(fs.existsSync(tmp))fs.unlinkSync(tmp);}
}
function journalPath(file,state){
 const dir=state??path.join(process.env.XDG_STATE_HOME??path.join(os.homedir(),'.local/state'),'opencode-agent-setup');
 fs.mkdirSync(dir,{recursive:true,mode:0o700});if(fs.lstatSync(dir).isSymbolicLink())throw Error('Refusing symbolic link state directory');fs.chmodSync(dir,0o700);
 return path.join(dir,crypto.createHash('sha256').update(path.resolve(file)).digest('hex')+'.json');
}
function loadHistory(file){const raw=readTarget(file);return raw?JSON.parse(raw):[];}
async function locked(file,fn){
 fs.mkdirSync(path.dirname(file),{recursive:true,mode:0o700});
 let fd;try{fd=fs.openSync(file+'.agent-setup.lock','wx',0o600);}catch(e){throw Error('Writer lock exists; another setup may be running. Inspect the lock before removing it.');}
 try{return await fn();}finally{fs.closeSync(fd);fs.unlinkSync(file+'.agent-setup.lock');}
}
export async function apply(file,changes,{state,expected,validate}={}){
 if(typeof validate!=='function')throw Error('Native validation is required');
 return locked(file,async()=>{
  const p=preview(file,changes);if(p.before!==expected)throw Error('Configuration changed since preview; review again.');
  if(p.after===(p.before??'{}\n'))return {changed:false};
  const dest=journalPath(file,state);const history=loadHistory(dest);
  if(history.at(-1)?.status==='prepared')throw Error('Unfinished transaction; run undo before applying again.');
  const prior=parseConfig(p.before??'{}');const next=parseConfig(p.after);
  const entry={file:path.resolve(file),date:new Date().toISOString(),status:'prepared',before:p.before,after:p.after,changes:changes.map(c=>({path:c.path,before:get(prior,c.path),after:get(next,c.path)}))};
  history.push(entry);atomic(dest,JSON.stringify(history,null,2));
  try{
   atomic(file,p.after);await validate(file,changes);
   if(readTarget(file)!==p.after)throw Error('Configuration changed during validation; recovery required.');
   entry.status='applied';atomic(dest,JSON.stringify(history,null,2));return {changed:true,backup:dest};
  }catch(e){
   if(readTarget(file)===p.after){if(p.before===null)fs.unlinkSync(file);else atomic(file,p.before);history.pop();atomic(dest,JSON.stringify(history,null,2));}
   throw e;
  }
 });
}
export function undoPreview(file,{state}={}){
 const dest=journalPath(file,state),history=loadHistory(dest),entry=history.at(-1);
 if(!entry)throw Error('No tool transaction to undo for this configuration.');
 const current=readTarget(file);
 if(current===entry.before)return {before:current,after:current,dest,history};
 if(current===entry.after)return {before:current,after:entry.before,dest,history};
 let after=current??'{}';const obj=parseConfig(after);
 for(const c of entry.changes){if(!equal(get(obj,c.path),c.after))throw Error(`Undo conflict: ${c.path.join('.')} was changed after apply.`);after=applyEdits(after,modify(after,c.path,c.before,{formattingOptions:{insertSpaces:true,tabSize:2}}));}
 const original=parseConfig(entry.before??'{}');
 const ancestors=new Map();
 for(const c of entry.changes)for(let n=c.path.length-1;n>0;n--){const keys=c.path.slice(0,n);ancestors.set(JSON.stringify(keys),keys);}
 for(const keys of [...ancestors.values()].sort((a,b)=>b.length-a.length)){
  const value=get(parseConfig(after),keys);
  if(get(original,keys)===undefined&&value&&typeof value==='object'&&!Array.isArray(value)&&!Object.keys(value).length)
   after=applyEdits(after,modify(after,keys,undefined,{formattingOptions:{insertSpaces:true,tabSize:2}}));
 }
 return {before:current,after,dest,history};
}
export async function undo(file,{state,expected,validate=async()=>{}}={}){
 return locked(file,async()=>{
  const p=undoPreview(file,{state});
  if(expected!==undefined&&p.before!==expected)throw Error('Configuration changed since undo preview; review again.');
  if(p.after===null){if(fs.existsSync(file))fs.unlinkSync(file);}else atomic(file,p.after);
  try{await validate(file,[]);}catch(e){if(p.before===null){if(fs.existsSync(file))fs.unlinkSync(file);}else atomic(file,p.before);throw e;}
  p.history.pop();atomic(p.dest,JSON.stringify(p.history,null,2));return {changed:p.before!==p.after};
 });
}
export function resetChanges(obj,includeCustom=false){
 const ids=[...baseline.map(a=>a.id),...(includeCustom?customIds:[])];const changes=[];
 for(const key of ['agents','agent'])for(const id of ids)if(obj[key]?.[id]!==undefined)changes.push({path:[key,id],value:undefined});
 if(ids.includes(obj.default_agent))changes.push({path:['default_agent'],value:undefined});
 return changes;
}
export function redact(value){
 if(Array.isArray(value))return value.map(redact);
 if(value&&typeof value==='object')return Object.fromEntries(Object.entries(value).map(([k,v])=>[k,/api.?key|authorization|password|secret|token/i.test(k)?'[REDACTED]':redact(v)]));
 return value;
}

export function redactText(text){
 if(!text)return text;
 const edits=[];
 function walk(node){
  if(node.type==='property'&&/api.?key|authorization|password|secret|token/i.test(node.children[0].value)){
   const value=node.children[1];edits.push({offset:value.offset,length:value.length,content:'"[REDACTED]"'});return;
  }
  for(const child of node.children??[])walk(child);
 }
 const tree=parseTree(text);if(tree)walk(tree);
 return applyEdits(text,edits);
}
