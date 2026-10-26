from pathlib import Path
import sqlite3,json,csv,hashlib,datetime
r=Path(__file__).parent;a=r/'opencode';native=a/'native-records';native.mkdir(exist_ok=True)
c=sqlite3.connect('file:'+str(Path.home()/'.local/share/opencode/opencode.db')+'?mode=ro',uri=True);c.row_factory=sqlite3.Row
sessions=[dict(s) for s in c.execute('select * from session_v2 where directory=? order by time_created',(str(a/'repo'),))]
assert sessions
ids={s['id'] for s in sessions};assert sum(s['parent_id'] is None for s in sessions)==1
assert all(s['parent_id'] is None or s['parent_id'] in ids for s in sessions)
requests=[];session_summary=[];totals={k:dict(input=0,output=0,reasoning=0,cache_read=0,cache_write=0,total=0) for k in ['cloud','local','unknown']}
for s in sessions:
 rows=[dict(x) for x in c.execute('select * from session_message where session_id=? order by seq',(s['id'],))]
 with (native/(s['id']+'.jsonl')).open('w') as f:
  f.write(json.dumps({'session':s})+'\n')
  for row in rows:f.write(json.dumps(row)+'\n')
 turn=0;known=0;pending=[]
 for row in rows:
  q=json.loads(row['data'])
  if row['type']=='user':turn+=1
  if row['type']!='assistant':continue
  t=q.get('tokens') or {};model=q.get('model') or {};tier='local' if model.get('providerID')=='omlx' else 'cloud' if model.get('providerID')=='openai' else 'unknown'
  counts={k:t.get(k,0) for k in ['input','output','reasoning']};counts.update(cache_read=(t.get('cache') or {}).get('read',0),cache_write=(t.get('cache') or {}).get('write',0));counts['total']=sum(counts.values());known+=counts['total']
  for k,v in counts.items():totals[tier][k]+=v
  if not q.get('finish'):pending.append(row['id'])
  requests.append(dict(session=s['id'],message=row['id'],seq=row['seq'],agent=q.get('agent'),turn=turn,model=model,tier=tier,finish=q.get('finish'),**counts))
 native_total=sum(s.get('tokens_'+k) or 0 for k in ['input','output','reasoning','cache_read','cache_write'])
 session_summary.append(dict(id=s['id'],parent=s['parent_id'],agent=s['agent'],model=s['model'],native_total=native_total,assistant_total=known,maintenance_gap=native_total-known,pending_assistant_messages=pending,time_created=s['time_created'],time_idle=s['time_idle'],outcome=s['idle_outcome']))
summary={'snapshot_utc':datetime.datetime.now(datetime.timezone.utc).isoformat(),'scope':'All saved OpenCode assistant usage in the root and complete child session tree; output and reasoning are separate native fields; cached input is added once. Maintenance gaps and unfinished assistant records are explicit. External Codex host usage is in host-cloud-snapshot.json.','totals':totals,'sessions':session_summary,'request_count':len(requests),'unattributed_maintenance_total':sum(x['maintenance_gap'] for x in session_summary)}
(a/'usage-audit.json').write_text(json.dumps(summary,indent=2));(a/'requests.json').write_text(json.dumps(requests,indent=2))
with (a/'requests.csv').open('w') as f:
 w=csv.DictWriter(f,fieldnames=list(requests[0]));w.writeheader();w.writerows(requests)
(native/'sha256.json').write_text(json.dumps({p.name:hashlib.sha256(p.read_bytes()).hexdigest() for p in native.glob('*.jsonl')},indent=2))
print(json.dumps(summary,indent=2))
