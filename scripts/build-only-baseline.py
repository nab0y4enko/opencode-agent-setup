"""Build-only baseline for the stage-commit task: same fixture, same two stages, no delegation.
Produces a usage report to compare against the mixed Orchestrator/Qwen run (artifacts/stage-usage.json)."""
import os,json,pathlib,tempfile,subprocess,time,sys
ROOT=pathlib.Path(__file__).resolve().parent.parent
base=pathlib.Path(tempfile.mkdtemp(prefix='build-only-baseline-')).resolve();job=base/'repo';job.mkdir()
env=dict(os.environ,PWD=str(job))
def git(*args):return subprocess.check_output(['git',*args],cwd=job,text=True).strip()
(job/'opencode.json').write_text(json.dumps({'warming':False,'agents':{'build':{'model':'openai/gpt-6.1-sol#high'}}},indent=2))
(job/'.gitignore').write_text('opencode.json\nevidence/\n__pycache__/\n');(job/'evidence').mkdir()
(job/'fixture.py').write_text('def clamp(value, low, high):\n    return min(value, low)\n')
(job/'test_fixture.py').write_text('import unittest\nfrom fixture import clamp\nclass Tests(unittest.TestCase):\n def test_low(self): self.assertEqual(clamp(-2,0,10),0)\n def test_middle(self): self.assertEqual(clamp(4,0,10),4)\n def test_high(self): self.assertEqual(clamp(15,0,10),10)\n')
(job/'unrelated.txt').write_text('baseline\n')
git('init','-b','stage-smoke');git('add','.gitignore','fixture.py','test_fixture.py','unrelated.txt');git('commit','-m','test: baseline broken clamp fixture');baseline=git('rev-parse','HEAD')
prompt=f'''Perform two dependent implementation stages yourself in this disposable repo. Do not delegate to any subagent.
Stage 1: fix ONLY fixture.py so clamp returns low below the range, high above it, and the original value inside it. test_fixture.py has 3 tests and must remain unchanged. Run python3 -m unittest -v. Write evidence/stage1.patch and evidence/stage1-tests.txt, then commit only fixture.py.
Stage 2: add a regression test requiring ValueError when low > high; observe its failure, implement the validation, rerun python3 -m unittest -v (4 tests expected). Write evidence/stage2.patch and evidence/stage2-tests.txt, commit this stage separately; never amend stage 1.
Do not change opencode.json, .gitignore or unrelated.txt. Return a concise stage table with commit SHAs and validation. Initial HEAD: {baseline}.'''
start=time.monotonic()
result=subprocess.run(['opencode','run','--agent','build','--model','openai/gpt-6.1-sol#high','--auto','--format','json',prompt],cwd=job,env=env,capture_output=True,text=True,timeout=300)
(ROOT/'artifacts/build-only-events.jsonl').write_text(result.stdout)
check=subprocess.run(['python3','-m','unittest','-v'],cwd=job,capture_output=True,text=True)
commits=[line.split('\t',1) for line in git('log','--reverse','--format=%H%x09%s',baseline+'..HEAD').splitlines() if line]
usage=subprocess.run(['node',str(ROOT/'bin/setup.js'),'usage','--directory',str(job),'--json'],cwd=ROOT,capture_output=True,text=True)
report={'workspace':str(job),'elapsed_seconds':round(time.monotonic()-start,2),'opencode_exit':result.returncode,'independent_test_exit':check.returncode,'tests':check.stderr,'commits':commits,'status':git('status','--porcelain'),'usage':json.loads(usage.stdout) if usage.returncode==0 else None,'usage_error':usage.stderr[-500:] if usage.returncode else ''}
(ROOT/'artifacts/build-only-result.json').write_text(json.dumps(report,indent=2));print(json.dumps({k:v for k,v in report.items() if k!='usage'},indent=2))
mixed=ROOT/'artifacts/stage-usage.json'
if report['usage'] and mixed.exists():
 compare=subprocess.run(['node',str(ROOT/'bin/setup.js'),'usage','--session',json.loads(mixed.read_text())['root']['id'],'--compare',report['usage']['root']['id']],cwd=ROOT,capture_output=True,text=True)
 (ROOT/'artifacts/usage-comparison.txt').write_text(compare.stdout);print(compare.stdout.split('Comparison',1)[-1])
sys.exit(0 if report['opencode_exit']==0 and report['independent_test_exit']==0 and report['usage'] else 1)
