import test from 'node:test';
import assert from 'node:assert/strict';
import {analyze, hierarchy, normalizeMessage, render, summaryLine, treeFrom} from '../src/usage-analysis.js';
const cloud={providerID:'openai',id:'gpt'};
const local={providerID:'omlx',id:'qwen'};
const root={id:'r',parentID:null,agent:'build',model:local,title:'Task',directory:'/work',created:0};
const msg=(agent,model,input,extra={})=>normalizeMessage('r',{type:'assistant',agent,model,tokens:{input},time:{created:1,completed:2},...extra});
const tree=messages=>({root,sessions:[root],messages});

test('model and agent switches retain message identities, hierarchy and individual prices',()=>{
 const report=analyze(tree([msg('build',cloud,10000),msg('general',local,100)]),{pricing:{'openai/gpt':{input:2,output:8}}});
 assert.equal(report.totals.cloud.raw.input,10000);
 assert.equal(report.totals.local.raw.input,100);
 assert.equal(report.totals.all.cost,0.02);
 assert.equal(report.sessions.length,1);
 assert.equal(report.sessions[0].agent,'mixed');assert.equal(report.sessions[0].model,'mixed');assert.equal(report.sessions[0].class,'mixed');
 assert.equal(report.breakdown.length,2);
 assert.equal(report.byAgent.find(a=>a.agent==='build').raw.input,10000);
 const h=hierarchy(report);assert.equal(h.find(a=>a.agent==='build').models[0].model,'openai/gpt');
 assert.equal(h.find(a=>a.agent==='general').models[0].instances[0].tokens.input,100);
});

test('partial recorded costs do not hide unpriced messages and available prices fill the gap',()=>{
 const data=tree([msg('build',cloud,1000,{cost:0.25}),msg('build',cloud,2000)]);
 const unknown=analyze(data);assert.equal(unknown.totals.all.cost,null);assert.ok(unknown.findings.some(f=>f.id==='unpriced-models'));
 const priced=analyze(data,{pricing:{'openai/gpt':{input:2,output:8}}});assert.equal(priced.totals.all.cost,0.254);
});

test('agent groups used with multiple model classes explicitly expose mixed class and distinct sessions',()=>{
 const report=analyze(tree([msg('general',cloud,1000),msg('general',local,2000)]));
 assert.equal(report.byAgent[0].class,'mixed');assert.equal(report.byAgent[0].sessions,1);
 assert.equal(hierarchy(report)[0].class,'mixed');assert.equal(hierarchy(report)[0].sessions,1);
 assert.equal(report.findings.find(f=>f.id==='cloud-worker-routing').observedWeighted,1000);
});

test('native compaction and tokenless error/retry records survive SDK normalization',()=>{
 const data=treeFrom([root],{r:[{id:'c',type:'compaction',model:cloud,tokens:{input:25}},
 {id:'e',type:'assistant',error:{name:'APIError',data:{message:'SENTINEL'}}},
 {id:'s',type:'assistant',status:{type:'error',error:{message:'SENTINEL'}}},
 {id:'t',type:'assistant',content:[{type:'retry',error:{message:'SENTINEL'},attempt:1}]}]},'r');
 assert.equal(data.messages.length,4);
 assert.equal(data.messages[0].agent,'compaction');assert.equal(data.messages[0].compaction,true);
 assert.equal(JSON.stringify(data).includes('SENTINEL'),false);
 const report=analyze(data);assert.equal(report.sessions[0].compactions,1);assert.equal(report.sessions[0].errors,3);
 assert.ok(report.findings.some(f=>f.id==='compaction-on-cloud'));
});

test('provider name prefixes cannot silently classify unknown providers as local and free',()=>{
 const report=analyze(tree([msg('build',{providerID:'local-cloud-hosted',id:'model'},1000)]));
 assert.equal(report.sessions[0].class,'unknown');assert.equal(report.totals.unknown.raw.input,1000);assert.equal(report.totals.all.cost,null);
 const explicit=analyze(tree([msg('build',{providerID:'my-provider',id:'model'},1000)]),{localProviders:['my-provider']});assert.equal(explicit.totals.local.raw.input,1000);
});

test('routing status describes usage without rewarding extra local tokens or claiming outcome',()=>{
 const a=analyze(tree([msg('build',cloud,10000),msg('general',local,100)]));
 const b=analyze(tree([msg('build',cloud,10000),msg('general',local,1000000)]));
 assert.equal(a.routing.status,'mixed');assert.equal(a.routing.status,b.routing.status);
 assert.equal(a.routing.label,b.routing.label);
 assert.doesNotMatch(render(a)+summaryLine(a),/Grade [A-D]|delegation is not paying off|cost more than it saved|inefficient|failed local attempt|saving/i);
});

test('General followed by Build is a possible handoff and does not infer failure',()=>{
 const data=tree([msg('build',cloud,100,{content:[{type:'tool',name:'subagent',state:{input:{agent:'general'},metadata:{sessionID:'g'}}},{type:'tool',name:'subagent',state:{input:{agent:'build'},metadata:{sessionID:'b'}}}]})]);
 const report=analyze(data);assert.equal(report.possibleHandoffs.length,1);
 const finding=report.findings.find(f=>f.id==='possible-handoff');assert.ok(finding);assert.match(finding.title,/possible/i);
 assert.doesNotMatch(finding.detail+finding.suggestion,/failed|paid twice|escalated/);
});

test('message cache rounding is conserved through identities, sessions and provider totals',()=>{
 const first=msg('general',local,0,{tokens:{cache:{read:6}}});
 const second=msg('general',local,0,{tokens:{cache:{read:6}}});
 const third=msg('build',cloud,0,{tokens:{cache:{read:6}}});
 const report=analyze(tree([first,second,third]));
 assert.equal(report.totals.all.weighted,3);
 assert.equal(report.sessions[0].weighted,3);
 assert.equal(report.breakdown.reduce((n,b)=>n+b.weighted,0),3);
 assert.equal(report.totals.local.weighted,2);assert.equal(report.totals.cloud.weighted,1);
});

test('legacy user rows without a database type do not become assistant turns',()=>{
 const user={id:'user',role:'user',content:[{type:'text',text:'SENTINEL'}]};
 assert.equal(normalizeMessage('r',user),null);
 const data=treeFrom([root],{r:[user,msg('build',cloud,1)]},'r');
 assert.equal(data.messages.length,1);assert.equal(analyze(data).totals.all.turns,1);
});

test('incomplete pricing cannot turn an unpriced token component into NaN or a partial bill',()=>{
 const report=analyze(tree([msg('build',cloud,100,{tokens:{input:100,output:20}})]),{pricing:{'openai/gpt':{input:2}}});
 assert.equal(report.totals.all.cost,null);
});
