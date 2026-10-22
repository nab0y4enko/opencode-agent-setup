// Pure token/model/agent usage analysis shared by the CLI, the smoke tests and the OpenCode plugin.
// No Node-only or Bun-only imports here: this file must load in Node, in Bun (server plugin) and in the TUI.
export const CACHE_READ_WEIGHT=0.1; // reporting heuristic; actual billing comes from message costs or model rates
const WORKER_AGENTS=['general','explore','scout','title','summary'];
const NO_DELEGATION_AGENTS=['general','explore','scout','cloud-reviewer'];
const DEFAULT_STEPS={general:24,explore:12};
const LOCAL_PROVIDERS=['omlx','ollama','lmstudio','llama.cpp','mlx','vllm'];
const CLOUD_PROVIDERS=['openai','anthropic','google','google-vertex','amazon-bedrock','azure','azure-cognitive-services','openrouter','github-copilot','deepseek','groq','mistral','xai','cerebras','togetherai','fireworks-ai','opencode'];
const zero=()=>({input:0,output:0,reasoning:0,cacheRead:0,cacheWrite:0});
const add=(a,b)=>{for(const k of Object.keys(a))a[k]+=b[k]??0;return a;};
export const weighted=t=>t.input+t.output+t.reasoning+t.cacheWrite+Math.round(t.cacheRead*CACHE_READ_WEIGHT);
export const modelRef=m=>m?`${m.providerID}/${m.id??m.modelID}${m.variant?'#'+m.variant:''}`:'unknown';
export const modelKey=m=>m?`${m.providerID}/${m.id??m.modelID}`:'unknown';
export const pct=x=>`${Math.round(x*100)}%`;
export const num=n=>n===null||n===undefined?'-':Number(n).toLocaleString('en-US');
export const money=c=>c===null||c===undefined?'unpriced':`$${c.toFixed(4)}`;
/** Epoch milliseconds from a number, Date, Effect DateTime ({epochMillis}) or ISO string. */
export function toMillis(v){
 if(v===null||v===undefined)return null;
 if(typeof v==='number')return v;
 if(v instanceof Date)return v.getTime();
 if(typeof v==='object'&&typeof v.epochMillis==='number')return v.epochMillis;
 if(typeof v==='string'){const t=Date.parse(v);return Number.isNaN(t)?null:t;}
 return null;
}
const ref=m=>m?{providerID:m.providerID,id:m.id??m.modelID,variant:m.variant}:null;

/** Normalizes one stored or SDK assistant message into the shape analyze() consumes. Prompts and tool output are dropped. */
export function normalizeMessage(sessionID,d,fallback={}){
 if(!d||typeof d!=='object')return null;
 const type=d.type??fallback.type??d.role;
 if(type&&type!=='assistant'&&type!=='compaction')return null;
 const t=d.tokens??{};
 const compaction=d.summary===true||d.type==='compaction'||fallback.type==='compaction'||d.agent==='compaction';
 const error=!!d.error||d.finish==='error'||['error','retry'].includes(d.status?.type??d.status)||!!d.retry||(d.content??[]).some(p=>p?.type==='retry'||p?.state?.status==='error');
 const dispatches=[];
 for(const part of d.content??[]){
  if(part?.type!=='tool'||part.name!=='subagent')continue;
  const input=part.state?.input??{};
  dispatches.push({id:part.id??null,agent:input.agent??null,background:!!input.background,sessionID:part.state?.metadata?.sessionID??null,description:input.description??null,status:part.state?.status??null});
 }
 return {id:d.id??fallback.id??null,sessionID,agent:d.agent??(compaction?'compaction':null),model:ref(d.model),created:toMillis(d.time?.created)??fallback.created??0,completed:toMillis(d.time?.completed)??toMillis(d.time?.created)??fallback.completed??0,finish:d.finish??null,cost:Number(d.cost??0),
  compaction,error,dispatches,
  tokens:{input:Number(t.input??0),output:Number(t.output??0),reasoning:Number(t.reasoning??0),cacheRead:Number(t.cache?.read??0),cacheWrite:Number(t.cache?.write??0)}};
}
/** Normalizes an SDK Session.Info (as the TUI data layer exposes it). */
export function normalizeSession(s){
 return {id:s.id,parentID:s.parentID??s.parent_id??null,agent:s.agent??null,model:ref(s.model),directory:s.location?.directory??s.directory??'',title:s.title??'',created:toMillis(s.time?.created)??s.created??0,updated:toMillis(s.time?.updated)??s.updated??0,compacting:null};
}
/** Builds an analyze() tree from SDK-shaped sessions and messages (TUI data layer), rooted at rootId. */
export function treeFrom(sessions,messagesBySession,rootId){
 const all=sessions.map(normalizeSession);const byParent=new Map();
 for(const s of all){if(!byParent.has(s.parentID))byParent.set(s.parentID,[]);byParent.get(s.parentID).push(s);}
 const root=all.find(s=>s.id===rootId);if(!root)return null;
 const tree=[];const queue=[root];
 while(queue.length){const s=queue.shift();tree.push(s);queue.push(...(byParent.get(s.id)??[]).sort((a,b)=>a.created-b.created));}
 const messages=[];
 for(const s of tree){
  const list=typeof messagesBySession==='function'?messagesBySession(s.id):messagesBySession?.[s.id];
  for(const raw of list??[]){
   if(raw?.type&&raw.type!=='assistant'&&raw.type!=='compaction')continue;
   const m=normalizeMessage(s.id,raw);if(m)messages.push(m);
  }
 }
 return {root,sessions:tree,messages};
}

function classify(model,localProviders,cloudProviders){
 if(!model?.providerID)return 'unknown';
 if(localProviders.includes(model.providerID))return 'local';
 return cloudProviders.includes(model.providerID)?'cloud':'unknown';
}
function priceFor(tokens,rate){
 if(!rate)return null;
 const r={reasoning:rate.output,cacheWrite:rate.input,cacheRead:rate.input,...rate};
 let cost=0;
 for(const k of Object.keys(tokens)){
  if(!tokens[k])continue;
  if(!Number.isFinite(r[k])||r[k]<0)return null;
  cost+=tokens[k]*r[k]/1e6;
 }
 return cost;
}
const uniqueValue=(values,fallback='unknown')=>{const all=[...new Set(values)];return all.length===1?all[0]:all.length?'mixed':fallback;};
function sum(rows){
 const out={sessions:new Set(rows.map(r=>r.sessionID??r.id)).size,turns:0,raw:zero(),weighted:0,cost:0};
 for(const r of rows){out.turns+=r.turns;add(out.raw,r.tokens);out.weighted+=r.weighted;out.cost=out.cost===null||r.cost===null?null:out.cost+r.cost;}
 return out;
}

export function analyze(tree,{pricing={},steps=DEFAULT_STEPS,localProviders=LOCAL_PROVIDERS,cloudProviders=CLOUD_PROVIDERS}={}){
 const sessions=new Map();
 for(const s of tree.sessions)sessions.set(s.id,{...s,depth:0,children:[],dispatches:[],buckets:new Map()});
 for(const s of sessions.values()){
  let p=sessions.get(s.parentID),d=0;const seen=new Set([s.id]);
  while(p&&!seen.has(p.id)){seen.add(p.id);d++;p=sessions.get(p.parentID);}s.depth=d;
  if(sessions.has(s.parentID))sessions.get(s.parentID).children.push(s.id);
 }
 const bucketFor=(s,agent,model)=>{
  const key=JSON.stringify([agent,modelRef(model)]);
  if(!s.buckets.has(key))s.buckets.set(key,{id:s.id,sessionID:s.id,parentID:s.parentID,title:s.title,depth:s.depth,agent,model:modelRef(model),modelKey:modelKey(model),class:classify(model,localProviders,cloudProviders),turns:0,tokens:zero(),weighted:0,cost:0,errors:0,compactions:0,first:null,last:null});
  return s.buckets.get(key);
 };
 for(const m of tree.messages){
  const s=sessions.get(m.sessionID);if(!s)continue;
  const b=bucketFor(s,m.agent??(m.compaction?'compaction':'unknown'),m.model);
  b.turns++;add(b.tokens,m.tokens);b.weighted+=weighted(m.tokens);
  if(m.compaction)b.compactions++;
  if(m.error||m.finish==='error')b.errors++;
  const cost=m.cost>0?m.cost:b.class==='local'?0:priceFor(m.tokens,pricing[modelKey(m.model)]);
  b.cost=b.cost===null||cost===null?null:b.cost+cost;
  b.first=b.first===null?m.created:Math.min(b.first,m.created);b.last=b.last===null?m.completed:Math.max(b.last,m.completed);
  for(const d of m.dispatches??[])s.dispatches.push({...d,parent:s.id,messageID:m.id,at:m.created});
 }
 const list=[...sessions.values()];
 for(const s of list){
  if(!s.buckets.size)bucketFor(s,s.agent??'unknown',s.model);
  s.breakdown=[...s.buckets.values()].map(b=>({...b,elapsedSeconds:b.first===null?0:Math.max(0,Math.round((b.last-b.first)/1000))}));
  const total=sum(s.breakdown);s.tokens=total.raw;s.weighted=total.weighted;s.turns=total.turns;s.cost=total.cost;
  s.agent=uniqueValue(s.breakdown.map(b=>b.agent));s.modelRef=uniqueValue(s.breakdown.map(b=>b.model));s.class=uniqueValue(s.breakdown.map(b=>b.class));
  s.errors=s.breakdown.reduce((n,b)=>n+b.errors,0);s.compactions=s.breakdown.reduce((n,b)=>n+b.compactions,0);
  const active=s.breakdown.filter(b=>b.first!==null);s.elapsedSeconds=active.length?Math.max(0,Math.round((Math.max(...active.map(b=>b.last))-Math.min(...active.map(b=>b.first)))/1000)):0;
 }
 const breakdown=list.flatMap(s=>s.breakdown);
 const totals={cloud:sum(breakdown.filter(b=>b.class==='cloud')),local:sum(breakdown.filter(b=>b.class==='local')),unknown:sum(breakdown.filter(b=>b.class==='unknown')),all:sum(breakdown)};
 const group=key=>{
  const groups=new Map();for(const b of breakdown){const k=key(b);if(!groups.has(k))groups.set(k,[]);groups.get(k).push(b);}
  return [...groups].map(([key,rows])=>({key,class:uniqueValue(rows.map(b=>b.class)),...sum(rows)})).sort((a,b)=>b.weighted-a.weighted);
 };
 const byAgent=group(b=>b.agent).map(({key,...g})=>({agent:key,...g}));
 const byModel=group(b=>b.modelKey).map(({key,...g})=>({model:key,...g}));
 // Stored tool parts can recur in later turns. Keep one dispatch per child/call.
 const seen=new Set();
 const dispatches=list.flatMap(s=>s.dispatches).sort((a,b)=>a.at-b.at).filter(d=>{const key=d.sessionID??d.id??`${d.parent}:${d.at}:${d.agent}`;if(seen.has(key))return false;seen.add(key);return true;}).map(d=>({...d,childClass:sessions.get(d.sessionID)?.class??'unknown',childWeighted:sessions.get(d.sessionID)?.weighted??0}));
 for(const s of list)s.dispatches=dispatches.filter(d=>d.parent===s.id);
 const possibleHandoffs=[];
 for(const parent of list){const ds=parent.dispatches;for(let i=0;i<ds.length;i++)if(ds[i].agent==='general')for(let j=i+1;j<ds.length;j++)if(ds[j].agent==='build'){possibleHandoffs.push({parent:parent.id,from:ds[i].sessionID,to:ds[j].sessionID,fromWeighted:sessions.get(ds[i].sessionID)?.weighted??0,toWeighted:sessions.get(ds[j].sessionID)?.weighted??0});break;}}
 const root=sessions.get(tree.root.id);
 const delegated=dispatches.length>0||list.length>1;
 const descendantsWeighted=list.filter(s=>s.id!==root.id).reduce((n,s)=>n+s.weighted,0);
 const rootCloud=breakdown.filter(b=>b.sessionID===root.id&&b.class==='cloud').reduce((n,b)=>n+b.weighted,0);
 const shares={cloudWeighted:totals.all.weighted?totals.cloud.weighted/totals.all.weighted:0,localWeighted:totals.all.weighted?totals.local.weighted/totals.all.weighted:0,unknownWeighted:totals.all.weighted?totals.unknown.weighted/totals.all.weighted:0,rootShareOfCloud:totals.cloud.weighted?rootCloud/totals.cloud.weighted:0,rootVsWorkers:descendantsWeighted?root.weighted/descendantsWeighted:null};
 const classes=[...new Set(breakdown.filter(b=>b.turns).map(b=>b.class))];
 const status=classes.length>1?'mixed':classes[0]==='local'?'local-only':classes[0]==='cloud'?'cloud-only':'unknown';
 const routing={status,label:{'local-only':'Local models only','cloud-only':'Cloud models only',mixed:'Mixed model classes',unknown:'Model class unknown'}[status],reasons:[`Observed cloud ${pct(shares.cloudWeighted)}, local ${pct(shares.localWeighted)}, unknown ${pct(shares.unknownWeighted)} of weighted tokens`,delegated?'delegation observed':'no delegation observed']};
 const findings=[];
 const describe=rows=>rows.map(b=>`${b.agent} ${b.sessionID} (${b.model}, ${num(b.weighted)} weighted)`).join('; ')+'.';
 const cloudWorkers=breakdown.filter(b=>WORKER_AGENTS.includes(b.agent)&&b.class==='cloud'&&b.turns);
 if(cloudWorkers.length)findings.push({id:'cloud-worker-routing',severity:'high',title:'Worker roles ran on a cloud model',detail:describe(cloudWorkers),suggestion:'Review worker model assignments against the intended routing policy. Token volume alone does not establish task suitability or outcome.',observedWeighted:cloudWorkers.reduce((n,b)=>n+b.weighted,0)});
 if(dispatches.some(d=>d.background))findings.push({id:'background-dispatch',severity:'high',title:'Background subagent dispatch observed',detail:`${dispatches.filter(d=>d.background).length} of ${dispatches.length} dispatches ran with background=true.`,suggestion:'Review these dispatches against the foreground worker policy.'});
 if(delegated&&rootCloud>0&&shares.rootVsWorkers>1)findings.push({id:'coordinator-token-share',severity:'info',title:'Root used more weighted tokens than child sessions',detail:`Root used ${num(root.weighted)} weighted tokens; children used ${num(descendantsWeighted)}.`,suggestion:'Review the task outcome and context carried by each role before changing delegation. Token share alone does not measure efficiency.'});
 for(const e of possibleHandoffs)findings.push({id:'possible-handoff',severity:'info',title:'Possible General-to-Build handoff',detail:`General ${e.from} was followed by Build ${e.to} under ${e.parent}.`,suggestion:'Inspect the task briefs and outcomes to determine whether these dispatches were related.'});
 const nested=list.filter(s=>s.children.length&&s.breakdown.some(b=>NO_DELEGATION_AGENTS.includes(b.agent)));
 if(nested.length)findings.push({id:'nested-delegation',severity:'medium',title:'A session with a worker role delegated further',detail:nested.map(s=>`${s.breakdown.filter(b=>NO_DELEGATION_AGENTS.includes(b.agent)).map(b=>b.agent).join('/')} ${s.id} has ${s.children.length} child session(s)`).join('; ')+'.',suggestion:'Check the dispatch-time role and worker permissions against the no-delegation policy.'});
 const reasoningHeavy=breakdown.filter(b=>b.class==='cloud'&&b.tokens.output+b.tokens.reasoning>1000&&b.tokens.reasoning/(b.tokens.output+b.tokens.reasoning)>0.6);
 if(reasoningHeavy.length)findings.push({id:'reasoning-heavy',severity:'info',title:'Reasoning dominates cloud output',detail:describe(reasoningHeavy),suggestion:'Interpret reasoning volume in the context of the assigned task and result.'});
 const cloudCompactions=breakdown.filter(b=>b.class==='cloud'&&b.compactions);
 if(cloudCompactions.length)findings.push({id:'compaction-on-cloud',severity:'medium',title:'Context compaction ran on a cloud model',detail:describe(cloudCompactions),suggestion:'Review compaction model routing and context requirements.'});
 const budget=breakdown.filter(b=>steps[b.agent]&&b.turns>=steps[b.agent]);
 if(budget.length)findings.push({id:'step-budget',severity:'medium',title:'Worker reached its configured step threshold',detail:describe(budget),suggestion:'Check the actual step limit and completion outcome before inferring that work stopped early.'});
 const errors=breakdown.filter(b=>b.errors);
 if(errors.length)findings.push({id:'errors',severity:'medium',title:'Error or retry records observed',detail:errors.map(b=>`${b.agent} ${b.sessionID} (${b.model}): ${b.errors} affected turn(s)`).join('; ')+'.',suggestion:'Inspect the provider and OpenCode logs to establish the cause and final outcome.'});
 const unpriced=breakdown.filter(b=>b.cost===null);
 if(unpriced.length)findings.push({id:'unpriced-models',severity:'low',title:'Some message costs are unknown',detail:`Missing recorded costs or complete rates for ${[...new Set(unpriced.map(b=>b.modelKey))].join(', ')}.`,suggestion:'Supply per-million model rates with --pricing FILE. A partially recorded cost does not price the remaining messages.'});
 if(totals.unknown.turns)findings.push({id:'unknown-provider-class',severity:'low',title:'Provider location is unknown',detail:describe(breakdown.filter(b=>b.class==='unknown'&&b.turns)),suggestion:'Set localProviders or cloudProviders explicitly when using the analysis API; provider name prefixes do not establish hosting location.'});
 const order={high:0,medium:1,low:2,info:3};findings.sort((a,b)=>order[a.severity]-order[b.severity]);
 return {root:{id:root.id,title:root.title,agent:root.agent,model:root.modelRef,directory:root.directory,started:tree.root.created,elapsedSeconds:root.elapsedSeconds},
  sessions:list.map(s=>({id:s.id,parentID:s.parentID,title:s.title,depth:s.depth,agent:s.agent,model:s.modelRef,class:s.class,turns:s.turns,tokens:s.tokens,weighted:s.weighted,cost:s.cost,errors:s.errors,compactions:s.compactions,elapsedSeconds:s.elapsedSeconds,children:s.children.length,breakdown:s.breakdown})),
  breakdown,totals,byAgent,byModel,shares,dispatches:dispatches.map(d=>({parent:d.parent,agent:d.agent,background:d.background,sessionID:d.sessionID,childClass:d.childClass,childWeighted:d.childWeighted})),possibleHandoffs,findings,routing,
  notes:[`weighted = input + output + reasoning + cache-write + ${Math.round(CACHE_READ_WEIGHT*100)}% of cache-read (rounded per message; heuristic weighting, not a bill)`,"Token counts are OpenCode's per-turn records; routing observations do not establish task quality or efficiency.",'Costs combine recorded positive per-message costs and available model rates; local estimates exclude hardware and operating costs. Unknown message costs keep aggregate cost unknown.','Session counts in groups are distinct contributing sessions; a session with multiple identities can appear in more than one group.']};
}

function table(headers,rows){
 const widths=headers.map((h,i)=>Math.max(h.length,...rows.map(r=>String(r[i]).length)));
 const line=cells=>cells.map((c,i)=>i===0?String(c).padEnd(widths[i]):String(c).padStart(widths[i])).join('  ');
 return [line(headers),...rows.map(line)].join('\n');
}
const tokenCells=(t,w,cost)=>[num(t.input),num(t.output),num(t.reasoning),num(t.cacheRead),num(t.cacheWrite),num(w),money(cost)];
const tokenHeaders=['input','output','reason','cache-rd','cache-wr','weighted','cost'];

export function render(report){
 const out=[];
 out.push(`OpenCode usage report: ${report.root.title||'(untitled)'} [${report.root.id}]`);
 out.push(`Directory ${report.root.directory}; root ${report.root.agent} on ${report.root.model}; ${report.root.elapsedSeconds}s wall-clock span; ${report.sessions.length} session(s), ${report.dispatches.length} dispatch(es).`);
 out.push(`Routing: ${report.routing.label} (${report.routing.reasons.join('; ')})`);
 out.push('\nSessions');
 out.push(table(['agent','model','class','turns',...tokenHeaders,'span-s'],report.sessions.map(s=>[`${'  '.repeat(s.depth)}${s.agent??'?'}`,s.model,s.class,s.turns,...tokenCells(s.tokens,s.weighted,s.cost),s.elapsedSeconds])));
 out.push('\nMessage identities');
 out.push(table(['session','agent','model','class','turns',...tokenHeaders],report.breakdown.map(b=>[b.sessionID,b.agent,b.model,b.class,b.turns,...tokenCells(b.tokens,b.weighted,b.cost)])));
 out.push('\nTotals by class');
 const classRow=(name,t)=>[name,t.sessions,t.turns,...tokenCells(t.raw,t.weighted,t.cost)];
 out.push(table(['class','sessions','turns',...tokenHeaders],[classRow('Cloud',report.totals.cloud),classRow('Local',report.totals.local),classRow('Unknown',report.totals.unknown),classRow('All',report.totals.all)]));
 out.push(`Cloud share of weighted tokens: ${pct(report.shares.cloudWeighted)}; local share: ${pct(report.shares.localWeighted)}.`);
 out.push('\nBy agent');
 out.push(table(['agent','class','sessions','turns','weighted','cost'],report.byAgent.map(a=>[a.agent,a.class,a.sessions,a.turns,num(a.weighted),money(a.cost)])));
 out.push('\nBy model');
 out.push(table(['model','class','sessions','turns','weighted','cost'],report.byModel.map(m=>[m.model,m.class,m.sessions,m.turns,num(m.weighted),money(m.cost)])));
 if(report.dispatches.length){out.push('\nDispatches');out.push(table(['from','agent','mode','child class','child weighted'],report.dispatches.map(d=>[d.parent,d.agent??'?',d.background?'background':'foreground',d.childClass,num(d.childWeighted)])));}
 out.push('\nFindings');
 if(!report.findings.length)out.push('none');
 for(const f of report.findings)out.push(`[${f.severity}] ${f.title}: ${f.detail}\n  Suggestion: ${f.suggestion}`);
 out.push('\nNotes');for(const n of report.notes)out.push(`- ${n}`);
 return out.join('\n');
}

export function renderComparison(reports){
 const rows=reports.map(r=>[r.root.id,r.root.agent,r.routing.label,num(r.totals.cloud.weighted),num(r.totals.local.weighted),pct(r.shares.cloudWeighted),r.totals.all.turns,money(r.totals.cloud.cost),r.root.elapsedSeconds]);
 return 'Comparison\n'+table(['session','root agent','routing','cloud weighted','local weighted','cloud share','turns','cloud cost','span-s'],rows)+'\nCompare measured cloud usage and costs only after checking equivalent task outcomes and conditions.';
}

/** Agents -> models -> session instances, for a live tree view. */
export function hierarchy(report){
 const agents=new Map();
 for(const b of report.breakdown){if(!agents.has(b.agent))agents.set(b.agent,[]);agents.get(b.agent).push(b);}
 return [...agents].map(([agent,rows])=>{
  const models=new Map();for(const b of rows){if(!models.has(b.model))models.set(b.model,[]);models.get(b.model).push(b);}
  return {agent,class:uniqueValue(rows.map(b=>b.class)),...sum(rows),models:[...models].map(([model,instances])=>({model,class:uniqueValue(instances.map(b=>b.class)),...sum(instances),instances})).sort((a,b)=>b.weighted-a.weighted)};
 }).sort((a,b)=>b.weighted-a.weighted);
}
/** One-line summary for a toast or status line. */
export function summaryLine(report){
 const top=report.findings.find(f=>f.severity==='high'||f.severity==='medium');
 return `Routing: ${report.routing.label}; cloud ${pct(report.shares.cloudWeighted)} / local ${pct(report.shares.localWeighted)} / unknown ${pct(report.shares.unknownWeighted)} of ${num(report.totals.all.weighted)} weighted tokens, ${report.sessions.length} session(s)`+(top?`. ${top.title}.`:'.');
}
