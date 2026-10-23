import test from 'node:test';
import assert from 'node:assert/strict';
import {dashboard} from '../plugin/agent-usage/presentation.js';
import {treeFrom} from '../src/usage-analysis.js';
const cloud={providerID:'openai',id:'sol',variant:'medium'},local={providerID:'omlx',id:'qwen'};
function fixture(){
 const sessions=[{id:'root',agent:'orchestrator',model:cloud,time:{created:1000,updated:900000}},{id:'worker',parentID:'root',agent:'general',model:local,time:{created:2000}}];
 const messages={root:[{id:'plan',type:'assistant',agent:'orchestrator',model:cloud,time:{created:1000,completed:3000},tokens:{input:100,output:20,reasoning:4,cache:{read:50,write:2}},cost:0.01},{id:'review',type:'assistant',agent:'orchestrator',model:cloud,time:{created:9000,completed:11000},tokens:{input:80,output:10},content:[{type:'text',text:'Reviewed tests.\n**VERDICT: PASS**'}]}],worker:[{id:'work',type:'assistant',agent:'general',model:local,time:{created:2000,completed:10000},tokens:{input:200,output:70,reasoning:30,cache:{read:600}},content:[{type:'text',text:'VERDICT: PASS. SENTINEL_PRIVATE_DETAILS'}]}]};
 return {sessions,messages,tree:()=>treeFrom(sessions,messages,'root')};
}
test('widget preserves raw categories and measured span without adding parallel session durations or view time',()=>{
 const f=fixture(),view=dashboard(f.tree(),{now:999999});
 assert.deepEqual(view.cloud.tokens,{input:180,output:30,reasoning:4,cacheRead:50,cacheWrite:2});
 assert.equal(view.local.tokens.input,200);assert.equal(view.elapsedSeconds,10);
 assert.equal(view.cloud.elapsedSeconds,4);assert.equal(view.local.elapsedSeconds,8);
 assert.equal(view.cloud.cost.value,null);assert.equal(view.cloud.cost.kind,'unavailable');
 assert.equal(view.local.cost.kind,'local');assert.match(view.local.cost.label,/operating.*unmeasured/i);
});
test('widget distinguishes recorded and estimated costs; incomplete pricing stays unavailable',()=>{
 const f=fixture();f.messages.root.pop();
 assert.equal(dashboard(f.tree()).cloud.cost.kind,'recorded');
 f.messages.root[0].cost=0;
 assert.equal(dashboard(f.tree(),{pricing:{'openai/sol':{input:2,output:8}}}).cloud.cost.kind,'estimated');
 assert.equal(dashboard(f.tree(),{pricing:{'openai/sol':{input:2}}}).cloud.cost.kind,'unavailable');
});
test('active models use the latest identity in running sessions; selected next does not rewrite model history',()=>{
 const f=fixture();f.messages.worker.push({...f.messages.worker[0],id:'switch',agent:'build',model:cloud,time:{created:12000}});
 const selected={agent:'general',model:local};const v=dashboard(f.tree(),{statuses:{worker:'running'},selected,now:16000});
 assert.equal(v.status,'running');assert.equal(v.elapsedSeconds,15);
 assert.equal(v.active.length,1);assert.equal(v.active[0].model,'openai/sol#medium');
 assert.equal(v.active[0].agent,'build');assert.equal(v.selected.model,'omlx/qwen');
 assert.ok(v.history.some(h=>h.model==='omlx/qwen'&&h.agent==='general'));
 assert.equal(v.local.elapsedSeconds,8);assert.equal(v.cloud.elapsedSeconds,8);
});
test('review exposes explicit coordinator verdict and never promotes worker self-check to independent review',()=>{
 const f=fixture(),v=dashboard(f.tree());
 assert.equal(v.review.verdict,'PASS');assert.equal(v.review.kind,'Coordinator review');
 assert.equal(v.review.model,'openai/sol#medium');assert.equal(v.review.independent,false);
 assert.equal(v.review.independentVerdict,null);assert.equal(v.review.sourceMessageID,'review');
 assert.equal(JSON.stringify(f.tree()).includes('SENTINEL_PRIVATE_DETAILS'),false);
 f.messages.root[1].summary=true;assert.equal(dashboard(f.tree()).review.verdict,null);delete f.messages.root[1].summary;
 f.messages.root[1].content=[{type:'text',text:'No explicit final review verdict.'}];
 assert.equal(dashboard(f.tree()).review.verdict,null);
});
test('independent review shows its own verdict and later coordinator corrections supersede older PASS',()=>{
 const f=fixture();f.sessions.push({id:'reviewer',parentID:'root',agent:'cloud-reviewer',model:cloud});
 f.messages.reviewer=[{id:'independent',type:'assistant',agent:'cloud-reviewer',model:cloud,time:{created:8000,completed:8500},content:[{type:'text',text:'VERDICT: CHANGES_REQUIRED'}]}];
 let v=dashboard(f.tree());assert.equal(v.review.independent,true);assert.equal(v.review.independentVerdict,'CHANGES_REQUIRED');
 f.messages.root.push({...f.messages.root[1],id:'correction',time:{created:13000,completed:14000},content:[{type:'text',text:'VERDICT: NEEDS_CONTEXT'}]});
 v=dashboard(f.tree());assert.equal(v.review.verdict,'NEEDS_CONTEXT');assert.equal(v.review.sourceMessageID,'correction');
 f.messages.reviewer[0].model=local;v=dashboard(f.tree());assert.equal(v.review.independent,false);
});
test('quoted verdicts, tool output and unterminated responses do not become review approval',()=>{
 const f=fixture();
 for(const content of [[{type:'text',text:'The worker wrote VERDICT: PASS in its log.'}],[{type:'tool',name:'read',state:{output:'VERDICT: PASS'}}],[{type:'text',text:'```\nVERDICT: PASS\n```'}]]){
  f.messages.root[1].content=content;assert.equal(dashboard(f.tree()).review.verdict,null);
 }
 f.messages.root[1].content=[{type:'text',text:'VERDICT: PASS'}];delete f.messages.root[1].time.completed;
 assert.equal(dashboard(f.tree(),{statuses:{root:'running'}}).review.verdict,null);
});
test('idle models are historical and missing timestamps never turn into an epoch-long timer',()=>{
 const f=fixture();const v=dashboard(f.tree());assert.equal(v.active.length,0);assert.equal(v.selected,null);
 const empty=dashboard(treeFrom([{id:'empty'}],{},'empty'),{statuses:{empty:'running'},now:Date.now()});
 assert.equal(empty.elapsedSeconds,0);assert.equal(empty.review.verdict,null);
});
test('missing prices expose known partial charges and unpriced turns',()=>{
 const f=fixture(),view=dashboard(f.tree());assert.equal(view.cloud.cost.recordedValue,0.01);assert.equal(view.cloud.cost.unpricedTurns,1);
});
test('independent reviewer activity without a verdict is shown without inventing approval',()=>{
 const f=fixture();f.sessions.push({id:'reviewer',parentID:'root',agent:'cloud-reviewer',model:cloud});
 f.messages.reviewer=[{id:'reviewing',type:'assistant',agent:'cloud-reviewer',model:cloud,time:{created:12000},content:[{type:'text',text:'Checking evidence now.'}]}];
 const view=dashboard(f.tree(),{statuses:{reviewer:'running'},now:14000});
 assert.equal(view.review.independent,true);assert.equal(view.review.independentVerdict,null);assert.equal(view.review.independentStatus,'running');
 assert.equal(view.review.previous,true);
});
test('completed session span includes its start and final idle boundary, never the last viewed time',()=>{
 const f=fixture();f.sessions[0].time={created:500,updated:9999999,idle:12000};f.sessions[0].outcome='succeeded';
 const v=dashboard(f.tree(),{now:20000000});assert.equal(v.elapsedSeconds,12);assert.equal(v.status,'succeeded');
});
test('a missing agent label cannot move known cloud usage into unknown provider totals',()=>{
 const f=fixture();delete f.messages.root[0].agent;
 const v=dashboard(f.tree());assert.equal(v.cloud.tokens.input,180);assert.equal(v.unknown.tokens.input,0);assert.equal(v.cloud.elapsedSeconds,4);assert.equal(v.history.find(h=>h.agent==='unknown').class,'cloud');
});
test('fences split across text parts stay quoted; a verdict predating later work is labeled previous',()=>{
 const f=fixture();f.messages.root[1].content=[{type:'text',text:'```\nExample:'},{type:'text',text:'VERDICT: PASS\n```'}];
 assert.equal(dashboard(f.tree()).review.verdict,null);
 f.messages.root[1].content=[{type:'text',text:'VERDICT: PASS'}];
 f.messages.worker.push({...f.messages.worker[0],id:'later-work',time:{created:13000,completed:14000}});
 assert.equal(dashboard(f.tree()).review.previous,true);
});
test('model history keeps the newest use and parallel cloud intervals are counted once',()=>{
 const f=fixture(),v=dashboard(f.tree());
 assert.equal(v.history.find(h=>h.agent==='orchestrator').lastUsed,11000);
 f.messages.worker[0].model=cloud;
 assert.equal(dashboard(f.tree()).cloud.elapsedSeconds,10);
});
test('different coordinator and independent verdicts remain visible with separate evidence sources',()=>{
 const f=fixture();f.sessions.push({id:'reviewer',parentID:'root',agent:'cloud-reviewer',model:cloud});
 f.messages.reviewer=[{id:'independent',type:'assistant',agent:'cloud-reviewer',model:cloud,time:{created:8000,completed:8500},content:[{type:'text',text:'VERDICT: CHANGES_REQUIRED'}]}];
 const v=dashboard(f.tree());assert.equal(v.review.conflict,true);assert.equal(v.review.independentSourceSessionID,'reviewer');assert.equal(v.review.independentSourceMessageID,'independent');
});
test('a new run after a model switch waits for an actual model record and does not extend old usage',()=>{
 const f=fixture();f.sessions[1].model=cloud;
 const v=dashboard(f.tree(),{statuses:{worker:'running'},now:16000,selected:{model:cloud}});
 assert.equal(v.active[0].model,'unknown');assert.equal(v.active[0].state,'awaiting-model');
 assert.equal(v.local.elapsedSeconds,8);assert.equal(v.history.find(h=>h.agent==='general').active,false);
});
test('indented code and shorter nested fences cannot supply a review verdict',()=>{
 const f=fixture();
 for(const text of ['    VERDICT: PASS','\tVERDICT: PASS','````markdown\n```\nVERDICT: PASS\n```\n````']){
  f.messages.root[1].content=[{type:'text',text}];assert.equal(dashboard(f.tree()).review.verdict,null);
 }
 f.messages.root[1].content=[{type:'text',text:'````markdown\n```\nVERDICT: PASS\n```\n````\nVERDICT: CHANGES_REQUIRED'}];
 assert.equal(dashboard(f.tree()).review.verdict,'CHANGES_REQUIRED');
});
