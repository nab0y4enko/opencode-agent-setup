"""Explicit cloud-led mixed-profile test in a disposable Git repo; no production settings applied."""
import os,json,pathlib,tempfile,subprocess,time,atexit
from importlib.util import module_from_spec,spec_from_file_location
ROOT=pathlib.Path(__file__).resolve().parent.parent
def dispatch_info(part):
 # OpenCode v2.1.2: only background=true selects async; a running result
 # also records a foreground job explicitly moved to the background.
 state=part.get('state',{});inputs=state.get('input',{})
 meta=state.get('metadata',{}).get('metadata',{});status=meta.get('status')
 background=True if inputs.get('background') is True or status=='running' else False if status=='completed' else None
 return {'agent':inputs.get('agent'),'background':background,'backgroundExplicit':'background' in inputs,
         'completionStatus':status,'sessionID':meta.get('sessionID')}

def main():
 base=pathlib.Path(tempfile.mkdtemp(prefix='native-stage-check-')).resolve();job=base/'repo';job.mkdir()
 settings=json.loads((pathlib.Path.home()/'.omlx/settings.json').read_text());port=settings['server']['port']
 secret=base/'local.key';secret.write_text(settings['auth']['api_key']);secret.chmod(0o600);atexit.register(lambda:secret.unlink(missing_ok=True))
 env=dict(os.environ,PWD=str(job))
 def git(*args):return subprocess.check_output(['git',*args],cwd=job,text=True).strip()
 def evidence(obj):
  (ROOT/'artifacts/stage-commit-result.json').write_text(json.dumps(obj,indent=2));print(json.dumps(obj,indent=2))
 choices=json.loads((ROOT/'examples/mixed-workers.json').read_text())
 js="""import {buildOverrides} from './src/policy.js';const obj={};for(const c of buildOverrides(JSON.parse(process.argv[1]))){let o=obj;for(const k of c.path.slice(0,-1))o=o[k]??={};o[c.path.at(-1)]=c.value;}console.log(JSON.stringify(obj));"""
 config=json.loads(subprocess.check_output(['node','--input-type=module','-e',js,json.dumps(choices)],cwd=ROOT,text=True))
 config.update({'default_agent':'orchestrator','warming':False,'providers':{'omlx':{'name':'Local staged test','package':'@opencode/ai/providers/openai-compatible','settings':{'baseURL':f'http://127.0.0.1:{port}/v1','apiKey':'{file:'+str(secret)+'}'},'models':{'qwen-3.8-nf-splash':{'capabilities':{'tools':True,'input':['text'],'output':['text']},'limit':{'context':262144,'output':8192}}}}}})
 (job/'opencode.json').write_text(json.dumps(config,indent=2));(job/'evidence').mkdir()
 (job/'.gitignore').write_text('opencode.json\nevidence/\n__pycache__/\n')
 (job/'fixture.py').write_text('def clamp(value, low, high):\n    return min(value, low)\n')
 (job/'test_fixture.py').write_text('import unittest\nfrom fixture import clamp\nclass Tests(unittest.TestCase):\n def test_low(self): self.assertEqual(clamp(-2,0,10),0)\n def test_middle(self): self.assertEqual(clamp(4,0,10),4)\n def test_high(self): self.assertEqual(clamp(15,0,10),10)\n')
 (job/'unrelated.txt').write_text('baseline\n')
 git('init','-b','stage-smoke');git('add','.gitignore','fixture.py','test_fixture.py','unrelated.txt');git('commit','-m','test: baseline broken clamp fixture');baseline=git('rev-parse','HEAD')
 for attempt in range(30):
  data=json.loads(subprocess.check_output(['opencode','api','model.list','--param','location[directory]='+str(job)],text=True)).get('data',[])
  if any(m.get('providerID')=='omlx' for m in data):break
  time.sleep(.15)
 prompt=f'''Use one foreground General subagent for this complete two-stage task. Preserve its configured local model. Give it both dependent stages in a single bounded brief so it can reuse context. General owns fixture.py and test_fixture.py; it must verify, self-check and commit stage 1 before starting stage 2. You are the cloud planner and reviewer; General is only the implementation worker. Do not edit or run shell commands yourself. The task supplies all required scope: delegate once without initial discovery. Build remains available for an evidence-backed local blocker. A separate reviewer seat is unnecessary because you will review the result in this cloud session.
 Stage 1: fix ONLY fixture.py so clamp returns low below the range, high above it, and the original value inside it. test_fixture.py has 3 tests and must remain unchanged. Run python3 -m unittest -v. Write git diff output to evidence/stage1.patch and full passing unittest output to evidence/stage1-tests.txt, then commit only fixture.py.
 Stage 2: add a regression test requiring ValueError when low > high; run python3 -m unittest -v and save its failing four-test output to evidence/stage2-red-tests.txt. Implement validation, rerun python3 -m unittest -v (exactly 4 tests expected). Write git diff output to evidence/stage2.patch and full passing unittest output to evidence/stage2-tests.txt, then commit this stage separately; never amend stage 1.
 Do not change opencode.json, .gitignore or unrelated.txt. Evidence artifacts are ignored by Git. Stop on failed required checks or scope conflict. After the worker completes both stages, review evidence/stage1.patch, stage2.patch, stage1-tests.txt, stage2-red-tests.txt and stage2-tests.txt once against the requirements and edge cases. Keep planning and final correctness judgment in this cloud session. Return a concise stage table with commit SHAs, validation and a final VERDICT: PASS | CHANGES_REQUIRED | NEEDS_CONTEXT; report missing evidence instead of inferring a pass. Initial HEAD: {baseline}.'''

 start=time.monotonic()
 try:
  result=subprocess.run(['opencode','run','--agent','orchestrator','--model','openai/gpt-6.1-sol#medium','--auto','--format','json',prompt],cwd=job,env=env,capture_output=True,text=True,timeout=300)
  model_run_seconds=round(time.monotonic()-start,3)
  (ROOT/'artifacts/stage-commit-events.jsonl').write_text(result.stdout)
  check=subprocess.run(['python3','-m','unittest','-v'],cwd=job,capture_output=True,text=True)
  commits=[dict(zip(['sha','subject'],line.split('\t',1))) for line in git('log','--reverse','--format=%H%x09%s',baseline+'..HEAD').splitlines() if line]
  details=[]
  for commit in commits:details.append({**commit,'files':git('diff-tree','--no-commit-id','--name-only','-r',commit['sha']).splitlines()})
  report={'profile':'cloud-led','workspace':str(job),'elapsed_seconds':round(time.monotonic()-start,2),'model_run_seconds':model_run_seconds,'opencode_exit':result.returncode,'independent_test_exit':check.returncode,'tests':check.stderr,'commits':details,'status':git('status','--porcelain'),'stderr':result.stderr[-1000:],'port':port}
 except subprocess.TimeoutExpired as error:
  spec=spec_from_file_location('capture',ROOT/'scripts/build-only-baseline.py');capture=module_from_spec(spec);spec.loader.exec_module(capture)
  partial=error.stdout or '';partial=partial.decode(errors='replace') if isinstance(partial,bytes) else partial
  interrupts=capture.interrupt_sessions(partial)
  report={'profile':'cloud-led','workspace':str(job),'status':'timeout','interrupts':interrupts,'elapsed_seconds':round(time.monotonic()-start,2),'port':port}
 # Inspect actual child session records, not just the coordinator's summary.
 report['dispatches']=[];report['review']=''
 if 'result' in locals():
  for line in result.stdout.splitlines():
   if not line.strip():continue
   event=json.loads(line)
   part=event.get('part',{})
   if event.get('type')=='text':report['review']+=part.get('text','')+'\n'
   if event.get('type')!='tool_use' or part.get('tool')!='subagent':continue
   state=part.get('state',{});inputs=state.get('input',{});sid=state.get('metadata',{}).get('metadata',{}).get('sessionID')
   record=json.loads(subprocess.check_output(['opencode','api','session.get','--param','sessionID='+sid],text=True))['data'] if sid else {}
   report['dispatches'].append({**dispatch_info(part),'model':record.get('model')})
   if inputs.get('agent')=='cloud-reviewer':report['review']=state.get('output','')
 # Token/model/agent usage from OpenCode's own session records, for the root session this run created.
 usage=subprocess.run(['node',str(ROOT/'bin/setup.js'),'usage','--directory',str(job),'--json'],cwd=ROOT,capture_output=True,text=True)
 if usage.returncode==0:
  report['usage']=json.loads(usage.stdout)
  (ROOT/'artifacts/stage-usage.json').write_text(usage.stdout)
  rendered=subprocess.run(['node',str(ROOT/'bin/setup.js'),'usage','--session',report['usage']['root']['id']],cwd=ROOT,capture_output=True,text=True)
  (ROOT/'artifacts/stage-usage.txt').write_text(rendered.stdout);print(rendered.stdout)
 else:
  report['usage_error']=usage.stderr[-500:]
 report['total_seconds']=round(time.monotonic()-start,3)
 evidence(report)
 return(subprocess.run(['python3',str(ROOT/'scripts/verify-stage-result.py'),str(ROOT/'artifacts/stage-commit-result.json')]).returncode)

if __name__ == '__main__':
 raise SystemExit(main())
