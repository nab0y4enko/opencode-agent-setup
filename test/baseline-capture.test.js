import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {spawnSync} from 'node:child_process';

const script=path.resolve('scripts/build-only-baseline.py');
function python(code,input){const r=spawnSync('python3',['-c',`import importlib.util,json,pathlib,subprocess,sys\noriginals={name:getattr(subprocess,name) for name in ('run','check_output','Popen')}\ndef tripwire(*args,**kwargs): raise RuntimeError('Baseline import attempted a subprocess; inference is forbidden during tests')\nfor name in originals: setattr(subprocess,name,tripwire)\nspec=importlib.util.spec_from_file_location('baseline',sys.argv[1]); m=importlib.util.module_from_spec(spec); spec.loader.exec_module(m)\nfor name,original in originals.items(): setattr(subprocess,name,original)\n${code}`,script],{input:JSON.stringify(input),encoding:'utf8',timeout:10000});assert.equal(r.status,0,r.stderr+r.stdout);return JSON.parse(r.stdout);}
test('baseline import launches no subprocess or model request',()=>{
 assert.deepEqual(python('print(json.dumps({"imported": True}))',null),{imported:true});
});
test('mixed baseline import launches no subprocess or model request',()=>{
 const r=spawnSync('python3',['-c',`import importlib.util,subprocess,sys
def tripwire(*args,**kwargs): raise RuntimeError('Mixed import attempted a subprocess')
for name in ('run','check_output','Popen'): setattr(subprocess,name,tripwire)
spec=importlib.util.spec_from_file_location('mixed',sys.argv[1]);m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)`,path.resolve('scripts/stage-commit-smoke.py')],{encoding:'utf8',timeout:10000});
 assert.equal(r.status,0,r.stderr+r.stdout);
});
test('baseline event capture preserves bad records and attempted delegation even without a child session',()=>{
 const events=[JSON.stringify({type:'step_start',sessionID:'root'}),JSON.stringify({type:'tool_use',sessionID:'root',part:{tool:'subagent',state:{status:'error'}}}),'not json'].join('\n');
 const r=python('print(json.dumps(m.summarize_events(json.load(sys.stdin))))',events);
 assert.equal(r.count,2);assert.deepEqual(r.sessionIDs,['root']);assert.deepEqual(r.delegationCalls,['subagent']);assert.equal(r.parseErrors.length,1);
});
test('baseline timeout interrupts only IDs from its captured stream and records native failures',()=>{
 const code=`from types import SimpleNamespace\ncalls=[]\ndef runner(args,**kwargs):\n calls.append(args)\n if args[-1].endswith('bad'): return SimpleNamespace(returncode=1,stdout='',stderr='fixture failure')\n return SimpleNamespace(returncode=0,stdout='{"interrupted":true}',stderr='')\nevents='\\n'.join(json.dumps({'sessionID':sid}) for sid in ['owned-good','owned-bad','owned-good'])\nprint(json.dumps({'calls':calls,'interrupts':m.interrupt_sessions(events,runner=runner),'missing':m.interrupt_sessions('',runner=runner)}))`;
 const r=python(code,null);assert.equal(r.calls.length,2);
 assert.deepEqual(r.calls.map(c=>c.at(-1)),['sessionID=owned-good','sessionID=owned-bad']);
 assert.equal(r.interrupts[0].interrupted,true);assert.equal(r.interrupts[1].interrupted,false);assert.match(r.interrupts[1].error,/fixture failure/);
 assert.equal(r.missing[0].interrupted,false);assert.match(r.missing[0].error,/No session ID/);
});
test('baseline main timeout uses targeted interruption and always writes a failed result',()=>{
 const code=String.raw`import contextlib,io,tempfile
from types import SimpleNamespace
with tempfile.TemporaryDirectory(prefix='baseline-timeout-fixture-') as temporary:
 base=pathlib.Path(temporary);(base/'scripts').mkdir()
 (base/'scripts/verify-baseline-result.py').write_text(pathlib.Path(sys.argv[1]).with_name('verify-baseline-result.py').read_text())
 m.ROOT=base;m.git=lambda job,*args: 'a'*40 if args[0]=='rev-parse' else ''
 original_mkdtemp=m.tempfile.mkdtemp
 m.tempfile.mkdtemp=lambda **kwargs: original_mkdtemp(dir=base,**kwargs)
 calls=[]
 def runner(args,**kwargs):
  calls.append(args[:3])
  if args[:2]==['opencode','run']:
   assert '--standalone' in args
   assert kwargs['env']['XDG_CONFIG_HOME']==str(base/'isolated-config') or pathlib.Path(kwargs['env']['XDG_CONFIG_HOME']).name=='isolated-config'
   raise subprocess.TimeoutExpired(args,300,output=json.dumps({'type':'step_start','sessionID':'owned-timeout'}).encode())
  if args[:3]==['opencode','api','session.interrupt']:
   return SimpleNamespace(returncode=0,stdout='{"interrupted":true}',stderr='')
  raise RuntimeError('Unexpected subprocess in controlled test: '+str(args[:3]))
 m.subprocess.run=runner
 with contextlib.redirect_stdout(io.StringIO()): exit_code=m.main()
 report=json.loads((base/'artifacts/build-only-result.json').read_text())
 print(json.dumps({'exit':exit_code,'error':report.get('error'),'interrupts':report.get('interrupts'),'passed':report['verification']['passed'],'calls':calls}))`;
 const r=python(code,null);assert.equal(r.exit,1);assert.equal(r.error,'timeout');assert.equal(r.passed,false);
 assert.deepEqual(r.interrupts,[{sessionID:'owned-timeout',interrupted:true}]);
 assert.deepEqual(r.calls,[['opencode','run','--agent'],['opencode','api','session.interrupt']]);
});
test('baseline capture independently replays committed stages and the old-code regression in isolated directories',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'baseline-capture-'));
 const git=(...args)=>{const r=spawnSync('git',args,{cwd:dir,encoding:'utf8',env:{...process.env,GIT_AUTHOR_NAME:'Fixture',GIT_AUTHOR_EMAIL:'fixture@example.test',GIT_COMMITTER_NAME:'Fixture',GIT_COMMITTER_EMAIL:'fixture@example.test'}});assert.equal(r.status,0,r.stderr);return r.stdout.trim();};
 try {
  const first='def clamp(value, low, high):\n    return max(low, min(value, high))\n';
  const tests='import unittest\nfrom fixture import clamp\nclass Tests(unittest.TestCase):\n def test_low(self): self.assertEqual(clamp(-1,0,10),0)\n def test_middle(self): self.assertEqual(clamp(5,0,10),5)\n def test_high(self): self.assertEqual(clamp(11,0,10),10)\n';
  fs.writeFileSync(path.join(dir,'fixture.py'),first);fs.writeFileSync(path.join(dir,'test_fixture.py'),tests);
  git('init','-b','test');git('add','.');git('commit','-m','stage1');const sha1=git('rev-parse','HEAD');
  fs.appendFileSync(path.join(dir,'test_fixture.py'),' def test_invalid(self):\n  with self.assertRaises(ValueError): clamp(5,10,0)\n');
  fs.writeFileSync(path.join(dir,'fixture.py'),'def clamp(value, low, high):\n    if low > high: raise ValueError("invalid bounds")\n    return max(low, min(value, high))\n');
  git('add','.');git('commit','-m','stage2');const sha2=git('rev-parse','HEAD');
  const before=fs.readFileSync(path.join(dir,'fixture.py'),'utf8');
  const checkpoints=python('v=json.load(sys.stdin);print(json.dumps(m.collect_checkpoints(pathlib.Path(v["job"]),v["commits"])))',{job:dir,commits:[{sha:sha1},{sha:sha2}]});
  assert.equal(checkpoints.length,2);assert.equal(checkpoints[0].independent_test_exit,0);assert.match(checkpoints[0].tests,/Ran 3 tests/);
  assert.equal(checkpoints[1].independent_test_exit,0);assert.match(checkpoints[1].tests,/Ran 4 tests/);
  assert.equal(checkpoints[1].regression_exit,1);assert.match(checkpoints[1].regression_tests,/ValueError not raised/);
  assert.equal(fs.readFileSync(path.join(dir,'fixture.py'),'utf8'),before);assert.equal(git('status','--porcelain'),'');
 } finally {fs.rmSync(dir,{recursive:true,force:true});}
});

test('mixed capture uses native completion metadata for omitted foreground flags and background transitions',()=>{
 const code=`import importlib.util,json\nspec=importlib.util.spec_from_file_location('mixed','scripts/stage-commit-smoke.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)\ncases=[({},'completed'),({'background':False},'running'),({'background':True},'completed'),({},None)]\nprint(json.dumps([m.dispatch_info({'state':{'input':{'agent':'general',**inputs},'metadata':{'metadata':{'sessionID':'child','status':status}}}}) for inputs,status in cases]))`;
 const r=spawnSync('python3',['-c',code],{encoding:'utf8',timeout:10000});assert.equal(r.status,0,r.stderr+r.stdout);
 const rows=JSON.parse(r.stdout);assert.deepEqual(rows.map(r=>r.background),[false,true,true,null]);
 assert.equal(rows[0].sessionID,'child');assert.equal(rows[0].completionStatus,'completed');assert.equal(rows[0].backgroundExplicit,false);
});

test('Build baseline isolates global profiles while preserving native role defaults',()=>{
 const result=python('import tempfile\nwith tempfile.TemporaryDirectory() as temporary:\n job=pathlib.Path(temporary)/"repo";job.mkdir()\n env=m.baseline_environment(job)\n print(json.dumps({"config":m.baseline_config(),"isolated":env["XDG_CONFIG_HOME"]==str(job.parent/"isolated-config"),"created":pathlib.Path(env["XDG_CONFIG_HOME"]).is_dir(),"pwd":env["PWD"]==str(job)}))',null);
 assert.equal(result.isolated,true);assert.equal(result.created,true);assert.equal(result.pwd,true);
 assert.equal(result.config.agents.build.system,undefined);
 assert.equal(result.config.agents.build.model,'openai/gpt-6.1-sol#high');
 assert.equal(result.config.agents.build.request.body.service_tier,'default');
});
