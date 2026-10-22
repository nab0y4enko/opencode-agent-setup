import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';

test('benchmark reconciliation independently sums native counters and rejects stale usage or incomplete execution',()=>{
 const code=String.raw`import importlib.util,json,sqlite3
spec=importlib.util.spec_from_file_location('comparison','scripts/compare-baselines.py');m=importlib.util.module_from_spec(spec);spec.loader.exec_module(m)
db=sqlite3.connect(':memory:')
db.execute('CREATE TABLE session_v2(id,parent_id,agent,model,time_idle,idle_outcome)')
db.execute('CREATE TABLE session_message(session_id,type,seq,data)')
db.execute('INSERT INTO session_v2 VALUES(?,?,?,?,?,?)',('root',None,'build','{"providerID":"openai","id":"fixture"}',123,'succeeded'))
db.execute('INSERT INTO session_message VALUES(?,?,?,?)',('root','assistant',1,json.dumps({'tokens':{'input':10,'output':2,'reasoning':3,'cache':{'read':4,'write':5}},'cost':0})))
db.execute('INSERT INTO session_message VALUES(?,?,?,?)',('root','compaction',2,json.dumps({'tokens':{'input':6,'output':7,'reasoning':8,'cache':{'read':9,'write':10}}})))
db.execute('INSERT INTO session_message VALUES(?,?,?,?)',('root','user',3,json.dumps({'tokens':{'input':999}})))
tokens={'input':16,'output':9,'reasoning':11,'cacheRead':13,'cacheWrite':15}
report={'usage':{'root':{'id':'root'},'sessions':[{'id':'root','tokens':tokens.copy()}],'totals':{'all':{'raw':tokens.copy()}}}}
valid=m.reconcile(report,db)
def rejected():
 try: m.reconcile(report,db);return False
 except AssertionError: return True
db.execute("UPDATE session_v2 SET agent='orchestrator'")
row=json.loads(db.execute("SELECT data FROM session_message WHERE type='assistant'").fetchone()[0])
row['content']=[{'type':'tool','name':'glob','state':{'status':'completed'}}]
db.execute("UPDATE session_message SET data=? WHERE type='assistant'",(json.dumps(row),))
readonly_allowed=m.reconcile(report,db)['sessions']['root']['tools']=={'glob':1}
row['content'][0]['name']='shell'
db.execute("UPDATE session_message SET data=? WHERE type='assistant'",(json.dumps(row),));shell_rejected=rejected()
row['content']=[];db.execute("UPDATE session_message SET data=? WHERE type='assistant'",(json.dumps(row),))
report['usage']['sessions'][0]['tokens']['input']=15;stale=rejected()
report['usage']['sessions'][0]['tokens']['input']=16
db.execute("UPDATE session_v2 SET time_idle=NULL,idle_outcome=NULL");incomplete=rejected()
print(json.dumps({'valid':valid,'stale':stale,'incomplete':incomplete,'readonlyAllowed':readonly_allowed,'shellRejected':shell_rejected}))`;
 const r=spawnSync('python3',['-c',code],{encoding:'utf8',timeout:10000});
 assert.equal(r.status,0,r.stderr+r.stdout);
 const result=JSON.parse(r.stdout);
 assert.deepEqual(result.valid.raw,{input:16,output:9,reasoning:11,cacheRead:13,cacheWrite:15});
 assert.equal(result.valid.actual_dollar_cost,null);
 assert.deepEqual(result.valid.recorded_cost_values,[null,0]);
 assert.equal(result.stale,true);assert.equal(result.incomplete,true);
 assert.equal(result.readonlyAllowed,true);assert.equal(result.shellRejected,true);
});
