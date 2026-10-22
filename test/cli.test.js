import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const cli=path.resolve('bin/setup.js');
test('help is read-only and non-interactive wizard refuses before discovery',()=>{
 const help=spawnSync(process.execPath,[cli,'--help'],{encoding:'utf8'});assert.equal(help.status,0);assert.match(help.stdout,/undo/);assert.match(help.stdout,/ports/);
 const run=spawnSync(process.execPath,[cli],{encoding:'utf8',input:''});assert.equal(run.status,1);assert.match(run.stderr,/terminal/);
});
test('offline preview shows exact additions without creating config',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'patcher cli '));const choices=path.join(dir,'choices.json'),config=path.join(dir,'opencode.json');
 fs.writeFileSync(choices,JSON.stringify([{id:'general',model:'omlx/qwen',prompt:'enhance'}]));
 const run=spawnSync(process.execPath,[cli,'preview','--choices',choices,'--config',config],{encoding:'utf8'});
 assert.equal(run.status,0,run.stderr);assert.match(run.stdout,/\+.*assigned scope/);assert.match(run.stdout,/omlx\/qwen/);assert.ok(!fs.existsSync(config));
});
test('preview masks credentials even in single-line configuration',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'patcher secret '));const choices=path.join(dir,'choices.json'),config=path.join(dir,'opencode.json');
 fs.writeFileSync(config,JSON.stringify({providers:{local:{settings:{apiKey:'SENTINEL_SECRET'}}}}));fs.writeFileSync(choices,JSON.stringify([{id:'general',model:'omlx/qwen',prompt:'enhance'}]));
 const result=spawnSync(process.execPath,[cli,'preview','--choices',choices,'--config',config],{encoding:'utf8'});
 assert.equal(result.status,0);assert.equal(result.stdout.includes('SENTINEL_SECRET'),false);assert.match(result.stdout,/REDACTED/);
});

test('plugin dry-run leaves global and project installations unchanged',t=>{
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'plugin dry-run '));t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
 const env={...process.env,XDG_CONFIG_HOME:path.join(directory,'config')};
 for(const project of [false,true]){
  const target=path.join(project?path.join(directory,'.opencode'):path.join(env.XDG_CONFIG_HOME,'opencode'),'plugins','agent-usage');
  const flags=project?['--project']:[];
  let result=spawnSync(process.execPath,[cli,'plugin','install',...flags,'--dry-run'],{cwd:directory,env,encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);assert.equal(fs.existsSync(path.dirname(target)),false,'dry-run created plugin directories');
  result=spawnSync(process.execPath,[cli,'plugin','install',...flags],{cwd:directory,env,encoding:'utf8'});assert.equal(result.status,0,result.stderr);
  result=spawnSync(process.execPath,[cli,'plugin','uninstall',...flags,'--dry-run'],{cwd:directory,env,encoding:'utf8'});
  assert.equal(result.status,0,result.stderr);assert.equal(fs.lstatSync(target).isSymbolicLink(),true,'dry-run removed plugin');
  result=spawnSync(process.execPath,[cli,'plugin','uninstall',...flags],{cwd:directory,env,encoding:'utf8'});assert.equal(result.status,0,result.stderr);
 }
});

for(const runtime of ['missing','unsupported','unavailable'])test(`undo restores the journal when native runtime is ${runtime}`,async t=>{
 const {apply}=await import('../src/store.js');
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'offline undo '));t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
 const config=path.join(directory,'opencode.json'),stateRoot=path.join(directory,'state'),state=path.join(stateRoot,'opencode-agent-setup');
 const before='{"theme":"original"}\n';fs.writeFileSync(config,before);
 await apply(config,[{path:['agents','general','steps'],value:24}],{state,expected:before,validate:async()=>{}});
 const applied=fs.readFileSync(config,'utf8');const executable=path.join(directory,'native');
 if(runtime!=='missing')fs.writeFileSync(executable,`#!${process.execPath}\nif(process.argv[2]==='--version'){console.log('opencode v${runtime==='unsupported'?'2.1.3':'2.1.2'}');process.exit(0)}process.exit(1);\n`,{mode:0o700});
 const env={...process.env,XDG_STATE_HOME:stateRoot,OPENCODE_AGENT_SETUP_BINARY:executable};
 const dry=spawnSync(process.execPath,[cli,'undo','--config',config,'--dry-run'],{env,encoding:'utf8'});
 assert.equal(dry.status,0,dry.stderr);assert.equal(fs.readFileSync(config,'utf8'),applied);
 const result=spawnSync(process.execPath,[cli,'undo','--config',config,'--yes'],{env,encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);assert.equal(fs.readFileSync(config,'utf8'),before);assert.match(result.stdout,/restored/i);assert.match(result.stdout,/not.*validated|validation.*unavailable|unvalidated/i);
});

test('plugin install resolves checkout paths containing spaces and URL characters',t=>{
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'patcher checkout #% '));t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
 for(const folder of ['bin','src','data','plugin'])fs.cpSync(path.resolve(folder),path.join(directory,folder),{recursive:true});
 fs.copyFileSync(path.resolve('package.json'),path.join(directory,'package.json'));
 fs.symlinkSync(path.resolve('node_modules'),path.join(directory,'node_modules'),'dir');
 const config=path.join(directory,'config'),env={...process.env,XDG_CONFIG_HOME:config};
 const result=spawnSync(process.execPath,[path.join(directory,'bin/setup.js'),'plugin','install'],{cwd:directory,env,encoding:'utf8'});
 assert.equal(result.status,0,result.stderr);
 assert.equal(fs.realpathSync(path.join(config,'opencode/plugins/agent-usage')),fs.realpathSync(path.join(directory,'plugin/agent-usage')));
});

test('undo reports on-disk recovery when an inherited Markdown agent cannot be reconstructed',async t=>{
 const {apply}=await import('../src/store.js');
 const directory=fs.mkdtempSync(path.join(os.tmpdir(),'markdown undo '));t.after(()=>fs.rmSync(directory,{recursive:true,force:true}));
 const config=path.join(directory,'opencode.json'),stateRoot=path.join(directory,'state'),state=path.join(stateRoot,'opencode-agent-setup');
 const before='{"theme":"original"}\n';fs.writeFileSync(config,before);
 await apply(config,[{path:['agents','general','system'],value:'temporary'}],{state,expected:before,validate:async()=>{}});
 const configDir=path.join(directory,'.opencode');fs.mkdirSync(path.join(configDir,'agents'),{recursive:true});fs.writeFileSync(path.join(configDir,'agents','general.md'),'---\nmode: subagent\n---\nFrom Markdown\n');
 const executable=path.join(directory,'native');
 fs.writeFileSync(executable,`#!${process.execPath}\nconst fs=require('node:fs');if(process.argv[2]==='--version'){console.log('opencode v2.1.2');process.exit(0)}const docs=[{type:'document',path:${JSON.stringify(config)},info:JSON.parse(fs.readFileSync(${JSON.stringify(config)},'utf8'))},{type:'directory',path:${JSON.stringify(configDir)}}];const data={'config.get':docs,'agent.list':[{id:'build'},{id:'general',system:'From Markdown'}],'model.list':[]};console.log(JSON.stringify({data:data[process.argv[3]]}));\n`,{mode:0o700});
 const env={...process.env,XDG_STATE_HOME:stateRoot,OPENCODE_AGENT_SETUP_BINARY:executable};
 const result=spawnSync(process.execPath,[cli,'undo','--config',config,'--yes'],{env,encoding:'utf8',timeout:30000});
 assert.equal(result.status,0,result.stderr);assert.equal(fs.readFileSync(config,'utf8'),before);assert.match(result.stdout,/not.*validated/i);assert.match(result.stdout,/Markdown|inherited/i);
});
