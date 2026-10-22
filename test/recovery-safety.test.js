import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {apply,undo,readTarget} from '../src/store.js';

function fixture(t,original='{}'){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'recovery-safety-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 const file=path.join(dir,'opencode.json'),state=path.join(dir,'state');fs.writeFileSync(file,original);return {file,state};
}
function history(state){return JSON.parse(fs.readFileSync(path.join(state,fs.readdirSync(state)[0]),'utf8'));}
for(const fail of [true,false])test(`undo preserves concurrent editor bytes and recovery history after ${fail?'failed':'successful'} validation`,async t=>{
 const {file,state}=fixture(t);await apply(file,[{path:['agents','build','steps'],value:24}],{state,expected:'{}',validate:async()=>{}});
 const concurrent='{"username":"concurrent editor"}';
 await assert.rejects(undo(file,{state,validate:async()=>{fs.writeFileSync(file,concurrent);if(fail)throw Error('validation rejected');}}),/validation rejected|changed during.*validation/i);
 assert.equal(readTarget(file),concurrent);assert.equal(history(state).length,1);
});
test('undo supplies restored values and removals to native validation',async t=>{
 const original='{"agents":{"build":{"steps":9}}}';const {file,state}=fixture(t,original);
 await apply(file,[{path:['agents','build','steps'],value:24},{path:['agents','build','system'],value:'temporary prompt'}],{state,expected:original,validate:async()=>{}});
 let restored;
 await undo(file,{state,validate:async(_file,changes)=>{restored=changes;}});
 assert.deepEqual(restored,[{path:['agents','build','steps'],value:9,previousValue:24,restoration:true},{path:['agents','build','system'],value:undefined,previousValue:'temporary prompt',restoration:true}]);
});
test('failed undo rolls back only its own unchanged restoration and retains journal',async t=>{
 const {file,state}=fixture(t);await apply(file,[{path:['default_agent'],value:'build'}],{state,expected:'{}',validate:async()=>{}});const applied=readTarget(file);
 await assert.rejects(undo(file,{state,validate:async()=>{throw Error('rejected');}}),/rejected/);
 assert.equal(readTarget(file),applied);assert.equal(history(state).length,1);
});

async function nativeFixture(t,{source={},decodedSource=source,otherSources=[],agents=[{id:'build'}],models=[],present=true}={}){
 const {file}=fixture(t,JSON.stringify(source));if(!present)fs.unlinkSync(file);
 const binary=path.join(path.dirname(file),'mock-opencode');
 const docs=[...otherSources,...(present?[{type:'document',path:file,info:decodedSource}]:[])];
 const outputs={'config.get':docs,'agent.list':agents,'model.list':models};
 fs.writeFileSync(binary,`#!${process.execPath}\nprocess.stdout.write(JSON.stringify((${JSON.stringify(outputs)})[process.argv[3]]));\n`,{mode:0o700});
 const old=process.env.OPENCODE_AGENT_SETUP_BINARY;process.env.OPENCODE_AGENT_SETUP_BINARY=binary;
 let native;try{native=await import(`../src/native.js?fixture=${encodeURIComponent(binary)}`);}finally{if(old===undefined)delete process.env.OPENCODE_AGENT_SETUP_BINARY;else process.env.OPENCODE_AGENT_SETUP_BINARY=old;}
 return {file,validate:native.validateNative};
}
for(const [name,expected,actual] of [
 ['resource-specific grant',[{action:'edit',resource:'*',effect:'deny'}],[{action:'edit',resource:'*',effect:'deny'},{action:'edit',resource:'/tmp/owned',effect:'allow'}]],
 ['action-specific grant',[{action:'*',resource:'*',effect:'deny'}],[{action:'*',resource:'*',effect:'deny'},{action:'custom_tool',resource:'/tmp/owned',effect:'allow'}]],
 ['overlapping glob grant',[{action:'read',resource:'*.env*',effect:'ask'}],[{action:'read',resource:'*.env*',effect:'ask'},{action:'read',resource:'credentials.env',effect:'allow'}]],
])test(`native permissions reject a later effective ${name}`,async t=>{
 const source={agents:{build:{permissions:expected}}};const {file,validate}=await nativeFixture(t,{source,agents:[{id:'build',permissions:actual}]});
 await assert.rejects(validate(file,[{path:['agents','build','permissions'],value:expected}]),/Native validation failed/);
});
test('native permissions accept shadowed grants and deliberate narrower exceptions',async t=>{
 const expected=[{action:'read',resource:'*',effect:'deny'},{action:'read',resource:'*.env',effect:'ask'},{action:'read',resource:'*.env.example',effect:'allow'}];
 const actual=[{action:'*',resource:'*',effect:'allow'},{action:'read',resource:'/tmp/owned',effect:'allow'},...expected];
 const {file,validate}=await nativeFixture(t,{source:{agents:{build:{permissions:expected}}},agents:[{id:'build',permissions:actual}]});
 await validate(file,[{path:['agents','build','permissions'],value:expected}]);
});
test('native undo validation rejects stale effective removed fields',async t=>{
 const {file,validate}=await nativeFixture(t,{agents:[{id:'build',steps:24}]});
 await assert.rejects(validate(file,[{path:['agents','build','steps'],value:undefined,previousValue:24,restoration:true}]),/Native validation failed/);
});
test('native undo validates decoded restored fields',async t=>{
 const {file,validate}=await nativeFixture(t,{source:{agents:{build:{steps:9}}},agents:[{id:'build',steps:24}]});
 await assert.rejects(validate(file,[{path:['agents','build','steps'],value:9,previousValue:24,restoration:true}]),/Native validation failed/);
});
test('native removed prompt may inherit a remaining configuration source',async t=>{
 const otherSources=[{type:'document',path:'/lower-priority/opencode.json',info:{agents:{build:{system:'inherited prompt'}}}}];
 const {file,validate}=await nativeFixture(t,{otherSources,agents:[{id:'build',system:'inherited prompt'}]});
 await validate(file,[{path:['agents','build','system'],value:undefined,previousValue:'temporary prompt',restoration:true}]);
});
test('native removed prompt rejects stale runtime despite an inherited source',async t=>{
 const otherSources=[{type:'document',path:'/lower-priority/opencode.json',info:{agents:{build:{system:'inherited prompt'}}}}];
 const {file,validate}=await nativeFixture(t,{otherSources,agents:[{id:'build',system:'temporary prompt'}]});
 await assert.rejects(validate(file,[{path:['agents','build','system'],value:undefined,previousValue:'temporary prompt',restoration:true}]),/Native validation failed/);
});
test('native undo rejects a custom agent still loaded after its document disappears',async t=>{
 const {file,validate}=await nativeFixture(t,{present:false,agents:[{id:'build'},{id:'orchestrator',mode:'primary'}]});
 await assert.rejects(validate(file,[{path:['agents','orchestrator','mode'],value:undefined,previousValue:'primary',restoration:true}]),/Native validation failed/);
});
test('native undo rejects a stale removed default agent',async t=>{
 const {file,validate}=await nativeFixture(t,{agents:[{id:'orchestrator'},{id:'build'}]});
 await assert.rejects(validate(file,[{path:['default_agent'],value:undefined,previousValue:'orchestrator',restoration:true}]),/Native validation failed/);
});
for(const [name,expected,actual] of [
 ['single character glob',[{action:'edit',resource:'/tmp/?',effect:'deny'}],[{action:'edit',resource:'/tmp/?',effect:'deny'},{action:'edit',resource:'/tmp/a',effect:'allow'}]],
 ['UTF16 path',[{action:'edit',resource:'*',effect:'deny'}],[{action:'edit',resource:'*',effect:'deny'},{action:'edit',resource:'/tmp/😀/owned',effect:'allow'}]],
 ['optional command suffix',[{action:'shell',resource:'git *',effect:'deny'}],[{action:'shell',resource:'git *',effect:'deny'},{action:'shell',resource:'git',effect:'allow'}]],
])test(`native permissions preserve ${name} semantics when detecting later grants`,async t=>{
 const {file,validate}=await nativeFixture(t,{source:{agents:{build:{permissions:expected}}},agents:[{id:'build',permissions:actual}]});
 await assert.rejects(validate(file,[{path:['agents','build','permissions'],value:expected}]),/Native validation failed/);
});
test('native permissions normalize backslash paths before applying later safe overrides',async t=>{
 const expected=[{action:'edit',resource:'*',effect:'deny'}];
 const actual=[...expected,{action:'edit',resource:'\\tmp\\owned',effect:'allow'},{action:'edit',resource:'/tmp/owned',effect:'deny'}];
 const {file,validate}=await nativeFixture(t,{source:{agents:{build:{permissions:expected}}},agents:[{id:'build',permissions:actual}]});
 await validate(file,[{path:['agents','build','permissions'],value:expected}]);
});

test('native undo rejects stale decoded restored default agent',async t=>{
 const {file,validate}=await nativeFixture(t,{source:{default_agent:'build'},decodedSource:{default_agent:'plan'}});
 await assert.rejects(validate(file,[{path:['default_agent'],value:'build',previousValue:'plan',restoration:true}]),/Native validation failed/);
});
test('native undo rejects stale decoded removed provider',async t=>{
 const {file,validate}=await nativeFixture(t,{decodedSource:{providers:{temporary:{models:{}}}}});
 await assert.rejects(validate(file,[{path:['providers','temporary'],value:undefined,previousValue:{models:{}},restoration:true}]),/Native validation failed/);
});

test('native undo accepts a restored whole agent with a decoded model reference',async t=>{
 const source={agents:{build:{steps:9,model:'openai/strong'}}};
 const decodedSource={agents:{build:{model:{providerID:'openai',model:'strong'},steps:9}}};
 const agents=[{id:'build',model:{providerID:'openai',id:'strong'},steps:9}];
 const models=[{providerID:'openai',id:'strong',variants:[]}];
 const {file,validate}=await nativeFixture(t,{source,decodedSource,agents,models});
 await validate(file,[{path:['agents','build'],value:source.agents.build,previousValue:undefined,restoration:true}]);
});
test('native permissions expand home paths for filesystem actions',async t=>{
 const expected=[{action:'edit',resource:'~/private/*',effect:'deny'}];
 const actual=[{action:'*',resource:'*',effect:'allow'},{action:'edit',resource:path.join(os.homedir(),'private/*'),effect:'deny'}];
 const {file,validate}=await nativeFixture(t,{source:{agents:{build:{permissions:expected}}},agents:[{id:'build',permissions:actual}]});
 await validate(file,[{path:['agents','build','permissions'],value:expected}]);
});
test('native undo inherits global permissions when removing an agent policy',async t=>{
 const globalPolicy=[{action:'edit',resource:'*',effect:'deny'}];
 const source={permissions:globalPolicy,agents:{orchestrator:{description:'remaining role'}}};
 const {file,validate}=await nativeFixture(t,{source,agents:[{id:'build'},{id:'orchestrator',description:'remaining role',permissions:globalPolicy}]});
 await validate(file,[{path:['agents','orchestrator','permissions'],value:undefined,previousValue:[{action:'edit',resource:'*',effect:'allow'}],restoration:true}]);
});
test('native undo rebuilds builtin Plan permission paths for the current home',async t=>{
 const baseline=JSON.parse(fs.readFileSync(new URL('../data/builtin-2.1.2.json',import.meta.url),'utf8'));
 const plan=baseline.find(a=>a.id==='plan');const oldHome=process.env.HOME;
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'native-home-'));t.after(()=>fs.rmSync(home,{recursive:true,force:true}));
 process.env.HOME=home;
 try{
  const permissions=plan.permissions.map(r=>r.resource.endsWith('/.opencode/plan/*')?{...r,resource:path.join(home,'.opencode/plan/*')}:r);
  const {file,validate}=await nativeFixture(t,{agents:[{id:'build'},{...plan,permissions}]});
  await validate(file,[{path:['agents','plan','permissions'],value:undefined,previousValue:[{action:'edit',resource:'*',effect:'deny'}],restoration:true}]);
 }finally{if(oldHome===undefined)delete process.env.HOME;else process.env.HOME=oldHome;}
});
function markdownSource(t,id){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'native-agent-markdown-'));t.after(()=>fs.rmSync(dir,{recursive:true,force:true}));
 fs.mkdirSync(path.join(dir,'agents'));fs.writeFileSync(path.join(dir,'agents',`${id}.md`),'---\nmode: primary\n---\nInherited markdown prompt');return {type:'directory',path:dir};
}
test('native undo distinguishes unobservable Markdown inheritance from definite mismatch',async t=>{
 const otherSources=[markdownSource(t,'build')];
 const {file,validate}=await nativeFixture(t,{otherSources,agents:[{id:'build',system:'Inherited markdown prompt'}]});
 await assert.rejects(validate(file,[{path:['agents','build','system'],value:undefined,previousValue:'temporary prompt',restoration:true}]),{code:'NATIVE_RESTORATION_UNVERIFIABLE'});
});
test('unobservable Markdown inheritance never masks a stale restored source field',async t=>{
 const otherSources=[markdownSource(t,'build')];
 const {file,validate}=await nativeFixture(t,{source:{default_agent:'build'},decodedSource:{default_agent:'plan'},otherSources,agents:[{id:'build',system:'Inherited markdown prompt'}]});
 await assert.rejects(validate(file,[{path:['agents','build','system'],value:undefined,previousValue:'temporary prompt',restoration:true},{path:['default_agent'],value:'build',previousValue:'plan',restoration:true}]),error=>error.code!=='NATIVE_RESTORATION_UNVERIFIABLE'&&/Native validation failed/.test(error.message));
});
test('native undo restores a disabled whole agent by checking runtime absence',async t=>{
 const source={agents:{general:{disabled:true,system:'prior prompt',steps:9,model:'unavailable/old'}}};
 const decodedSource={agents:{general:{...source.agents.general,model:{providerID:'unavailable',model:'old'}}}};
 const {file,validate}=await nativeFixture(t,{source,decodedSource});
 await validate(file,[{path:['agents','general'],value:source.agents.general,previousValue:undefined,restoration:true}]);
});
test('native undo respects disabled inherited agents after removing a higher source',async t=>{
 const otherSources=[{type:'document',path:'/lower-priority/opencode.json',info:{agents:{general:{disabled:true,system:'prior prompt'}}}}];
 const {file,validate}=await nativeFixture(t,{otherSources});
 await validate(file,[{path:['agents','general','system'],value:undefined,previousValue:'temporary prompt',restoration:true}]);
});
test('native undo accepts whole-agent request headers with native request defaults',async t=>{
 const source={agents:{general:{request:{headers:{'X-Review':'test'}}}}};
 const agents=[{id:'build'},{id:'general',request:{settings:{},headers:{'X-Review':'test'},body:{}}}];
 const {file,validate}=await nativeFixture(t,{source,agents});
 await validate(file,[{path:['agents','general'],value:source.agents.general,previousValue:undefined,restoration:true}]);
});
test('native undo merges inherited request headers and body maps across source layers',async t=>{
 const otherSources=[{type:'document',path:'/lower/opencode.json',info:{agents:{general:{request:{headers:{'X-Lower':'keep','X-Review':'old'},body:{lower:true,options:{lower:true}}}}}}}];
 const request={headers:{'X-Review':'restored'},body:{options:{restored:true}}};
 const source={agents:{general:{request}}};
 const agents=[{id:'build'},{id:'general',request:{settings:{},headers:{'X-Lower':'keep','X-Review':'restored'},body:{lower:true,options:{restored:true}}}}];
 const {file,validate}=await nativeFixture(t,{source,otherSources,agents});
 await validate(file,[{path:['agents','general','request'],value:request,previousValue:{headers:{'X-Review':'temporary'}},restoration:true}]);
});
test('native undo request removal accepts inherited headers with native defaults',async t=>{
 const otherSources=[{type:'document',path:'/lower/opencode.json',info:{agents:{general:{request:{headers:{'X-Lower':'keep'}}}}}}];
 const agents=[{id:'build'},{id:'general',request:{settings:{},headers:{'X-Lower':'keep'},body:{}}}];
 const {file,validate}=await nativeFixture(t,{otherSources,agents});
 await validate(file,[{path:['agents','general','request'],value:undefined,previousValue:{headers:{'X-Temporary':'remove'}},restoration:true}]);
});
test('native undo request removal rejects stale removed header keys',async t=>{
 const agents=[{id:'build'},{id:'general',request:{settings:{},headers:{'X-Temporary':'stale'},body:{}}}];
 const {file,validate}=await nativeFixture(t,{agents});
 await assert.rejects(validate(file,[{path:['agents','general','request'],value:undefined,previousValue:{headers:{'X-Temporary':'stale'}},restoration:true}]),/Native validation failed/);
});
test('native undo request restoration rejects a stale decoded header value',async t=>{
 const source={agents:{general:{request:{headers:{'X-Review':'restored'}}}}};
 const decodedSource={agents:{general:{request:{headers:{'X-Review':'temporary'}}}}};
 const agents=[{id:'build'},{id:'general',request:{settings:{},headers:{'X-Review':'restored'},body:{}}}];
 const {file,validate}=await nativeFixture(t,{source,decodedSource,agents});
 await assert.rejects(validate(file,[{path:['agents','general'],value:source.agents.general,previousValue:undefined,restoration:true}]),/Native validation failed/);
});
test('native undo identifies unverifiable decoded request and system references without exposing values',async t=>{
 const source={agents:{general:{system:'Prefix {file:./prompt.txt} suffix',request:{headers:{'X-Reference':'{env:REVIEW_REFERENCE}','X-Literal':'restored'}}}}};
 const decodedSource={agents:{general:{system:'Prefix PRIVATE_PROMPT suffix',request:{headers:{'X-Reference':'PRIVATE_HEADER','X-Literal':'restored'}}}}};
 const agents=[{id:'build'},{id:'general',system:decodedSource.agents.general.system,request:{settings:{},headers:decodedSource.agents.general.request.headers,body:{}}}];
 const {file,validate}=await nativeFixture(t,{source,decodedSource,agents});
 await assert.rejects(validate(file,[{path:['agents','general'],value:source.agents.general,restoration:true}]),error=>error.code==='NATIVE_RESTORATION_UNVERIFIABLE'&&/reference/i.test(error.message)&&!error.message.includes('PRIVATE_'));
});
test('native undo reference classification never masks a stale literal header sibling',async t=>{
 const source={agents:{general:{request:{headers:{'X-Reference':'{env:REVIEW_REFERENCE}','X-Literal':'restored'}}}}};
 const decodedSource={agents:{general:{request:{headers:{'X-Reference':'PRIVATE_HEADER','X-Literal':'stale'}}}}};
 const agents=[{id:'build'},{id:'general',request:{settings:{},headers:decodedSource.agents.general.request.headers,body:{}}}];
 const {file,validate}=await nativeFixture(t,{source,decodedSource,agents});
 await assert.rejects(validate(file,[{path:['agents','general'],value:source.agents.general,restoration:true}]),error=>error.code!=='NATIVE_RESTORATION_UNVERIFIABLE'&&/Native validation failed/.test(error.message));
});
test('native undo reference classification rejects stale effective expanded headers',async t=>{
 const source={agents:{general:{request:{headers:{'X-Reference':'{env:REVIEW_REFERENCE}'}}}}};
 const decodedSource={agents:{general:{request:{headers:{'X-Reference':'CURRENT_PRIVATE_HEADER'}}}}};
 const agents=[{id:'build'},{id:'general',request:{settings:{},headers:{'X-Reference':'STALE_PRIVATE_HEADER'},body:{}}}];
 const {file,validate}=await nativeFixture(t,{source,decodedSource,agents});
 await assert.rejects(validate(file,[{path:['agents','general'],value:source.agents.general,restoration:true}]),error=>error.code!=='NATIVE_RESTORATION_UNVERIFIABLE'&&/Native validation failed/.test(error.message));
});
test('native apply keeps strict validation of unresolved source references',async t=>{
 const source={agents:{general:{request:{headers:{'X-Reference':'{env:REVIEW_REFERENCE}'}}}}};
 const decodedSource={agents:{general:{request:{headers:{'X-Reference':'PRIVATE_HEADER'}}}}};
 const agents=[{id:'build'},{id:'general',request:{settings:{},headers:decodedSource.agents.general.request.headers,body:{}}}];
 const {file,validate}=await nativeFixture(t,{source,decodedSource,agents});
 await assert.rejects(validate(file,[{path:['agents','general'],value:source.agents.general}]),error=>error.code!=='NATIVE_RESTORATION_UNVERIFIABLE'&&/Native validation failed/.test(error.message));
});
test('native undo checks decoded model references against the effective model inventory',async t=>{
 const source={agents:{general:{model:'{env:REVIEW_MODEL}'}}};
 const decodedSource={agents:{general:{model:{providerID:'openai',model:'strong'}}}};
 const agents=[{id:'build'},{id:'general',model:{providerID:'openai',id:'strong'}}];
 const models=[{providerID:'openai',id:'strong',variants:[]}];
 const {file,validate}=await nativeFixture(t,{source,decodedSource,agents,models});
 await assert.rejects(validate(file,[{path:['agents','general'],value:source.agents.general,restoration:true}]),{code:'NATIVE_RESTORATION_UNVERIFIABLE'});
});
