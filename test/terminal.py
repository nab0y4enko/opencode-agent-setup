"""Real PTY smoke tests; Python standard library only. No model requests."""
import os, pty, select, re, tempfile, time, signal, json
from pathlib import Path
ROOT=Path(__file__).resolve().parent.parent
ANSI=re.compile(r'\x1b(?:\[[0-?]*[ -/]*[@-~]|\][^\x07]*(?:\x07|\x1b\\))')
def run(mode):
    directory=tempfile.mkdtemp(prefix='opencode-wizard-')
    config=Path(directory)/'opencode.json'
    pid,fd=pty.fork()
    if pid==0:
        os.chdir(ROOT)
        os.execvp('node',['node','bin/setup.js','--config',str(config),'--dry-run'])
    pending=''; transcript=''
    def expect(text,answer):
        nonlocal pending,transcript
        end=time.monotonic()+20
        while time.monotonic()<end:
            clean=ANSI.sub('',pending)
            if text in clean:
                pending='';os.write(fd,answer);return
            ready,_,_=select.select([fd],[],[],0.1)
            if ready:
                try: data=os.read(fd,65536).decode(errors='replace')
                except OSError:break
                if not data:break
                pending+=data;transcript+=data
        raise AssertionError('Missing prompt '+text+'\n'+ANSI.sub('',transcript)[-3000:])
    try:
        expect('Orchestration profile',b'\x1b[B\r') # native roles
        expect('cloud-reviewer',b'n\r')
        if mode=='local-dry-run':
            expect('Model providers',b'\x1b[B\x1b[B\r')
            expect('Existing local API URL',b'\r')
            expect('Local API key source',b'\r')
            expect('Choose the actual local Qwen model',b'\r')
            expect('Model providers',b'\r')
        else:
            expect('Model providers',b'\r')
        if mode=='cancel':
            expect('build: model',b'\x03')
        else:
            for agent in ['build','plan','general','explore','compaction','title','summary']:
                expect(agent+': model',b'\r')
                if agent in ['build','plan','general','explore']:
                    expect('System instructions',b'\x1b[B\r' if agent=='general' else b'\r')
        end=time.monotonic()+20;status=None
        while time.monotonic()<end:
            done,value=os.waitpid(pid,os.WNOHANG)
            if done:status=os.waitstatus_to_exitcode(value);break
            ready,_,_=select.select([fd],[],[],0.1)
            if ready:
                try:transcript+=os.read(fd,65536).decode(errors='replace')
                except OSError: pass
        assert status==(1 if mode=='cancel' else 0),(status,ANSI.sub('',transcript)[-3000:])
        assert not config.exists(),'Wizard wrote config despite cancel/dry-run'
        if mode!='cancel':
            clean=ANSI.sub('',transcript);assert 'assigned scope' in clean;assert 'No configuration changes saved.' in clean
        return {'mode':mode,'exit':status,'config_created':config.exists(),'passed':True}
    finally:
        try:os.kill(pid,signal.SIGTERM)
        except ProcessLookupError:pass
        os.close(fd)
if __name__=='__main__':print(json.dumps([run('dry-run'),run('cancel'),run('local-dry-run')],indent=2))
