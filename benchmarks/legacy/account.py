from pathlib import Path
import sqlite3,json,sys,re,datetime
r=Path(__file__).parent;arm=sys.argv[1];out=[]
if arm=='opencode':
 c=sqlite3.connect('file:'+str(Path.home()/'.local/share/opencode/opencode.db')+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
else:
 c=sqlite3.connect('file:'+str(Path.home()/'.cline/data/db/sessions.db')+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
for d in sorted((r/arm).iterdir()):
 if not (d/'execution.json').exists():continue
 e=json.loads((d/'execution.json').read_text());a=[json.loads(x) for x in (d/'events.jsonl').read_text().splitlines() if x.startswith('{')];row={'phase':d.name,'exit_code':e['exit_code'],'seconds':e['elapsed_seconds'],'sessions':[],'cloud':0,'local':0,'unattributed':0}
 if arm=='opencode':
  ids=e['session_ids']; pending=list(ids)
  while pending:
   sid=pending.pop(0)
   for child in c.execute('select id from session_v2 where parent_id=?',(sid,)):
    if child['id'] not in ids:ids.append(child['id']);pending.append(child['id'])
  for sid in ids:
   session=dict(c.execute('select id,model,parent_id,tokens_input,tokens_output,tokens_reasoning,tokens_cache_read,tokens_cache_write from session_v2 where id=?',(sid,)).fetchone());msgs=[];known=0
   for m in c.execute("select id,data from session_message where session_id=? and type='assistant'",(sid,)):
    q=json.loads(m['data']);t=q.get('tokens') or {};n=sum(t.get(k,0) for k in ['input','output','reasoning'])+sum((t.get('cache') or {}).values());tier='local' if (q.get('model') or {}).get('providerID')=='omlx' else 'cloud';row[tier]+=n;known+=n;msgs.append({'id':m['id'],'model':q.get('model'),'tokens':t,'total':n})
   native=sum(session[k] or 0 for k in ['tokens_input','tokens_output','tokens_reasoning','tokens_cache_read','tokens_cache_write']);gap=native-known;row['unattributed']+=gap;row['sessions'].append({'native':session,'assistant_usage':msgs,'native_total':native,'maintenance_gap':gap})
 else:
  res=[x for x in a if x.get('type')=='run_result'];usage=[x['event'] for x in a if x.get('event',{}).get('type')=='usage'];n=sum(x.get('inputTokens',0)+x.get('outputTokens',0) for x in usage)
  if res:
   u=res[-1]['aggregateUsage'];assert n==u['inputTokens']+u['outputTokens'];tier='local' if res[-1]['model']['provider']=='openai-compatible' else 'cloud';row[tier]=n
  else:
   provider=e['argv'][e['argv'].index('--provider')+1];tier='local' if provider=='openai-compatible' else 'cloud';row[tier]=n;row['usage_incomplete']=True
  row['usage_events']=usage
  for s in c.execute('select session_id,provider,model,started_at,ended_at,parent_session_id,messages_path from sessions where cwd=?',(str(r/arm/'repo'),)):
   start=datetime.datetime.fromisoformat(s['started_at'].replace('Z','+00:00')).timestamp()
   if e['start']-2<=start<=e['start']+e['elapsed_seconds']+2:
    sd=dict(s);row['sessions'].append(sd)
    if sd['messages_path'] and Path(sd['messages_path']).exists():(d/'native-messages.json').write_text(Path(sd['messages_path']).read_text())
 out.append(row)
(r/arm/'accounting.json').write_text(json.dumps(out,indent=2))
print(json.dumps([{k:v for k,v in x.items() if k not in ['sessions','usage_events']} for x in out],indent=2))
