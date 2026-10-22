import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import {spawnSync} from 'node:child_process';

function python(program){
 const result=spawnSync('python3',['-c',program,path.resolve('.')],{encoding:'utf8',timeout:10000});
 assert.equal(result.status,0,result.stderr+result.stdout);return result.stdout;
}
test('natural completion harness import cannot launch inference or subprocesses',()=>{
 python(`import importlib.util,pathlib,subprocess,sys,urllib.request
root=pathlib.Path(sys.argv[1])
def forbidden(*args,**kwargs):raise RuntimeError('Import attempted external work')
for name in ('run','Popen','check_output'):setattr(subprocess,name,forbidden)
urllib.request.urlopen=forbidden
spec=importlib.util.spec_from_file_location('completion_fixture',root/'test/natural-completion.py')
m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
`);
});
test('completion screen reader retains surrounding text during cursor-only toast updates',()=>{
 python(`import importlib.util,pathlib,sys
root=pathlib.Path(sys.argv[1]);spec=importlib.util.spec_from_file_location('screen',root/'test/terminal-screen.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
raw='\\x1b[2J\\x1b[1;1HAgent usage\\x1b[2;1Hof 551 weighted tokens\\x1b[2;4H737'
screen=m.screen_text(raw,rows=3,columns=40)
assert 'Agent usage' in screen and 'of 737 weighted tokens' in screen,screen
assert '551' not in screen,screen
`);
});
test('natural fixture cleanup targets only the private process family',()=>{
 python(`import importlib.util,pathlib,sys
root=pathlib.Path(sys.argv[1]);spec=importlib.util.spec_from_file_location('fixture',root/'test/natural-completion.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
m.subprocess.check_output=lambda *a,**kw:'100 1\\n101 100\\n102 101\\n200 1\\n'
killed=[];m.os.kill=lambda pid,sig:killed.append(pid);m.os.waitpid=lambda *a:(100,0)
m.stop_private(100)
assert sorted(killed)==[100,101,102],killed
`);
});

test('natural CLI and TUI completion delivery includes rapid follow-ups, failure and interruption',
 {skip:process.env.OPENCODE_COMPLETION_TESTS!=='1',timeout:200000},()=>{
 const result=spawnSync('python3',['test/natural-completion.py'],{encoding:'utf8',timeout:190000,maxBuffer:2*1024*1024});
 assert.equal(result.status,0,result.stderr+result.stdout);
 const evidence=JSON.parse(result.stdout);
 assert.equal(evidence.cliRootReportWritten,true);
 assert.equal(evidence.cliReportMatchesDatabase,true);
 assert.ok(evidence.rapidGapMillis<2000);
 assert.equal(evidence.tuiToastRendered,true);
 assert.equal(evidence.finalReportMatchesDatabase,true);
 assert.equal(evidence.interruptedReportWritten,true);
 assert.equal(evidence.failedReportWritten,true);
 assert.ok(evidence.tuiCompletions.some(e=>e.type==='session.execution.interrupted'));
 assert.equal(evidence.tuiCompletions.filter(e=>e.type==='session.execution.succeeded').length,2);
 assert.ok(evidence.tuiSnapshots.every(s=>s.toastWithFinalTotals));
 assert.ok(fs.existsSync(path.resolve('artifacts/natural-completion.json')));
});
