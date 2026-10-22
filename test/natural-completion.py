"""Opt-in live local inference check. Importing this module never starts OpenCode."""
import json
import os
import pathlib
import pty
import re
import select
import signal
import sqlite3
import subprocess
import tempfile
import time
import urllib.request
import fcntl
import termios
import struct
import codecs
import copy
from importlib.util import module_from_spec, spec_from_file_location

ROOT = pathlib.Path(__file__).resolve().parent.parent
spec=spec_from_file_location('terminal_screen',ROOT/'test/terminal-screen.py');screen=module_from_spec(spec);spec.loader.exec_module(screen)

def raw_tokens(messages):
    raw={'input':0,'output':0,'reasoning':0,'cacheRead':0,'cacheWrite':0}
    for message in messages:
        tokens=message.get('tokens',{})
        for name in ('input','output','reasoning'):raw[name]+=tokens.get(name,0)
        raw['cacheRead']+=tokens.get('cache',{}).get('read',0)
        raw['cacheWrite']+=tokens.get('cache',{}).get('write',0)
    return raw

def stop_private(pid):
    """Bound cleanup to this fixture's process tree, including private server children."""
    listing=subprocess.check_output(['ps','-axo','pid=,ppid='],text=True)
    family={pid}; pairs=[tuple(map(int,line.split())) for line in listing.splitlines()]
    while True:
        added={child for child,parent in pairs if parent in family}-family
        if not added:break
        family.update(added)
    for child in sorted(family,reverse=True):
        try:os.kill(child,signal.SIGKILL)
        except ProcessLookupError:pass
    try:os.waitpid(pid,0)
    except ChildProcessError:pass

def private_run(args, **options):
    process=subprocess.Popen(args,stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True,start_new_session=True,**options)
    try:
        stdout,stderr=process.communicate(timeout=45)
        return subprocess.CompletedProcess(args,process.returncode,stdout,stderr)
    finally:
        if process.poll() is None:stop_private(process.pid)

def main():
    (ROOT/'artifacts').mkdir(exist_ok=True)
    settings = json.loads((pathlib.Path.home() / '.omlx/settings.json').read_text())
    endpoint = f"http://127.0.0.1:{settings['server']['port']}/v1"
    request = urllib.request.Request(endpoint + '/models', headers={'Authorization': 'Bearer ' + settings['auth']['api_key']})
    with urllib.request.urlopen(request, timeout=5) as response:
        models = json.load(response)['data']
    model = next(m['id'] for m in models if 'qwen' in m['id'].lower())
    with tempfile.TemporaryDirectory(prefix='opencode-natural-completion-') as temporary:
        base = pathlib.Path(temporary).resolve(); base.chmod(0o700)
        job = base / 'repo'; job.mkdir()
        for name in ('config', 'data', 'state', 'cache'):
            (base / name).mkdir()
        env = dict(os.environ, PWD=str(job), TERM='xterm-256color', XDG_CONFIG_HOME=str(base/'config'), XDG_DATA_HOME=str(base/'data'), XDG_STATE_HOME=str(base/'state'), XDG_CACHE_HOME=str(base/'cache'))
        for key in ('OPENCODE_CONFIG', 'OPENCODE_CONFIG_CONTENT', 'OPENCODE_CONFIG_DIR'):
            env.pop(key, None)
        secret = base / 'local.key'; secret.write_text(settings['auth']['api_key']); secret.chmod(0o600)
        ref = 'omlx/' + model
        config = {'warming':False, 'model':ref, 'providers':{'omlx':{'package':'@opencode/ai/providers/openai-compatible','settings':{'baseURL':endpoint,'apiKey':'{file:'+str(secret)+'}'},'models':{model:{'capabilities':{'tools':True,'input':['text'],'output':['text']},'limit':{'context':262144,'output':512}}}}}, 'agents':{name:{'model':ref} for name in ('build','general','explore','plan','compaction','title','summary')}}
        config['agents']['build'].update(system='Respond concisely to the user. Never call tools.', steps=2, permissions=[{'action':'*','resource':'*','effect':'deny'}])
        (job/'opencode.json').write_text(json.dumps(config))
        subprocess.run(['git','init','-b','completion-fixture'],cwd=job,env=env,capture_output=True,check=True)
        plugins = job/'.opencode/plugins'; plugins.mkdir(parents=True)
        (plugins/'agent-usage').symlink_to(ROOT/'plugin/agent-usage',target_is_directory=True)
        observer = plugins/'completion-observer'; observer.mkdir()
        events_file = base/'events.jsonl'
        stop_marker=base/'interrupt-next-execution'
        # Observe the genuine stream. No event replacement, emission or production setup wrapper.
        (observer/'server.js').write_text('import {Plugin} from "@opencode/plugin";import fs from "node:fs";export default Plugin.define({id:"completion-observer",setup(ctx){const c=new AbortController();fs.appendFileSync('+json.dumps(str(events_file))+',JSON.stringify({type:"observer.ready"})+"\\n");(async()=>{for await(const e of ctx.event.subscribe({signal:c.signal})){if(e.type.startsWith("session.execution."))fs.appendFileSync('+json.dumps(str(events_file))+',JSON.stringify({type:e.type,sessionID:(e.data??e.properties??{}).sessionID,at:Date.now()})+"\\n");if(e.type==="session.execution.started"&&fs.existsSync('+json.dumps(str(stop_marker))+')){fs.unlinkSync('+json.dumps(str(stop_marker))+');setTimeout(()=>{void ctx.session.interrupt({sessionID:(e.data??e.properties??{}).sessionID});},50);}}})().catch(()=>{});return()=>c.abort();}});')
        started = time.monotonic()
        result = private_run(['opencode','run','--standalone','--agent','build','--model',ref,'--format','json','Reply exactly COMPLETION_OK. Do not use tools.'],cwd=job,env=env)
        observed = [json.loads(line) for line in events_file.read_text().splitlines()] if events_file.exists() else []
        roots = [e['sessionID'] for e in observed if e['type']=='session.execution.succeeded']
        reports = base/'state/opencode-agent-setup/usage'
        evidence = {'model':ref,'cliExit':result.returncode,'elapsedSeconds':round(time.monotonic()-started,2),'observedEvents':observed,'reportFiles':[p.name for p in reports.glob('*')] if reports.exists() else [],'stderr':result.stderr[-1000:]}
        dbfile = base/'data/opencode/opencode.db'
        if dbfile.exists():
            with sqlite3.connect(dbfile) as db:
                evidence['assistantRecords'] = db.execute("select count(*) from session_message where type='assistant'").fetchone()[0]
        evidence['cliRootReportWritten'] = bool(roots) and (reports/(roots[-1]+'.json')).exists()
        if evidence['cliRootReportWritten']:
            report = json.loads((reports/(roots[-1]+'.json')).read_text())
            evidence['reportTurns'] = report['totals']['all']['turns']
            evidence['reportTokens'] = report['totals']['all']['raw']
            with sqlite3.connect(dbfile) as db:
                rows=[json.loads(r[0]) for r in db.execute("select data from session_message where session_id=? and type='assistant'",(roots[-1],))]
            evidence['cliReportMatchesDatabase']=evidence['reportTokens']==raw_tokens(rows)
        (ROOT/'artifacts/natural-completion.json').write_text(json.dumps(evidence,indent=2))
        assert result.returncode == 0 and roots and evidence['cliRootReportWritten'], 'Natural CLI completion did not write its usage report'
        assert evidence['cliReportMatchesDatabase'], 'CLI report missed final persisted tokens before shutdown'
        sid = roots[-1]
        # Watch the real TUI data events as well as the production toast rendering.
        tui_events = base/'tui-events.jsonl'
        (observer/'tui.tsx').write_text('import {Plugin} from "@opencode/plugin/tui";import fs from "node:fs";export default Plugin.define({id:"completion-observer",setup(ctx){fs.appendFileSync('+json.dumps(str(tui_events))+',JSON.stringify({type:"observer.ready"})+"\\n");const offs=["session.execution.succeeded", "session.execution.failed", "session.execution.interrupted"].map(type=>ctx.data.on(type,e=>fs.appendFileSync('+json.dumps(str(tui_events))+',JSON.stringify({type:e.type,sessionID:(e.data??e.properties??{}).sessionID,at:Date.now()})+"\\n")));return()=>offs.forEach(off=>off());}});')
        pid, fd = pty.fork()
        if pid == 0:
            os.chdir(job); os.environ.update(env)
            os.execvp('opencode', ['opencode','--standalone','--session',sid])
        fcntl.ioctl(fd, termios.TIOCSWINSZ, struct.pack('HHHH',45,180,0,0))
        transcript = '';decoder=codecs.getincrementaldecoder('utf-8')('replace')
        def pump(seconds=.1):
            nonlocal transcript
            ready,_,_ = select.select([fd],[],[],seconds)
            if ready:
                try: transcript += decoder.decode(os.read(fd,262144))
                except OSError: pass
        def wait_for(predicate, timeout=15):
            end=time.monotonic()+timeout
            while time.monotonic()<end:
                pump()
                if predicate(): return
            raise AssertionError('Timed out waiting for natural TUI completion')
        def messages():
            with sqlite3.connect(dbfile) as db:
                return [json.loads(r[0]) for r in db.execute("select data from session_message where session_id=? and type='assistant' order by seq",(sid,))]
        def current_report():
            try:return json.loads((reports/(sid+'.json')).read_text())
            except (FileNotFoundError,ValueError):return {}
        try:
            wait_for(lambda:tui_events.exists())
            # Wait for initial session synchronization before typing.
            for _ in range(10):pump()
            snapshots=[]
            for number in (2,3):
                os.write(fd,b'Reply exactly COMPLETION_OK. Do not use tools.');pump(.1);os.write(fd,b'\r')
                wait_for(lambda:len(messages())>=number and current_report().get('totals',{}).get('all',{}).get('turns')==number)
                # The toast should describe the final, committed totals of this execution.
                report=current_report();needle='of '+format(report['totals']['all']['weighted'],',')+' weighted tokens'
                end=time.monotonic()+1
                while time.monotonic()<end and needle not in re.sub(r'\s+',' ',screen.screen_text(transcript)):pump()
                rendered=screen.screen_text(transcript)
                snapshots.append({'turns':number,'toastWithFinalTotals':needle in re.sub(r'\s+',' ',rendered),'weighted':report['totals']['all']['weighted']})
            # The public native interrupt API stops a real execution; no synthetic event is emitted.
            previous_mtime=(reports/(sid+'.json')).stat().st_mtime_ns
            stop_marker.touch()
            before_events=sum(1 for line in events_file.read_text().splitlines() if 'session.execution.started' in line)
            os.write(fd,b'Count from 1 to 100000, one number per line. Do not use tools.');pump(.1);os.write(fd,b'\r')
            wait_for(lambda:sum(1 for line in events_file.read_text().splitlines() if 'session.execution.started' in line)>before_events)
            wait_for(lambda:any('session.execution.interrupted' in line for line in tui_events.read_text().splitlines()))
            wait_for(lambda:(reports/(sid+'.json')).stat().st_mtime_ns>previous_mtime and current_report().get('totals',{}).get('all',{}).get('turns')==len(messages()))
            evidence['interruptedReportWritten']=True
            (ROOT/'artifacts/natural-completion-tui.txt').write_text(screen.screen_text(transcript))
            evidence['tuiCompletions']=[json.loads(line) for line in tui_events.read_text().splitlines() if 'session.execution.' in line]
            evidence['tuiSnapshots']=snapshots
            successes=[e for e in evidence['tuiCompletions'] if e['type']=='session.execution.succeeded']
            evidence['rapidGapMillis']=successes[1]['at']-successes[0]['at'] if len(successes)==2 else None
            evidence['tuiToastRendered']='Agent usage' in transcript and 'Routing:' in transcript
            raw=raw_tokens(messages())
            evidence['finalReportMatchesDatabase']=current_report()['totals']['all']['raw']==raw
            evidence['finalTokens']=raw
        finally:
            (ROOT/'artifacts/natural-completion-tui.txt').write_text(screen.screen_text(transcript))
            (ROOT/'artifacts/natural-completion.json').write_text(json.dumps(evidence,indent=2))
            stop_private(pid);os.close(fd)
        bad=base/'invalid.key';bad.write_text('intentionally-invalid-completion-fixture');bad.chmod(0o600)
        failure_config=copy.deepcopy(config);failure_config['providers']['omlx']['settings']['apiKey']='{file:'+str(bad)+'}'
        (job/'opencode.json').write_text(json.dumps(failure_config))
        failed=private_run(['opencode','run','--standalone','--agent','build','--model',ref,'--format','json','Reply OK.'],cwd=job,env=env)
        terminal=[json.loads(line) for line in events_file.read_text().splitlines() if 'session.execution.failed' in line]
        evidence['failedExit']=failed.returncode;evidence['failedEvents']=terminal
        evidence['failedReportWritten']=bool(terminal) and (reports/(terminal[-1]['sessionID']+'.json')).exists()
        (ROOT/'artifacts').mkdir(exist_ok=True)
        (ROOT/'artifacts/natural-completion.json').write_text(json.dumps(evidence,indent=2))
        print(json.dumps(evidence,indent=2))
        assert result.returncode == 0, 'Local completion failed'
        assert roots, 'Natural succeeded event not delivered'
        assert evidence['cliRootReportWritten'], 'Natural CLI completion did not write its usage report'
        assert sum(e['type']=='session.execution.succeeded' for e in evidence['tuiCompletions'])==2, 'Natural success events did not reach TUI'
        assert evidence['interruptedReportWritten'], 'Natural interruption report missing'
        assert evidence['failedReportWritten'], 'Natural failure event/report missing'
        assert evidence['rapidGapMillis'] is not None and evidence['rapidGapMillis']<2000, 'Rapid follow-up check inconclusive: local completions were not under two seconds apart'
        assert evidence['tuiToastRendered'], 'Natural TUI completion did not render usage toast'
        assert all(s['toastWithFinalTotals'] for s in evidence['tuiSnapshots']), 'TUI completion toast missing final totals'
        assert evidence['finalReportMatchesDatabase'], 'Report missed final persisted tokens'

if __name__ == '__main__':
    main()
