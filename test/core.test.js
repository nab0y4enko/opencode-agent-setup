import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { buildOverrides, promptDiff, selectModel, baseline } from '../src/policy.js';
import { parseConfig, preview, apply, undo, resetChanges, readTarget } from '../src/store.js';
const models = [{providerID:'openai',id:'strong',variants:[{id:'high'}],capabilities:{tools:true}}, {providerID:'omlx',id:'qwen',variants:[],capabilities:{tools:true}}];
const fixture = () => { const dir=fs.mkdtempSync(path.join(os.tmpdir(),'native patcher '));return {dir,file:path.join(dir,'opencode.jsonc'),state:path.join(dir,'state')}; };
test('explicit models and variants must exist; never silently fall back',()=>{
 assert.equal(selectModel('openai/strong#high',models),'openai/strong#high');
 assert.throws(()=>selectModel('openai/strong#max',models),/variant/);
 assert.throws(()=>selectModel('omlx/missing',models),/available/);
});
test('enhanced worker retains exact native prompt and concise contract',()=>{
 const changes=buildOverrides([{id:'explore',model:'omlx/qwen',prompt:'enhance'}]);
 const system=changes.find(x=>x.path.join('.')==='agents.explore.system').value;
 assert.ok(system.startsWith(baseline.find(x=>x.id==='explore').system));
 assert.match(system,/line references/);
 assert.match(promptDiff('explore','',system),/\+.*read-only|\+.*MUST NOT/);
});
test('native prompts produce no system override; coordinator hard permissions included',()=>{
 const changes=buildOverrides([{id:'title',model:'omlx/qwen',prompt:'native'},{id:'orchestrator',model:'openai/strong',prompt:'enhance'}]);
 assert.ok(!changes.some(x=>x.path.join('.')==='agents.title.system'));
 const rules=changes.find(x=>x.path.join('.')==='agents.orchestrator.permissions').value;
 for(const action of ['edit','shell']) assert.ok(rules.some(x=>x.action===action&&x.effect==='deny'));
});
test('JSONC comments survive preview/apply and undo restores exact original bytes',async()=>{
 const {file,state}=fixture();const original='// keep comment\n{ "username": "me", "agents": {"build":{"steps":9}}, }\n'; fs.writeFileSync(file,original);
 const changes=buildOverrides([{id:'build',model:'openai/strong',prompt:'native'}]);
 const p=preview(file,changes);assert.match(p.after,/keep comment/);assert.equal(fs.readFileSync(file,'utf8'),original);
 await apply(file,changes,{state,expected:p.before,validate:async()=>{}});
 assert.equal(parseConfig(fs.readFileSync(file,'utf8')).agents.build.steps,9);
 await undo(file,{state});assert.equal(fs.readFileSync(file,'utf8'),original);
});
test('failed native validation rolls back; concurrent preview edits are rejected',async()=>{
 const {file,state}=fixture(); fs.writeFileSync(file,'{}');const p=preview(file,[{path:['default_agent'],value:'build'}]);
 await assert.rejects(apply(file,[{path:['default_agent'],value:'build'}],{state,expected:p.before,validate:async()=>{throw Error('bad config')}}),/bad config/);
 assert.equal(fs.readFileSync(file,'utf8'),'{}');
 fs.writeFileSync(file,'{"username":"new"}');
 await assert.rejects(apply(file,[],{state,expected:p.before,validate:async()=>{}}),/changed/);
});
test('undo preserves unrelated later edits but refuses edits to owned fields',async()=>{
 const {file,state}=fixture(); fs.writeFileSync(file,'{}');
 await apply(file,[{path:['agents','build','model'],value:'openai/strong'}],{state,expected:'{}',validate:async()=>{}});
 let obj=parseConfig(fs.readFileSync(file,'utf8'));obj.username='later';fs.writeFileSync(file,JSON.stringify(obj));
 await undo(file,{state});assert.equal(parseConfig(fs.readFileSync(file,'utf8')).username,'later');
 const before=fs.readFileSync(file,'utf8');await apply(file,[{path:['default_agent'],value:'build'}],{state,expected:before,validate:async()=>{}});
 obj=parseConfig(fs.readFileSync(file,'utf8'));obj.default_agent='plan';fs.writeFileSync(file,JSON.stringify(obj));
 await assert.rejects(undo(file,{state}),/conflict/i);
});
test('reset removes built-in overrides and selected custom roles, preserves provider/auth settings',()=>{
 const source='{"agents":{"build":{"steps":9},"orchestrator":{"mode":"primary"},"mine":{"mode":"subagent"}},"providers":{"local":{}},"default_agent":"orchestrator"}';
 const dir=fixture();fs.writeFileSync(dir.file,source);const p=preview(dir.file,resetChanges(parseConfig(source),true));
 const obj=parseConfig(p.after);assert.ok(!obj.agents.build);assert.ok(!obj.agents.orchestrator);assert.ok(obj.agents.mine);assert.ok(obj.providers.local);assert.ok(!obj.default_agent);
});
test('malformed config, symlinks and active writer locks are rejected',async()=>{
 assert.throws(()=>parseConfig('{ bad'),/Invalid/);assert.throws(()=>parseConfig('[]'),/object/);
 const {file,state,dir}=fixture();fs.writeFileSync(path.join(dir,'real'),'{}');fs.symlinkSync(path.join(dir,'real'),file);assert.throws(()=>readTarget(file),/symbolic/);
 fs.unlinkSync(file);fs.writeFileSync(file,'{}');fs.writeFileSync(file+'.agent-setup.lock','busy');
 await assert.rejects(apply(file,[],{state,expected:'{}',validate:async()=>{}}),/lock/i);
});
test('apply is idempotent and empty-file reset/undo returns absence',async()=>{
 const {file,state}=fixture();const changes=[{path:['default_agent'],value:'build'}];
 await apply(file,changes,{state,expected:null,validate:async()=>{}});const before=fs.readFileSync(file,'utf8');
 const result=await apply(file,changes,{state,expected:before,validate:async()=>{}});assert.equal(result.changed,false);
 await undo(file,{state});assert.ok(!fs.existsSync(file));
});
test('undo removes newly created custom roles after unrelated user edits',async()=>{
 const {file,state}=fixture();fs.writeFileSync(file,'{}');
 await apply(file,buildOverrides([{id:'orchestrator',prompt:'enhance'}]),{state,expected:'{}',validate:async()=>{}});
 const obj=parseConfig(fs.readFileSync(file,'utf8'));obj.username='later';fs.writeFileSync(file,JSON.stringify(obj));
 await undo(file,{state});const restored=parseConfig(fs.readFileSync(file,'utf8'));assert.equal(restored.agents?.orchestrator,undefined);assert.equal(restored.username,'later');
});
test('undo rejects any edit after the user reviewed its preview',async()=>{
 const {file,state}=fixture();fs.writeFileSync(file,'{}');await apply(file,[{path:['default_agent'],value:'build'}],{state,expected:'{}',validate:async()=>{}});
 const expected=fs.readFileSync(file,'utf8');const obj=parseConfig(expected);obj.username='new';fs.writeFileSync(file,JSON.stringify(obj));
 await assert.rejects(undo(file,{state,expected}),/changed/);
});
test('keep existing custom role does not overwrite its prompt or permissions',()=>{
 const changes=buildOverrides([{id:'orchestrator',existing:true,prompt:'native'}]);assert.deepEqual(changes,[]);
});
test('enhanced Build is callable without coordinator/Build dispatch loops',()=>{
 const changes=buildOverrides([{id:'orchestrator',prompt:'enhance'},{id:'build',prompt:'enhance'}]);
 assert.equal(changes.find(c=>c.path.join('.')==='agents.build.mode')?.value,'all');
 const parent=changes.find(c=>c.path.join('.')==='agents.orchestrator.permissions').value;
 assert.ok(parent.some(r=>r.action==='subagent'&&r.resource==='build'&&r.effect==='allow'));
 const child=changes.find(c=>c.path.join('.')==='agents.build.permissions')?.value;
 assert.ok(child?.some(r=>r.action==='subagent'&&r.resource==='orchestrator'&&r.effect==='deny'));
});
test('implementation policies define evidence, self-review and safe stage commits',()=>{
 for(const id of ['general','build']){
  const text=buildOverrides([{id,prompt:'enhance'}]).find(c=>c.path.at(-1)==='system').value;
  assert.match(text,/SELF_CHECK/);assert.match(text,/COMMIT/);assert.match(text,/unrelated staged/);assert.match(text,/NEEDS_CONTEXT/);assert.match(text,/root cause/);
 }
});
