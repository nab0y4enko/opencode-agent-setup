"""Explicit mixed OpenAI/Qwen test in a disposable Git repo; no production settings applied."""
import os,json,pathlib,tempfile,subprocess,time,atexit
ROOT=pathlib.Path(__file__).resolve().parent.parent
base=pathlib.Path(tempfile.mkdtemp(prefix='native-stage-check-')).resolve();job=base/'repo';job.mkdir()
settings=json.loads((pathlib.Path.home()/'.omlx/settings.json').read_text());port=settings['server']['port']
secret=base/'local.key';secret.write_text(settings['auth']['api_key']);secret.chmod(0o600);atexit.register(lambda:secret.unlink(missing_ok=True))
env=dict(os.environ,PWD=str(job))
def git(*args):return subprocess.check_output(['git',*args],cwd=job,text=True).strip()
def evidence(obj):
 (ROOT/'artifacts/stage-commit-result.json').write_text(json.dumps(obj,indent=2));print(json.dumps(obj,indent=2))
choices=[{'id':id,'model':('omlx/qwen-3.8-nf-splash' if id in ['general','explore'] else 'openai/gpt-6.1-sol#medium' if id=='orchestrator' else 'openai/gpt-6.1-sol#high'),'prompt':'enhance'} for id in ['orchestrator','build','plan','general','explore','cloud-reviewer']]
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
prompt=f'''Perform two dependent implementation stages in this disposable repo. Use native foreground subagents, preserving each agent's configured model. Do not edit or run shell commands yourself. Supply complete bounded briefs and commit requirements.
Stage 1: General must fix ONLY fixture.py so clamp returns low below the range, high above it, and the original value inside it. Existing test_fixture.py has 3 tests and must remain unchanged. Run python3 -m unittest -v. Self-review, write the pre-commit diff and test evidence to evidence/stage1.patch and evidence/stage1-tests.txt, then commit only fixture.py. Report SHA. Review the actual patch and evidence before stage 2.
Stage 2: Explicitly dispatch Build to test the writable OpenAI escalation path. Build owns fixture.py and test_fixture.py. Add a regression test requiring ValueError when low > high; observe its failure, implement the validation, and rerun python3 -m unittest -v (4 tests expected). Self-review, write evidence/stage2.patch and evidence/stage2-tests.txt before committing. Commit this stage separately; never amend stage 1. Return SHA and checks. Do not delegate from this child.
After both stages, dispatch cloud-reviewer once to inspect requirements plus both evidence patches/logs. Reviewer must not mutate files or run shell. Return a concise stage table with commit SHAs, validation and review verdict. Evidence artifacts are intentionally ignored by Git. Do not change opencode.json, .gitignore or unrelated.txt. Stop on required validation failure or scope conflict. Test repo initial HEAD: {baseline}.'''
start=time.monotonic()
try:
 result=subprocess.run(['opencode','run','--agent','orchestrator','--model','openai/gpt-6.1-sol#medium','--auto','--format','json',prompt],cwd=job,env=env,capture_output=True,text=True,timeout=240)
 (ROOT/'artifacts/stage-commit-events.jsonl').write_text(result.stdout)
 check=subprocess.run(['python3','-m','unittest','-v'],cwd=job,capture_output=True,text=True)
 commits=[dict(zip(['sha','subject'],line.split('\t',1))) for line in git('log','--reverse','--format=%H%x09%s',baseline+'..HEAD').splitlines() if line]
 details=[]
 for commit in commits:details.append({**commit,'files':git('diff-tree','--no-commit-id','--name-only','-r',commit['sha']).splitlines()})
 report={'workspace':str(job),'elapsed_seconds':round(time.monotonic()-start,2),'opencode_exit':result.returncode,'independent_test_exit':check.returncode,'tests':check.stderr,'commits':details,'status':git('status','--porcelain'),'stderr':result.stderr[-1000:],'port':port}
except subprocess.TimeoutExpired:
 report={'workspace':str(job),'status':'timeout','elapsed_seconds':round(time.monotonic()-start,2),'port':port}
# Inspect actual child session records, not just the coordinator's summary.
report['dispatches']=[];report['review']=''
if 'result' in locals():
 for line in result.stdout.splitlines():
  if not line.strip():continue
  event=json.loads(line)
  part=event.get('part',{})
  if event.get('type')!='tool_use' or part.get('tool')!='subagent':continue
  state=part.get('state',{});inputs=state.get('input',{});sid=state.get('metadata',{}).get('metadata',{}).get('sessionID')
  record=json.loads(subprocess.check_output(['opencode','api','session.get','--param','sessionID='+sid],text=True))['data'] if sid else {}
  report['dispatches'].append({'agent':inputs.get('agent'),'background':inputs.get('background'),'sessionID':sid,'model':record.get('model')})
  if inputs.get('agent')=='cloud-reviewer':report['review']=state.get('output','')
evidence(report)
raise SystemExit(subprocess.run(['python3',str(ROOT/'scripts/verify-stage-result.py'),str(ROOT/'artifacts/stage-commit-result.json')]).returncode)
