import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
function run(obj){const dir=fs.mkdtempSync(path.join(os.tmpdir(),'stage-report-'));const file=path.join(dir,'result.json');fs.writeFileSync(file,JSON.stringify(obj));return spawnSync('python3',['scripts/verify-stage-result.py',file],{encoding:'utf8'});}
const good={opencode_exit:0,independent_test_exit:0,tests:'Ran 4 tests in 0.001s\nOK',commits:[{sha:'1',files:['fixture.py']},{sha:'2',files:['fixture.py','test_fixture.py']}],status:'',dispatches:[{agent:'general',background:false,model:{providerID:'omlx',id:'qwen-3.8-nf-splash'}},{agent:'build',background:false,model:{providerID:'openai',id:'gpt-6.1-sol',variant:'high'}},{agent:'cloud-reviewer',background:false,model:{providerID:'openai',id:'gpt-6.1-sol',variant:'high'}}],review:'VERDICT: PASS',usage:{byAgent:[{agent:'orchestrator',class:'cloud'},{agent:'general',class:'local'},{agent:'build',class:'cloud'},{agent:'cloud-reviewer',class:'cloud'}],totals:{local:{weighted:5000},cloud:{weighted:3000}},shares:{cloudWeighted:0.375},dispatches:[{background:false},{background:false},{background:false}]}};
test('stage verifier accepts observed model routing, two owned commits and independent tests',()=>{const p=run(good);assert.equal(p.status,0,p.stderr+p.stdout);});
test('stage verifier rejects successful CLI exits with missing checkpoint or wrong cloud route',()=>{assert.equal(run({...good,commits:good.commits.slice(0,1)}).status,1);assert.equal(run({...good,dispatches:good.dispatches.map(d=>({...d,model:{providerID:'omlx',id:'qwen'}}))}).status,1);});
test('stage verifier rejects failures, source dirtiness or inconclusive review',()=>{assert.equal(run({...good,independent_test_exit:1}).status,1);assert.equal(run({...good,status:' M fixture.py'}).status,1);assert.equal(run({...good,review:'NEEDS_CONTEXT'}).status,1);});
test('stage verifier accepts an actual Markdown PASS verdict inside native subagent output',()=>{assert.equal(run({...good,review:'<subagent>\n**PASS**\nFindings: none.\n</subagent>'}).status,0);});
test('stage verifier requires a usage report with local General tokens and foreground dispatches',()=>{
 const {usage,...withoutUsage}=good;assert.equal(run(withoutUsage).status,1);
 assert.equal(run({...good,usage:{...usage,byAgent:usage.byAgent.map(a=>({...a,class:'cloud'})),shares:{cloudWeighted:1},totals:{local:{weighted:0},cloud:{weighted:1}}}}).status,1);
 assert.equal(run({...good,usage:{...usage,dispatches:[{background:true}]}}).status,1);
});
