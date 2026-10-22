"""Explicit local-only functional test. Uses oMLX's existing key without printing it.
No global config, ports, models or server settings are changed.
"""
import json, os, subprocess, tempfile, pathlib, time, sys, atexit
ROOT=pathlib.Path(__file__).resolve().parent.parent
settings=json.loads((pathlib.Path.home()/'.omlx/settings.json').read_text())
key=os.environ.get('OMLX_API_KEY') or settings['auth']['api_key']
port=settings['server']['port']
coordinator='--coordinator' in sys.argv
model=next((a for a in sys.argv[1:] if not a.startswith('--')),'qwen-3.8-nf-splash')
job=pathlib.Path(tempfile.mkdtemp(prefix='opencode-real-worker-')).resolve()
env=dict(os.environ,PWD=str(job))
keyfile=job/'.test-api-key'
keyfile.write_text(key)
keyfile.chmod(0o600)
atexit.register(lambda:keyfile.unlink(missing_ok=True))
configuration={
 'providers':{'omlx':{'name':'Local smoke test','package':'@opencode/ai/providers/openai-compatible','settings':{'baseURL':f'http://127.0.0.1:{port}/v1','apiKey':'{file:'+str(keyfile)+'}'},'models':{model:{'name':model,'capabilities':{'tools':True,'input':['text'],'output':['text']},'limit':{'context':262144,'output':8192}}}}},
 'agents':{'general':{'model':f'omlx/{model}','steps':16,'system':'Complete only the assigned fixture change. Use tools. Run the requested tests in the foreground. Return exit status and actual test counts; do not claim success without test evidence.'},'explore':{'model':f'omlx/{model}','steps':8}},
 'model':f'omlx/{model}', 'warming':False
}
# Exercise the shipped patcher templates, not a separate handwritten approximation.
policy_js="""
import {buildOverrides} from './src/policy.js';
const model=process.argv[1],obj={};
for(const change of buildOverrides(['general','explore','orchestrator'].map(id=>({id,model,prompt:'enhance'})))){
 let current=obj;for(const key of change.path.slice(0,-1))current=current[key]??=( {} );
 current[change.path.at(-1)]=change.value;
}
console.log(JSON.stringify(obj.agents));
"""
configuration['agents']=json.loads(subprocess.check_output(['node','--input-type=module','-e',policy_js,f'omlx/{model}'],cwd=ROOT,text=True))
(job/'opencode.json').write_text(json.dumps(configuration,indent=2))
(job/'fixture.py').write_text('def clamp(value, low, high):\n    return min(value, low)\n')
(job/'test_fixture.py').write_text('import unittest\nfrom fixture import clamp\nclass Tests(unittest.TestCase):\n def test_low(self): self.assertEqual(clamp(-2,0,10),0)\n def test_middle(self): self.assertEqual(clamp(4,0,10),4)\n def test_high(self): self.assertEqual(clamp(15,0,10),10)\n')
prompt='Fix only fixture.py so clamp correctly bounds numbers inclusively between low and high. Read test_fixture.py, run python3 -m unittest -v to completion in the foreground, and report actual exit status and count. Do not change tests, config, or other files. Do not delegate.'
# Wait for native configuration/model registration in the existing service.
for attempt in range(30):
    inventory=json.loads(subprocess.check_output(['opencode','api','model.list','--param','location[directory]='+str(job)],text=True))
    if any(m.get('providerID')=='omlx' and m.get('id')==model for m in inventory.get('data',[])):break
    time.sleep(.15)
if coordinator:prompt='Delegate this task to General using one foreground subagent call. Do not edit or run commands yourself. '+prompt
start=time.monotonic()
try:
 result=subprocess.run(['opencode','run','--agent',('orchestrator' if coordinator else 'general'),'--model',f'omlx/{model}','--auto','--format','json',prompt],cwd=job,env=env,capture_output=True,text=True,timeout=180)
 # Credentials remain only in the child environment; event logs contain model output, not configuration.
 (ROOT/'artifacts'/'live-local-worker.jsonl').write_text(result.stdout)
 check=subprocess.run(['python3','-m','unittest','-v'],cwd=job,capture_output=True,text=True)
 report={'model':f'omlx/{model}','coordinator':coordinator,'port':port,'elapsed_seconds':round(time.monotonic()-start,2),'opencode_exit':result.returncode,'independent_test_exit':check.returncode,'test_output':check.stderr,'workspace':str(job),'stderr':result.stderr[-2000:]}
except subprocess.TimeoutExpired:
 report={'model':f'omlx/{model}','coordinator':coordinator,'port':port,'elapsed_seconds':round(time.monotonic()-start,2),'status':'timeout','workspace':str(job)}
keyfile.unlink(missing_ok=True)
(ROOT/'artifacts'/'live-local-result.json').write_text(json.dumps(report,indent=2))
print(json.dumps(report,indent=2))
