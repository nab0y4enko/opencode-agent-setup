import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';
import {DatabaseSync} from 'node:sqlite';
import {analyze, render, loadTree, findRoot, listRoots, weighted, openDatabase} from '../src/usage.js';

const cloud={providerID:'openai',id:'gpt-6.1-sol',variant:'high'};
const local={providerID:'omlx',id:'qwen-3.8-nf-splash'};
let seq=0;
function message(sessionID,agent,model,tokens,extra={}){
 seq++;
 return {id:`msg_${seq}`,sessionID,agent,model,created:1000+seq*1000,completed:1500+seq*1000,finish:'tool-calls',cost:0,compaction:false,dispatches:[],
  tokens:{input:0,output:0,reasoning:0,cacheRead:0,cacheWrite:0,...tokens},...extra};
}
function session(id,agent,model,parentID=null,extra={}){return {id,parentID,agent,model,directory:'/work',title:`${agent} session`,created:1000,updated:900000,compacting:null,...extra};}
/** Coordinator on OpenAI dispatching a local General worker, then a cloud Build escalation. */
function mixedTree(){
 const sessions=[session('root','orchestrator',{...cloud,variant:'medium'}),session('w1','general',local,'root'),session('b1','build',cloud,'root')];
 const messages=[
  message('root','orchestrator',{...cloud,variant:'medium'},{input:4000,output:600,reasoning:300,cacheRead:20000},{dispatches:[{agent:'general',background:false,sessionID:'w1'}]}),
  message('w1','general',local,{input:30000,output:4000,cacheRead:90000}),
  message('w1','general',local,{input:20000,output:3000,cacheRead:120000}),
  message('root','orchestrator',{...cloud,variant:'medium'},{input:3000,output:500,reasoning:200,cacheRead:26000},{dispatches:[{agent:'build',background:false,sessionID:'b1'}]}),
  message('b1','build',cloud,{input:9000,output:2500,reasoning:1500,cacheRead:40000}),
  message('root','orchestrator',{...cloud,variant:'medium'},{input:1500,output:400,cacheRead:30000},{finish:'stop'}),
 ];
 return {root:sessions[0],sessions,messages};
}

test('weighted tokens discount cache reads and count everything else fully',()=>{
 assert.equal(weighted({input:100,output:50,reasoning:25,cacheRead:1000,cacheWrite:10}),100+50+25+10+100);
});

test('analysis splits totals by provider class, agent and model',()=>{
 const report=analyze(mixedTree());
 assert.equal(report.totals.cloud.raw.input,4000+3000+1500+9000);
 assert.equal(report.totals.local.raw.input,50000);
 assert.equal(report.totals.local.raw.cacheRead,210000);
 assert.equal(report.byAgent.find(a=>a.agent==='general').class,'local');
 assert.equal(report.byAgent.find(a=>a.agent==='orchestrator').turns,3);
 assert.equal(report.byModel.find(m=>m.model==='openai/gpt-6.1-sol').sessions,2);
 assert.equal(report.sessions.find(s=>s.id==='w1').depth,1);
 assert.equal(report.dispatches.length,2);
 const repeated=mixedTree();repeated.messages[3].dispatches.push({...repeated.messages[0].dispatches[0]});
 assert.equal(analyze(repeated).dispatches.length,2,'a dispatch record repeated in a later turn is counted once');
 assert.equal(report.dispatches[1].agent,'build');
 assert.ok(report.shares.cloudWeighted>0&&report.shares.cloudWeighted<1);
});

test('a root whose children came from another dispatch tool still counts as delegation',()=>{
 const tree=mixedTree();for(const m of tree.messages)m.dispatches=[];
 const report=analyze(tree);assert.equal(report.dispatches.length,0);assert.match(report.grade.reasons[0],/cloud share/);
});

test('cloud share and grade reflect how much of the work stayed local',()=>{
 const good=analyze(mixedTree());
 const tree=mixedTree();for(const m of tree.messages)if(m.sessionID==='w1')m.model=cloud;tree.sessions[1].model=cloud;
 const bad=analyze(tree);
 assert.ok(bad.shares.cloudWeighted>good.shares.cloudWeighted);
 assert.ok(['A','B','C','D'].includes(good.grade.letter));
 assert.ok(bad.grade.letter>good.grade.letter,`${bad.grade.letter} should be worse than ${good.grade.letter}`);
 assert.match(bad.grade.reasons.join(' '),/cloud/i);
});

test('workers that ran on cloud models are the first routing suggestion with a token estimate',()=>{
 const tree=mixedTree();for(const m of tree.messages)if(m.sessionID==='w1')m.model=cloud;tree.sessions[1].model=cloud;
 const finding=analyze(tree).findings.find(f=>f.id==='cloud-worker-routing');
 assert.ok(finding);assert.equal(finding.severity,'high');assert.match(finding.detail,/general/);
 assert.equal(finding.savingWeighted,weighted({input:50000,output:7000,reasoning:0,cacheRead:210000,cacheWrite:0}));
 assert.equal(analyze(mixedTree()).findings.some(f=>f.id==='cloud-worker-routing'),false);
});

test('coordination overhead is flagged when the coordinator spends more than the workers',()=>{
 const tree=mixedTree();for(const m of tree.messages)if(m.sessionID==='root')m.tokens.input*=40;
 const finding=analyze(tree).findings.find(f=>f.id==='coordination-overhead');
 assert.ok(finding);assert.match(finding.suggestion,/Build directly|smaller/i);
 assert.equal(analyze(mixedTree()).findings.some(f=>f.id==='coordination-overhead'),false);
});

test('escalations, background dispatches and nested delegation are reported',()=>{
 const tree=mixedTree();
 tree.messages[0].dispatches[0].background=true;
 tree.sessions.push(session('w1child','explore',local,'w1'));tree.messages.push(message('w1child','explore',local,{input:100,output:10}));
 tree.messages[1].dispatches=[{agent:'explore',background:false,sessionID:'w1child'}];
 const report=analyze(tree);
 assert.equal(report.escalations.length,1);assert.equal(report.escalations[0].from,'w1');assert.equal(report.escalations[0].to,'b1');
 assert.ok(report.findings.some(f=>f.id==='escalation'));
 const background=report.findings.find(f=>f.id==='background-dispatch');assert.ok(background);assert.equal(background.severity,'high');
 const nested=report.findings.find(f=>f.id==='nested-delegation');assert.ok(nested);assert.match(nested.detail,/general/);
});

test('reasoning share, compaction on cloud, step budget and errors each produce a finding',()=>{
 const tree=mixedTree();
 for(const m of tree.messages)if(m.sessionID==='root'){m.tokens.reasoning=m.tokens.output*4;}
 tree.messages.push(message('root','compaction',cloud,{input:50000,output:2000},{compaction:true}));
 for(let i=0;i<25;i++)tree.messages.push(message('w1','general',local,{input:100,output:10}));
 tree.messages.push(message('b1','build',cloud,{input:10,output:0},{finish:'error'}));
 const ids=analyze(tree,{steps:{general:24}}).findings.map(f=>f.id);
 for(const id of ['reasoning-heavy','compaction-on-cloud','step-budget','errors'])assert.ok(ids.includes(id),id);
});

test('cost uses recorded message cost, then a pricing table, and flags unpriced cloud models',()=>{
 const tree=mixedTree();tree.messages[4].cost=0.25;
 const priced=analyze(tree,{pricing:{'openai/gpt-6.1-sol':{input:2,output:8,cacheRead:0.2,reasoning:8}}});
 const build=priced.sessions.find(s=>s.id==='b1');assert.equal(build.cost,0.25);
 const root=priced.sessions.find(s=>s.id==='root');
 assert.ok(Math.abs(root.cost-((8500*2+1500*8+500*8+76000*0.2)/1e6))<1e-9);
 assert.equal(priced.findings.some(f=>f.id==='unpriced-models'),false);
 const unpriced=analyze(mixedTree());assert.ok(unpriced.findings.some(f=>f.id==='unpriced-models'));assert.equal(unpriced.totals.cloud.cost,null);
});

test('rendered report lists sessions, totals, findings and grade without secrets',()=>{
 const text=render(analyze(mixedTree()));
 assert.match(text,/orchestrator/);assert.match(text,/omlx\/qwen-3.8-nf-splash/);assert.match(text,/Cloud/);assert.match(text,/Local/);
 assert.match(text,/Grade [A-D]/);assert.match(text,/Findings/);assert.match(text,/weighted/i);
});

function fixtureDatabase(){
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'usage db '));const file=path.join(dir,'opencode.db');const db=new DatabaseSync(file);
 db.exec(`CREATE TABLE session_v2 (id text primary key, project_id text not null, parent_id text, slug text not null, directory text not null, title text, version text not null, cost real default 0 not null, tokens_input integer default 0 not null, tokens_output integer default 0 not null, tokens_reasoning integer default 0 not null, tokens_cache_read integer default 0 not null, tokens_cache_write integer default 0 not null, agent text, model text, time_created integer not null, time_updated integer not null, time_compacting integer);
 CREATE TABLE session_message (id text primary key, session_id text not null, type text not null, seq integer not null, time_created integer not null, time_updated integer not null, data text not null);`);
 const s=db.prepare('insert into session_v2 (id,project_id,parent_id,slug,directory,title,version,agent,model,time_created,time_updated) values (?,?,?,?,?,?,?,?,?,?,?)');
 s.run('root','p',null,'root','/work','Fix clamp','2.1.2','orchestrator',JSON.stringify({id:'gpt-6.1-sol',providerID:'openai',variant:'medium'}),1000,9000);
 s.run('child','p','root','child','/work','general','2.1.2','general',JSON.stringify(local),2000,8000);
 s.run('grandchild','p','child','grandchild','/work','explore','2.1.2','explore',JSON.stringify(local),2500,7000);
 s.run('other','p',null,'other','/elsewhere','Other project','2.1.2','build',JSON.stringify(cloud),500,99999);
 s.run('older','p',null,'older','/work','Older root','2.1.2','build',JSON.stringify(cloud),100,200);
 const m=db.prepare('insert into session_message (id,session_id,type,seq,time_created,time_updated,data) values (?,?,?,?,?,?,?)');
 m.run('u1','root','user',0,1000,1000,JSON.stringify({text:'Fix clamp',metadata:{}}));
 m.run('a1','root','assistant',1,1100,1200,JSON.stringify({agent:'orchestrator',model:{id:'gpt-6.1-sol',providerID:'openai',variant:'medium'},time:{created:1100,completed:1200},finish:'tool-calls',cost:0,tokens:{input:500,output:60,reasoning:20,cache:{read:3000,write:0}},content:[{type:'tool',name:'subagent',state:{status:'completed',input:{agent:'general',background:false,prompt:'secret brief with apiKey=SENTINEL'},metadata:{sessionID:'child'}}}]}));
 m.run('a2','child','assistant',1,2100,2200,JSON.stringify({agent:'general',model:local,time:{created:2100,completed:2200},finish:'stop',cost:0,tokens:{input:7000,output:900,reasoning:0,cache:{read:1000,write:0}},content:[{type:'tool',name:'subagent',state:{status:'completed',input:{agent:'explore',background:false},metadata:{sessionID:'grandchild'}}}]}));
 m.run('a3','grandchild','assistant',1,2600,2700,JSON.stringify({agent:'explore',model:local,time:{created:2600,completed:2700},finish:'stop',cost:0,tokens:{input:400,output:30,reasoning:0,cache:{read:0,write:0}}}));
 m.run('a4','root','assistant',2,3000,3100,JSON.stringify({agent:'compaction',model:{id:'gpt-6.1-sol',providerID:'openai',variant:'medium'},time:{created:3000,completed:3100},finish:'stop',summary:true,cost:0,tokens:{input:9000,output:300,reasoning:0,cache:{read:0,write:0}}}));
 m.run('i1','root','idle',3,3200,3200,JSON.stringify({time:{created:3200},outcome:'succeeded'}));
 db.close();return file;
}

test('database loader returns the whole session tree, dispatches and compaction markers',()=>{
 const file=fixtureDatabase();const db=openDatabase(file);
 const tree=loadTree(db,'root');
 assert.deepEqual(tree.sessions.map(s=>s.id),['root','child','grandchild']);
 assert.equal(tree.messages.length,4);
 assert.equal(tree.messages[0].dispatches[0].sessionID,'child');
 assert.equal(JSON.stringify(tree).includes('SENTINEL'),false);
 assert.equal(tree.messages.find(m=>m.id==='a4').compaction,true);
 assert.equal(findRoot(db,{directory:'/work'}).id,'root');
 assert.equal(findRoot(db,{}).id,'other');
 assert.deepEqual(listRoots(db,{directory:'/work',limit:5}).map(s=>s.id),['root','older']);
 assert.throws(()=>loadTree(db,'missing'),/not found/);
 db.close();
});

test('usage command renders a report from an explicit database and session, and emits JSON',()=>{
 const file=fixtureDatabase();const cli=path.resolve('bin/setup.js');
 const text=spawnSync(process.execPath,[cli,'usage','--db',file,'--session','root'],{encoding:'utf8'});
 assert.equal(text.status,0,text.stderr);assert.match(text.stdout,/Grade/);assert.match(text.stdout,/compaction/i);assert.equal(text.stdout.includes('SENTINEL'),false);
 const json=spawnSync(process.execPath,[cli,'usage','--db',file,'--directory','/work','--json'],{encoding:'utf8'});
 assert.equal(json.status,0,json.stderr);const report=JSON.parse(json.stdout);assert.equal(report.root.id,'root');assert.ok(report.findings.length);
 const missing=spawnSync(process.execPath,[cli,'usage','--db',file,'--directory','/nowhere'],{encoding:'utf8'});
 assert.equal(missing.status,1);assert.match(missing.stderr,/No session/);
 const list=spawnSync(process.execPath,[cli,'usage','--db',file,'--directory','/work','--list'],{encoding:'utf8'});
 assert.equal(list.status,0);assert.match(list.stdout,/root/);assert.match(list.stdout,/older/);
});

test('compare mode prints both sessions side by side',()=>{
 const file=fixtureDatabase();const cli=path.resolve('bin/setup.js');
 const run=spawnSync(process.execPath,[cli,'usage','--db',file,'--session','root','--compare','older'],{encoding:'utf8'});
 assert.equal(run.status,0,run.stderr);assert.match(run.stdout,/root/);assert.match(run.stdout,/older/);assert.match(run.stdout,/Comparison/);
});

import {treeFrom, hierarchy, summaryLine, toMillis} from '../src/usage-analysis.js';
test('SDK-shaped sessions and messages build the same tree the database loader does',()=>{
 const at=ms=>({epochMillis:ms});
 const sessions=[
  {id:'root',projectID:'p',agent:'orchestrator',model:{providerID:'openai',modelID:'gpt-6.1-sol',variant:'medium'},title:'Fix clamp',location:{directory:'/work'},time:{created:at(1000),updated:at(9000)},tokens:{input:1,output:1,reasoning:0,cache:{read:0,write:0}},cost:0},
  {id:'child',parentID:'root',projectID:'p',agent:'general',model:{providerID:'omlx',modelID:'qwen'},title:'general',location:{directory:'/work'},time:{created:at(2000),updated:at(8000)},tokens:{input:1,output:1,reasoning:0,cache:{read:0,write:0}},cost:0},
  {id:'other',projectID:'p',agent:'build',title:'Other',location:{directory:'/x'},time:{created:at(1),updated:at(2)},tokens:{input:0,output:0,reasoning:0,cache:{read:0,write:0}},cost:0},
 ];
 const messages={
  root:[{id:'u1',type:'user',sessionID:'root',time:{created:at(1000)}},{id:'a1',type:'assistant',sessionID:'root',agent:'orchestrator',model:{providerID:'openai',modelID:'gpt-6.1-sol',variant:'medium'},time:{created:at(1100),completed:at(1200)},finish:'tool-calls',tokens:{input:500,output:60,reasoning:20,cache:{read:3000,write:0}},content:[{type:'tool',id:'c1',name:'subagent',state:{status:'completed',input:{agent:'general',background:false,prompt:'SENTINEL'},metadata:{sessionID:'child'}}}]}],
  child:[{id:'a2',type:'assistant',sessionID:'child',agent:'general',model:{providerID:'omlx',modelID:'qwen'},time:{created:at(2100),completed:at(2200)},finish:'stop',tokens:{input:7000,output:900,reasoning:0,cache:{read:1000,write:0}},content:[]}],
 };
 const tree=treeFrom(sessions,messages,'root');
 assert.deepEqual(tree.sessions.map(s=>s.id),['root','child']);
 assert.equal(tree.messages.length,2);assert.equal(tree.messages[0].dispatches[0].sessionID,'child');assert.equal(tree.messages[0].created,1100);
 assert.equal(JSON.stringify(tree).includes('SENTINEL'),false);
 const report=analyze(tree);
 assert.equal(report.sessions.find(s=>s.id==='child').class,'local');assert.equal(report.sessions.find(s=>s.id==='root').model,'openai/gpt-6.1-sol#medium');
 assert.equal(treeFrom(sessions,id=>messages[id],'missing'),null);
 assert.equal(treeFrom(sessions,id=>messages[id],'root').messages.length,2);
 assert.equal(toMillis(new Date(5)),5);assert.equal(toMillis('1970-01-01T00:00:00.010Z'),10);assert.equal(toMillis(undefined),null);
});

test('hierarchy nests agents, then models, then session instances, largest first',()=>{
 const report=analyze(mixedTree());const h=hierarchy(report);
 assert.deepEqual(h.map(a=>a.agent),['general','orchestrator','build']);
 const general=h[0];assert.equal(general.class,'local');assert.equal(general.models[0].model,'omlx/qwen-3.8-nf-splash');assert.equal(general.models[0].instances[0].id,'w1');
 assert.equal(general.models[0].instances[0].title,'general session');
 assert.equal(h.find(a=>a.agent==='orchestrator').cost,null);
 assert.match(summaryLine(report),/Grade [A-D]: cloud \d+% \/ local \d+%/);
});

import {writeSessionReport, COMPLETION_EVENTS} from '../plugin/agent-usage/report.js';
test('session report writer handles root sessions only and writes text, json and latest files',()=>{
 const file=fixtureDatabase();const dir=fs.mkdtempSync(path.join(os.tmpdir(),'usage reports '));
 const result=writeSessionReport('root',{database:file,directory:dir});
 assert.equal(result.written,true);assert.match(result.summary,/Grade/);assert.ok(fs.existsSync(result.files.text));assert.ok(fs.existsSync(result.files.json));
 assert.equal(fs.readFileSync(result.files.latest,'utf8'),fs.readFileSync(result.files.text,'utf8'));
 assert.equal(fs.readFileSync(result.files.text,'utf8').includes('SENTINEL'),false);
 assert.deepEqual(writeSessionReport('child',{database:file,directory:dir}),{skipped:'child session'});
 assert.deepEqual(writeSessionReport('nope',{database:file,directory:dir}),{skipped:'session not found'});
 assert.ok(COMPLETION_EVENTS.has('session.execution.succeeded'));
});

test('database loader accepts an injected driver with a bun:sqlite-like surface',()=>{
 const file=fixtureDatabase();let opened=0;
 const driver=f=>{opened++;const raw=new DatabaseSync(f,{readOnly:true});return {prepare:sql=>{const s=raw.prepare(sql);return {all:(...a)=>s.all(...a),get:(...a)=>s.get(...a)};},close:()=>raw.close()};};
 const db=openDatabase(file,{driver});assert.equal(opened,1);assert.equal(loadTree(db,'root').sessions.length,3);db.close();
});

test('plugin install links the plugin directory into the OpenCode plugins folder and status/uninstall reverse it',()=>{
 const home=fs.mkdtempSync(path.join(os.tmpdir(),'plugin home '));const cli=path.resolve('bin/setup.js');const env={...process.env,XDG_CONFIG_HOME:home};
 const link=path.join(home,'opencode','plugins','agent-usage');
 let run=spawnSync(process.execPath,[cli,'plugin','status'],{encoding:'utf8',env});assert.equal(run.status,0,run.stderr);assert.match(run.stdout,/not installed/);
 run=spawnSync(process.execPath,[cli,'plugin','install'],{encoding:'utf8',env});assert.equal(run.status,0,run.stderr);
 assert.ok(fs.lstatSync(link).isSymbolicLink());assert.equal(fs.realpathSync(link),fs.realpathSync(path.resolve('plugin/agent-usage')));
 assert.ok(fs.existsSync(path.join(link,'server.js')));assert.ok(fs.existsSync(path.join(link,'tui.tsx')));
 run=spawnSync(process.execPath,[cli,'plugin','install'],{encoding:'utf8',env});assert.equal(run.status,0);assert.match(run.stdout,/already/);
 run=spawnSync(process.execPath,[cli,'plugin','status'],{encoding:'utf8',env});assert.match(run.stdout,/installed/);
 fs.unlinkSync(link);fs.mkdirSync(link);fs.writeFileSync(path.join(link,'server.js'),'// someone else');
 run=spawnSync(process.execPath,[cli,'plugin','install'],{encoding:'utf8',env});assert.equal(run.status,1);assert.match(run.stderr,/exists/);
 run=spawnSync(process.execPath,[cli,'plugin','uninstall'],{encoding:'utf8',env});assert.equal(run.status,1);assert.match(run.stderr,/not .*link|not installed by/i);assert.ok(fs.existsSync(path.join(link,'server.js')));
 fs.rmSync(link,{recursive:true});spawnSync(process.execPath,[cli,'plugin','install'],{env});
 run=spawnSync(process.execPath,[cli,'plugin','uninstall'],{encoding:'utf8',env});assert.equal(run.status,0,run.stderr);assert.equal(fs.existsSync(link),false);
 const project=fs.mkdtempSync(path.join(os.tmpdir(),'plugin project '));
 run=spawnSync(process.execPath,[cli,'plugin','install','--project'],{encoding:'utf8',env,cwd:project});assert.equal(run.status,0,run.stderr);
 assert.ok(fs.lstatSync(path.join(project,'.opencode','plugins','agent-usage')).isSymbolicLink());
});
