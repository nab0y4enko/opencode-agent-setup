import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import os from 'node:os';
import {apply,undo,preview} from '../src/store.js';
import {buildOverrides} from '../src/policy.js';
import {api,discover,validateNative} from '../src/native.js';
const live=process.env.RUN_NATIVE_TESTS==='1';
function fixture(){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'opencode-native-integration-'));return {dir,file:path.join(dir,'opencode.json'),state:path.join(dir,'private-state')};}
test('native runtime loads custom roles, effective permissions and exact worker prompt, then undo',{skip:!live},async()=>{
 const {dir,file,state}=fixture();const info=await discover(dir);assert.ok(info.agents.some(agent=>agent.id==='build'));
 const model=info.models[0];const ref=`${model.providerID}/${model.id}`;
 const changes=[...buildOverrides([{id:'orchestrator',model:ref,prompt:'enhance'},{id:'build',model:ref,prompt:'enhance'},{id:'general',model:ref,prompt:'enhance'},{id:'cloud-reviewer',model:ref,prompt:'enhance'},{id:'explore',model:ref,prompt:'enhance'}]),{path:['default_agent'],value:'orchestrator'}];
 await apply(file,changes,{state,expected:null,validate:validateNative});
 const actual=api('agent.list',dir);assert.equal(actual[0].id,'orchestrator');
 assert.equal(actual.find(a=>a.id==='build').mode,'all');
 for(const id of ['orchestrator','general','build'])assert.equal(actual.find(a=>a.id===id).system,changes.find(c=>c.path.join('.')===`agents.${id}.system`).value,`${id} exact revised runtime instructions`);
 const coordinator=actual[0];assert.equal(coordinator.model.id,model.id);assert.ok(coordinator.permissions.some(r=>r.action==='shell'&&r.effect==='deny'));
 assert.match(actual.find(a=>a.id==='explore').system,/MUST NOT create/);
 await undo(file,{state,expected:fs.readFileSync(file,'utf8'),validate:validateNative});assert.equal(fs.existsSync(file),false);
 fs.rmSync(dir,{recursive:true,force:true});
});
test('native validation rejects higher-priority Markdown prompt shadowing and rolls back',{skip:!live},async()=>{
 const {dir,file,state}=fixture();fs.mkdirSync(path.join(dir,'.opencode','agents'),{recursive:true});fs.writeFileSync(path.join(dir,'.opencode','agents','general.md'),'---\ndescription: Shadow role\nmode: subagent\n---\nShadowed instructions\n');
 await discover(dir);await assert.rejects(apply(file,[{path:['agents','general','system'],value:'Expected instructions'}],{state,expected:null,validate:validateNative}),/validation|shadow/i);
 assert.equal(fs.existsSync(file),false);fs.rmSync(dir,{recursive:true,force:true});
});
test('real local provider registers using a private key file without restarting service',{skip:process.env.RUN_LOCAL_TESTS!=='1'},async()=>{
 const {proposedLocalProvider,localModels}=await import('../src/native.js');
 const {privateCredential,writeCredential}=await import('../src/credentials.js');
 const settings=JSON.parse(fs.readFileSync(path.join(os.homedir(),'.omlx/settings.json'),'utf8'));
 const endpoint=`http://127.0.0.1:${settings.server.port}/v1`;
 const available=await localModels(endpoint,settings.auth.api_key);const model=available.find(m=>/splash/i.test(m.id));assert.ok(model);
 const {dir,file,state}=fixture();const secret=privateCredential(settings.auth.api_key,path.join(dir,'credentials'));writeCredential(secret);
 const provider=proposedLocalProvider(endpoint,model.id,'OMLX_API_KEY');provider[0].value.settings.apiKey=`{file:${secret.file}}`;
 const changes=[...provider,...buildOverrides([{id:'general',model:`omlx/${model.id}`,prompt:'enhance'}])];
 try{
  await apply(file,changes,{state,expected:null,validate:validateNative});
  assert.ok(!fs.readFileSync(file,'utf8').includes(settings.auth.api_key));
  assert.ok(api('model.list',dir).some(m=>m.providerID==='omlx'&&m.id===model.id));
  await undo(file,{state,expected:fs.readFileSync(file,'utf8'),validate:validateNative});
 }finally{fs.rmSync(dir,{recursive:true,force:true});}
});
