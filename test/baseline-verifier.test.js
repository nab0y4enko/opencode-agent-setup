import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {analyze, treeFrom} from '../src/usage-analysis.js';

const root='ses_baseline',model='openai/gpt-6.1-sol#high';
const log=n=>`Ran ${n} tests in 0.001s\n\nOK\n`;
const checkpoint=(sha,count)=>({sha,independent_test_exit:0,tests:log(count),patch:'diff --git a/fixture.py b/fixture.py\n+fixed',artifact_patch:'diff --git a/fixture.py b/fixture.py\n+fixed',artifact_tests:log(count)});
const good={opencode_exit:0,independent_test_exit:0,tests:log(4),commits:[{sha:'1'.repeat(40),files:['fixture.py']},{sha:'2'.repeat(40),files:['fixture.py','test_fixture.py']}],status:'',children:[],events:{count:3,sessionIDs:[root],delegationCalls:[],parseErrors:[]},checkpoints:[checkpoint('1'.repeat(40),3),{...checkpoint('2'.repeat(40),4),regression_exit:1,regression_tests:'FAIL: test_invalid\nAssertionError: ValueError not raised\nRan 4 tests in 0.001s\nFAILED (failures=1)\n',artifact_red_tests:'FAIL: test_invalid\nAssertionError: ValueError not raised\nRan 4 tests in 0.001s\nFAILED (failures=1)\n'}],usage:{root:{id:root,agent:'build',model},sessions:[{id:root,parentID:null,agent:'build',model,class:'cloud',weighted:100,turns:1}],byAgent:[{agent:'build',class:'cloud',weighted:100}],byModel:[{model,class:'cloud',weighted:100}],totals:{all:{weighted:100},cloud:{weighted:100},local:{weighted:0},unknown:{weighted:0}},dispatches:[]}};
good.usage.byModel[0].model=model.split('#')[0];
function run(change={}){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'baseline-verifier-'));
 try {const file=path.join(dir,'result.json');fs.writeFileSync(file,JSON.stringify({...structuredClone(good),...change}));return spawnSync('python3',['scripts/verify-baseline-result.py',file],{encoding:'utf8'});}
 finally {fs.rmSync(dir,{recursive:true,force:true});}
}
function reject(change,message){const result=run(change);assert.equal(result.status,1,result.stderr+result.stdout);assert.match(JSON.parse(result.stdout).failures.join('\n'),message);}

test('baseline verifier accepts two independently replayed checkpoints on the cloud Build route',()=>{const r=run();assert.equal(r.status,0,r.stderr+r.stdout);});
test('baseline verifier accepts the analyzer model grouping while checking variants in actual message usage',()=>{
 const usage=analyze(treeFrom([{id:root,agent:'build',model:{providerID:'openai',id:'gpt-6.1-sol',variant:'high'}}],()=>[{id:'m',type:'assistant',agent:'build',model:{providerID:'openai',id:'gpt-6.1-sol',variant:'high'},tokens:{input:100,output:1},time:{created:1,completed:2}}],root));
 const r=run({usage});assert.equal(r.status,0,r.stderr+r.stdout);
});
test('baseline verifier rejects a successful zero-test or three-test run',()=>{
 reject({tests:log(0)},/four-test/i);reject({tests:log(3)},/four-test/i);
});
test('baseline verifier requires exactly two distinct commits with exact stage scopes and a clean tree',()=>{
 reject({commits:good.commits.slice(0,1)},/two.*commit/i);
 reject({commits:good.commits.map(c=>({...c,sha:'1'.repeat(40)}))},/distinct/i);
 reject({commits:[{...good.commits[0],files:['fixture.py','unrelated.txt']},good.commits[1]]},/stage 1.*files/i);
 reject({commits:[good.commits[0],{...good.commits[1],files:['fixture.py']}]},/stage 2.*files/i);
 reject({status:'?? stray.txt'},/dirty/i);
});
test('baseline verifier detects delegation from children, recorded tool calls, events and usage independently',()=>{
 reject({children:[{id:'child'}]},/child|delegat/i);
 reject({events:{...good.events,delegationCalls:['subagent']}},/delegat/i);
 reject({events:{...good.events,sessionIDs:[root,'child']}},/session/i);
 reject({usage:{...good.usage,dispatches:[{agent:'general'}]}},/delegat/i);
 reject({usage:{...good.usage,sessions:[...good.usage.sessions,{id:'child',parentID:root,agent:'general',class:'local'}]}},/session|delegat/i);
});
test('baseline verifier rejects missing, zero-token, incorrect and mixed actual model usage',()=>{
 reject({usage:null},/usage.*missing/i);
 reject({usage:{...good.usage,root:{...good.usage.root,model:'omlx/qwen'}}},/route/i);
 reject({usage:{...good.usage,totals:{...good.usage.totals,cloud:{weighted:0}}}},/cloud.*tokens/i);
 reject({usage:{...good.usage,breakdown:[{sessionID:root,agent:'build',model:'omlx/qwen',class:'local',weighted:100}]}},/route/i);
 reject({usage:{...good.usage,byModel:[{model:'openai/gpt-other',class:'cloud',weighted:100}]}},/model/i);
});
test('baseline verifier requires complete parseable events from the measured root',()=>{
 reject({events:null},/event/i);
 reject({events:{...good.events,parseErrors:['bad JSON']}},/event/i);
 reject({events:{...good.events,sessionIDs:['different-root']}},/root|session/i);
});
test('baseline verifier requires stage-specific passing test counts and matching patch artifacts',()=>{
 reject({checkpoints:[]},/checkpoint/i);
 reject({checkpoints:[{...good.checkpoints[0],tests:log(4)},good.checkpoints[1]]},/stage 1.*three-test/i);
 reject({checkpoints:[good.checkpoints[0],{...good.checkpoints[1],artifact_patch:''}]},/patch/i);
 reject({checkpoints:[{...good.checkpoints[0],artifact_tests:''},good.checkpoints[1]]},/stage 1.*evidence/i);
 reject({checkpoints:[good.checkpoints[0],{...good.checkpoints[1],regression_exit:0,regression_tests:log(4)}]},/regression/i);
 reject({checkpoints:[good.checkpoints[0],{...good.checkpoints[1],artifact_red_tests:''}]},/failure.*evidence|red.*evidence/i);
});
