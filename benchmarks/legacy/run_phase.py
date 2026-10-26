import json,subprocess,time,os,sys,signal
from pathlib import Path
r=Path(__file__).parent
arm,phase,tier=sys.argv[1:4]
d=r/arm/phase; repo=r/arm/'repo'; prompt=(d/'prompt.txt').read_text()
model=('openai/gpt-6.1-sol#medium' if tier=='cloud' else 'omlx/qwen-3.8-nf-splash')
write='implement' in phase or 'repair' in phase
seconds=900 if write else 300
if arm=='opencode':
 a=['opencode','run','--standalone','--format','json','--agent','build' if write else 'plan','--model',model,prompt]
else:
 a=['cline','--json','--provider','openai-codex' if tier=='cloud' else 'openai-compatible','--model','gpt-6.1-sol' if tier=='cloud' else 'qwen-3.8-nf-splash','--thinking','medium','--cwd',str(repo),'--retries','2','--timeout',str(seconds)]
 if not write:a+=['--plan']
 a+=[prompt]
(d/'argv.json').write_text(json.dumps(a,indent=2)); start=time.time();timed=False
with (d/'events.jsonl').open('w') as out,(d/'stderr.log').open('w') as err:
 p=subprocess.Popen(a,cwd=repo,env={**os.environ,'PWD':str(repo)},stdout=out,stderr=err,start_new_session=True)
 try:code=p.wait(timeout=seconds+20)
 except subprocess.TimeoutExpired:
  timed=True;os.killpg(p.pid,signal.SIGTERM)
  try:code=p.wait(timeout=10)
  except subprocess.TimeoutExpired:os.killpg(p.pid,signal.SIGKILL);code=p.wait()
texts=[];ids=set();errors=[]
for line in (d/'events.jsonl').read_text().splitlines():
 try:x=json.loads(line)
 except ValueError:continue
 if arm=='cline':
  if x.get('type')=='run_result':texts.append(x.get('text',''))
  if x.get('type')=='error':errors.append(x)
 else:
  if x.get('sessionID'):ids.add(x['sessionID'])
  if x.get('type')=='text':texts.append(x.get('part',{}).get('text',''))
  if x.get('type')=='error':errors.append(x)
(d/'response.txt').write_text('\n'.join(texts));(d/'execution.json').write_text(json.dumps({'argv':a,'start':start,'elapsed_seconds':time.time()-start,'exit_code':code,'timed_out':timed,'session_ids':sorted(ids),'errors':errors},indent=2))
print(arm,phase,'exit',code,'seconds',round(time.time()-start,1),'text_chars',sum(map(len,texts)))
