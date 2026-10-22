import test from 'node:test';
import assert from 'node:assert/strict';
import path from 'node:path';
import {spawnSync} from 'node:child_process';

// Opt-in native check: private server, isolated XDG state, fixture sessions only.
// The sole text submitted to the TUI is the registered /usage command.
test('native plugin discovery, TUI rendering and server completion report without inference',
 {skip:process.env.OPENCODE_PLUGIN_TESTS!=='1',timeout:40000},()=>{
 const program=String.raw`
import os,json,pathlib,subprocess,time,pty,select,signal,fcntl,termios,struct,re,sqlite3,tempfile
repo=pathlib.Path(__import__('sys').argv[1]);clean=lambda text:re.sub(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))','',text)
with tempfile.TemporaryDirectory(prefix='agent-usage-runtime-') as temporary:
 base=pathlib.Path(temporary).resolve();job=base/'repo';job.mkdir()
 for name in ('config','data','state','cache'):(base/name).mkdir()
 env=dict(os.environ,PWD=str(job),TERM='xterm-256color',XDG_CONFIG_HOME=str(base/'config'),XDG_DATA_HOME=str(base/'data'),XDG_STATE_HOME=str(base/'state'),XDG_CACHE_HOME=str(base/'cache'))
 subprocess.run(['git','init','-b','plugin-fixture'],cwd=job,capture_output=True,check=True)
 plugins=job/'.opencode/plugins';plugins.mkdir(parents=True)
 (plugins/'agent-usage').symlink_to(repo/'plugin/agent-usage',target_is_directory=True)
 (job/'opencode.json').write_text(json.dumps({'warming':False}))
 ids=[]
 for title in ['Older originating root','Newer unrelated root']:
  result=subprocess.run(['opencode','api','--standalone','session.create','--data',json.dumps({'title':title,'location':{'directory':str(job)}})],cwd=job,env=env,capture_output=True,text=True,timeout=10)
  if result.returncode:raise RuntimeError(result.stderr[-1000:])
  value=json.loads(result.stdout);ids.append(value.get('data',value)['id'])
 fixture=plugins/'agent-usage-event-fixture';fixture.mkdir()
 source=(repo/'plugin/agent-usage/server.js').as_uri()
 (fixture/'server.js').write_text('import {Plugin} from "@opencode/plugin";\nimport usage from '+json.dumps(source)+';\nexport default Plugin.define({id:"agent-usage-event-fixture",async setup(ctx){return usage.setup({...ctx,event:{subscribe:async function*(){yield {type:"session.execution.succeeded",data:{sessionID:'+json.dumps(ids[0])+'}};}}});}});\n')
 pid,fd=pty.fork()
 if pid==0:
  os.chdir(job);os.environ.update(env);os.execvp('opencode',['opencode','--standalone','--session',ids[0]])
 fcntl.ioctl(fd,termios.TIOCSWINSZ,struct.pack('HHHH',45,150,0,0))
 transcript=''
 def read(seconds):
  global transcript
  end=time.monotonic()+seconds
  while time.monotonic()<end:
   ready,_,_=select.select([fd],[],[],.1)
   if ready:
    try:data=os.read(fd,262144).decode(errors='replace')
    except OSError:return
    transcript+=data
 try:
  read(5);os.write(fd,b'/usage');read(.5);os.write(fd,b'\r');read(4)
 finally:
  try:os.kill(pid,signal.SIGTERM)
  except ProcessLookupError:pass
  try:os.waitpid(pid,0)
  except ChildProcessError:pass
  os.close(fd)
 text=clean(transcript);reportdir=base/'state/opencode-agent-setup/usage';reportfile=reportdir/(ids[0]+'.json')
 usage=json.loads(reportfile.read_text()) if reportfile.exists() else {}
 with sqlite3.connect(base/'data/opencode/opencode.db') as db:
  messages=db.execute('select count(*) from session_message').fetchone()[0]
 result={'tuiUsageRendered':'Agent usage' in text,'originIDRendered':ids[0] in text,'originTitleRendered':'Older originating root' in text,'routingRendered':'Routing: Model class unknown' in text,'reportWritten':bool(usage),'reportRootMatches':usage.get('root',{}).get('id')==ids[0],'reportRouting':usage.get('routing',{}).get('status'),'textAndLatestWritten':(reportdir/(ids[0]+'.txt')).exists() and (reportdir/'latest.txt').exists(),'messageCount':messages,'completionSource':'Synthetic iterable passed to production server.setup in native Bun runtime','limitation':'Natural model-completion event delivery and visible newest/back interaction are not asserted; navigation helper regressions cover origin/back/newest.'}
 (repo/'artifacts').mkdir(exist_ok=True);(repo/'artifacts/review-plugin-runtime.json').write_text(json.dumps(result,indent=2));print(json.dumps(result))
`;
 const result=spawnSync('python3',['-c',program,path.resolve('.')],{encoding:'utf8',timeout:35000,maxBuffer:1024*1024});
 assert.equal(result.status,0,result.stderr+result.stdout);
 const evidence=JSON.parse(result.stdout);
 for(const key of ['tuiUsageRendered','originIDRendered','originTitleRendered','routingRendered','reportWritten','reportRootMatches','textAndLatestWritten'])assert.equal(evidence[key],true,`${key}: ${result.stdout}`);
 assert.equal(evidence.reportRouting,'unknown');assert.equal(evidence.messageCount,0);
});
