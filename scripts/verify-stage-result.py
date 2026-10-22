"""Independently enforce the mixed-model smoke test's acceptance contract."""
import json,re,sys
r=json.load(open(sys.argv[1]));errors=[]
def require(condition,message):
 if not condition:errors.append(message)
require(r.get('opencode_exit')==0,'OpenCode failed')
require(r.get('independent_test_exit')==0 and re.search(r'Ran 4 tests\b',r.get('tests','')) and re.search(r'^OK\s*$',r.get('tests',''),re.M),'Independent four-test run missing or failed')
commits=r.get('commits',[])
require(len(commits)==2,'Expected exactly two completed stage commits')
if len(commits)==2:
 require(commits[0].get('sha')!=commits[1].get('sha'),'Stage commits are not distinct')
 require(sorted(commits[0].get('files',[]))==['fixture.py'],'Stage 1 committed unexpected files')
 require(sorted(commits[1].get('files',[]))==['fixture.py','test_fixture.py'],'Stage 2 committed unexpected files')
require(r.get('status')=='','Worktree is dirty')
dispatches=r.get('dispatches',[])
require([d.get('agent') for d in dispatches]==['general','build','cloud-reviewer'],'Expected General -> Build -> cloud-reviewer dispatches')
require(all(d.get('background') is False for d in dispatches),'A dispatch was not foreground')
if len(dispatches)==3:
 require(dispatches[0].get('model',{}).get('providerID')=='omlx','General did not use local Qwen')
 for d in dispatches[1:]:
  require(d.get('model',{}).get('providerID')=='openai' and d.get('model',{}).get('id')=='gpt-6.1-sol' and d.get('model',{}).get('variant')=='high',d.get('agent','agent')+' did not use OpenAI Sol high')
review_text=re.sub(r'<[^>]+>','',r.get('review','')).replace('**','').replace('`','')
require(bool(re.search(r'^\s*(?:VERDICT\s*[:\-]?\s*)?PASS\b',review_text,re.I|re.M)),'Independent reviewer did not give a PASS verdict')
usage=r.get('usage')
require(bool(usage),'Usage report missing; token measurement did not run')
if usage:
 by_agent={a['agent']:a for a in usage.get('byAgent',[])}
 require(by_agent.get('general',{}).get('class')=='local','Usage report shows General tokens were not local')
 for agent in ['build','cloud-reviewer']:require(by_agent.get(agent,{}).get('class')=='cloud',f'Usage report shows {agent} tokens were not cloud')
 require(usage.get('totals',{}).get('local',{}).get('weighted',0)>0,'No local tokens recorded')
 require(usage.get('shares',{}).get('cloudWeighted',1)<1,'All weighted tokens were cloud')
 require(not any(d.get('background') for d in usage.get('dispatches',[])),'Usage report shows a background dispatch')
print(json.dumps({'passed':not errors,'failures':errors},indent=2));sys.exit(1 if errors else 0)
