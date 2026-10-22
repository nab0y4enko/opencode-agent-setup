// Pure token/model/agent usage analysis shared by the CLI, the smoke tests and the OpenCode plugin.
// No Node-only or Bun-only imports here: this file must load in Node, in Bun (server plugin) and in the TUI.
export const CACHE_READ_WEIGHT=0.1; // cached input is typically billed at roughly a tenth of fresh input
const WORKER_AGENTS=['general','explore','scout','title','summary'];
const NO_DELEGATION_AGENTS=['general','explore','scout','cloud-reviewer'];
const DEFAULT_STEPS={general:24,explore:12};
const LOCAL_PROVIDER_PATTERN=/^(omlx|ollama|lmstudio|llama|local|mlx|vllm)/i;
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
 const t=d.tokens??{};
 const dispatches=[];
 for(const part of d.content??[]){
  if(part?.type!=='tool'||part.name!=='subagent')continue;
  const input=part.state?.input??{};
  dispatches.push({id:part.id??null,agent:input.agent??null,background:!!input.background,sessionID:part.state?.metadata?.sessionID??null,description:input.description??null,status:part.state?.status??null});
 }
 return {id:d.id??fallback.id??null,sessionID,agent:d.agent??null,model:ref(d.model),created:toMillis(d.time?.created)??fallback.created??0,completed:toMillis(d.time?.completed)??toMillis(d.time?.created)??fallback.completed??0,finish:d.finish??null,cost:Number(d.cost??0),
  compaction:d.summary===true||d.type==='compaction'||d.agent==='compaction',dispatches,
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
   const m=normalizeMessage(s.id,raw);if(m&&(m.agent||m.tokens.input||m.tokens.output))messages.push(m);
  }
 }
 return {root,sessions:tree,messages};
}

function classify(model,localProviders){
 if(!model)return 'unknown';
 return localProviders.includes(model.providerID)||LOCAL_PROVIDER_PATTERN.test(model.providerID)?'local':'cloud';
}
function priceFor(tokens,rate){
 if(!rate)return null;
 const r={reasoning:rate.output,cacheWrite:rate.input,cacheRead:rate.input,...rate};
 return (tokens.input*r.input+tokens.output*r.output+tokens.reasoning*r.reasoning+tokens.cacheRead*r.cacheRead+tokens.cacheWrite*r.cacheWrite)/1e6;
}

export function analyze(tree,{pricing={},steps=DEFAULT_STEPS,localProviders=['omlx']}={}){
 const sessions=new Map();
 for(const s of tree.sessions){
  sessions.set(s.id,{id:s.id,parentID:s.parentID,agent:s.agent,model:s.model,title:s.title,directory:s.directory,depth:0,turns:0,tokens:zero(),weighted:0,cost:null,recordedCost:0,errors:0,compactions:0,first:null,last:null,children:[],dispatches:[]});
 }
 for(const s of sessions.values()){let p=sessions.get(s.parentID),d=0;while(p){d++;p=sessions.get(p.parentID);}s.depth=d;if(sessions.has(s.parentID))sessions.get(s.parentID).children.push(s.id);}
 const messages=tree.messages.filter(m=>sessions.has(m.sessionID));
 const byModelClass=new Map();
 for(const m of messages){
  const s=sessions.get(m.sessionID);
  if(m.compaction){s.compactions++;}
  s.turns++;add(s.tokens,m.tokens);s.recordedCost+=m.cost||0;
  if(m.finish==='error')s.errors++;
  if(m.model)s.model=m.model;
  s.first=s.first===null?m.created:Math.min(s.first,m.created);s.last=s.last===null?m.completed:Math.max(s.last,m.completed);
  for(const d of m.dispatches)s.dispatches.push({...d,parent:s.id,messageID:m.id,at:m.created});
  byModelClass.set(modelKey(m.model),classify(m.model,localProviders));
 }
 for(const s of sessions.values()){
  s.class=classify(s.model,localProviders);
  s.modelRef=modelRef(s.model);
  s.weighted=weighted(s.tokens);
  s.elapsedSeconds=s.first===null?0:Math.max(0,Math.round((s.last-s.first)/1000));
  s.cost=s.class==='local'?0:s.recordedCost>0?s.recordedCost:priceFor(s.tokens,pricing[modelKey(s.model)]);
 }
 const list=[...sessions.values()];
 const sum=rows=>{const out={sessions:rows.length,turns:0,raw:zero(),weighted:0,cost:0,priced:true};for(const r of rows){out.turns+=r.turns;add(out.raw,r.tokens);out.weighted+=r.weighted;if(r.cost===null)out.priced=false;else out.cost+=r.cost;}if(!out.priced)out.cost=null;delete out.priced;return out;};
 const totals={cloud:sum(list.filter(s=>s.class==='cloud')),local:sum(list.filter(s=>s.class==='local')),all:sum(list)};
 const group=(key)=>{const g=new Map();for(const s of list){const k=key(s);if(!g.has(k))g.set(k,[]);g.get(k).push(s);}return [...g.entries()].map(([k,rows])=>({key:k,class:rows[0].class,...sum(rows)})).sort((a,b)=>b.weighted-a.weighted);};
 const byAgent=group(s=>s.agent??'unknown').map(g=>({agent:g.key,...g,key:undefined}));
 const byModel=group(s=>modelKey(s.model)).map(g=>({model:g.key,...g,key:undefined}));
 // Tool parts are repeated in later turns' stored content, so keep the first record per child session or call id.
 const seen=new Set();
 const dispatches=list.flatMap(s=>s.dispatches).sort((a,b)=>a.at-b.at).filter(d=>{const key=d.sessionID??d.id??`${d.parent}:${d.at}`;if(seen.has(key))return false;seen.add(key);return true;}).map(d=>({...d,childClass:sessions.get(d.sessionID)?.class??'unknown',childWeighted:sessions.get(d.sessionID)?.weighted??0}));
 for(const s of list)s.dispatches=dispatches.filter(d=>d.parent===s.id);
 const escalations=[];
 for(const parent of list){const ds=parent.dispatches.sort((a,b)=>a.at-b.at);for(let i=0;i<ds.length;i++)if(ds[i].agent==='general')for(let j=i+1;j<ds.length;j++)if(ds[j].agent==='build'){escalations.push({parent:parent.id,from:ds[i].sessionID,to:ds[j].sessionID,localWeighted:sessions.get(ds[i].sessionID)?.weighted??0,cloudWeighted:sessions.get(ds[j].sessionID)?.weighted??0});break;}}
 const root=sessions.get(tree.root.id);
 const delegated=dispatches.length>0||list.length>1;
 const descendantsWeighted=list.filter(s=>s.id!==root.id).reduce((a,s)=>a+s.weighted,0);
 const shares={cloudWeighted:totals.all.weighted?totals.cloud.weighted/totals.all.weighted:0,localWeighted:totals.all.weighted?totals.local.weighted/totals.all.weighted:0,rootShareOfCloud:totals.cloud.weighted?(root.class==='cloud'?root.weighted/totals.cloud.weighted:0):0,rootVsWorkers:descendantsWeighted?root.weighted/descendantsWeighted:null};
 const findings=[];
 const cloudWorkers=list.filter(s=>WORKER_AGENTS.includes(s.agent)&&s.class==='cloud');
 if(cloudWorkers.length){const saving=cloudWorkers.reduce((a,s)=>a+s.weighted,0);findings.push({id:'cloud-worker-routing',severity:'high',title:'Worker roles ran on a cloud model',detail:`${cloudWorkers.map(s=>`${s.agent} (${s.modelRef}, ${num(s.weighted)} weighted)`).join('; ')}.`,suggestion:'Assign General/Explore (and Title/Summary) to the local provider in the agent configuration; these sessions are the tool loop the setup intends to keep local.',savingWeighted:saving});}
 if(dispatches.some(d=>d.background))findings.push({id:'background-dispatch',severity:'high',title:'Background subagent dispatch observed',detail:`${dispatches.filter(d=>d.background).length} of ${dispatches.length} dispatches ran with background=true.`,suggestion:'The coordinator contract requires foreground dispatch; background workers invite polling turns, duplicate work and unreviewed results. Restate the rule in the brief or review the orchestrator prompt.'});
 if(delegated&&root.class==='cloud'&&shares.rootVsWorkers!==null&&shares.rootVsWorkers>1)findings.push({id:'coordination-overhead',severity:'medium',title:'Coordinator spent more than its workers',detail:`Root ${root.agent} used ${num(root.weighted)} weighted tokens against ${num(descendantsWeighted)} across ${list.length-1} child sessions (ratio ${shares.rootVsWorkers.toFixed(1)}).`,suggestion:'For a task this small the delegation overhead exceeds the delegated work: run Build directly for one-step changes, or give workers fewer, larger stages with complete briefs so the coordinator reads fewer reports.'});
 for(const e of escalations)findings.push({id:'escalation',severity:'medium',title:'Local worker escalated to cloud Build',detail:`General ${e.from} (${num(e.localWeighted)} local weighted) was followed by Build ${e.to} (${num(e.cloudWeighted)} cloud weighted) under ${e.parent}.`,suggestion:'Each failed local attempt is paid twice: the local tokens plus the coordinator reading the failure and Build re-reading the context. If this task type escalates repeatedly, route it to Build from the start.'});
 const nested=list.filter(s=>NO_DELEGATION_AGENTS.includes(s.agent)&&s.children.length);
 if(nested.length)findings.push({id:'nested-delegation',severity:'medium',title:'A worker delegated further',detail:nested.map(s=>`${s.agent} ${s.id} spawned ${s.children.length} child session(s)`).join('; ')+'.',suggestion:'Workers should not spawn subagents; nested context multiplies tokens and hides work from the coordinator review. Check the worker permissions deny the subagent tool.'});
 const reasoningHeavy=list.filter(s=>s.class==='cloud'&&s.tokens.output+s.tokens.reasoning>1000&&s.tokens.reasoning/(s.tokens.output+s.tokens.reasoning)>0.6);
 if(reasoningHeavy.length)findings.push({id:'reasoning-heavy',severity:'low',title:'Reasoning dominates cloud output',detail:reasoningHeavy.map(s=>`${s.agent} ${s.id}: ${pct(s.tokens.reasoning/(s.tokens.output+s.tokens.reasoning))} of output tokens were reasoning`).join('; ')+'.',suggestion:'Expected for Build on hard problems. For the coordinator, a lower reasoning variant (medium or low) usually suffices for routing and review.'});
 const cloudCompactions=list.filter(s=>s.class==='cloud'&&s.compactions);
 if(cloudCompactions.length)findings.push({id:'compaction-on-cloud',severity:'medium',title:'Context compaction ran on a cloud model',detail:cloudCompactions.map(s=>`${s.agent} ${s.id}: ${s.compactions} compaction(s)`).join('; ')+'.',suggestion:'Compaction re-reads the whole context. Keep briefs and worker reports short so coordinator sessions compact rarely, or evaluate a local compaction model once its long-context fidelity is tested.'});
 const budget=list.filter(s=>steps[s.agent]&&s.turns>=steps[s.agent]);
 if(budget.length)findings.push({id:'step-budget',severity:'medium',title:'Worker reached its step budget',detail:budget.map(s=>`${s.agent} ${s.id}: ${s.turns} turns, enhanced-profile budget ${steps[s.agent]}`).join('; ')+'.',suggestion:'The worker likely stopped with partial work, which the coordinator then pays to reconcile. Split the stage or supply exact file paths and commands in the brief.'});
 const errors=list.filter(s=>s.errors);
 if(errors.length)findings.push({id:'errors',severity:'medium',title:'Model turns ended in error',detail:errors.map(s=>`${s.agent} ${s.id}: ${s.errors} error turn(s)`).join('; ')+'.',suggestion:'Errored turns still consume input tokens. Check provider limits, local server availability and the OpenCode log for the failure cause.'});
 if(root.class==='cloud'&&root.turns>40&&dispatches.length<2)findings.push({id:'coordinator-tool-loop',severity:'medium',title:'Cloud root session ran a long tool loop itself',detail:`${root.agent} took ${root.turns} turns with ${dispatches.length} dispatch(es).`,suggestion:'Exploration and mechanical edits are what local workers are for; delegate the bounded discovery and implementation and keep the cloud session to planning and review.'});
 const unpriced=list.filter(s=>s.class==='cloud'&&s.cost===null);
 if(unpriced.length)findings.push({id:'unpriced-models',severity:'low',title:'Cloud cost unknown',detail:`No recorded cost for ${[...new Set(unpriced.map(s=>modelKey(s.model)))].join(', ')}; token counts are exact, dollars are not shown.`,suggestion:'Pass --pricing FILE with per-million rates ({"openai/MODEL":{"input":..,"output":..,"cacheRead":..}}) to see estimated cost.'});
 if(!findings.some(f=>f.severity==='high')&&delegated&&totals.local.weighted>totals.cloud.weighted)findings.push({id:'healthy-split',severity:'info',title:'Most of the token volume stayed local',detail:`Local ${pct(shares.localWeighted)} versus cloud ${pct(shares.cloudWeighted)} of weighted tokens across ${dispatches.length} dispatch(es).`,suggestion:'This is the intended shape. Compare against a Build-only run of the same task to confirm the absolute cloud saving.'});
 const order={high:0,medium:1,low:2,info:3};findings.sort((a,b)=>order[a.severity]-order[b.severity]);
 const grade=gradeFor(shares,findings,delegated,root);
 return {root:{id:root.id,title:root.title,agent:root.agent,model:root.modelRef,directory:root.directory,started:tree.root.created,elapsedSeconds:root.elapsedSeconds},
  sessions:list.map(s=>({id:s.id,parentID:s.parentID,title:s.title,depth:s.depth,agent:s.agent,model:s.modelRef,class:s.class,turns:s.turns,tokens:s.tokens,weighted:s.weighted,cost:s.cost,errors:s.errors,compactions:s.compactions,elapsedSeconds:s.elapsedSeconds,children:s.children.length})),
  totals,byAgent,byModel,shares,dispatches:dispatches.map(d=>({parent:d.parent,agent:d.agent,background:d.background,sessionID:d.sessionID,childClass:d.childClass,childWeighted:d.childWeighted})),escalations,findings,grade,
  notes:[`weighted = input + output + reasoning + cache-write + ${Math.round(CACHE_READ_WEIGHT*100)}% of cache-read (heuristic weighting, not a bill)`,'Token counts are OpenCode\'s own per-turn records; findings are heuristics about routing, not proof of correctness.']};
}

function gradeFor(shares,findings,delegated,root){
 const reasons=[];let score;
 if(!delegated&&root.class==='cloud'){score=root.turns>12?'C':'B';reasons.push(`single cloud session, no delegation (${root.turns} turns)`);}
 else if(!delegated&&root.class==='local'){score='A';reasons.push('entire session ran locally');}
 else{
  const c=shares.cloudWeighted;score=c<0.4?'A':c<0.6?'B':c<0.8?'C':'D';
  reasons.push(`cloud share of weighted tokens ${pct(c)}`);
 }
 const highs=findings.filter(f=>f.severity==='high');
 if(highs.length){score=String.fromCharCode(Math.min('D'.charCodeAt(0),score.charCodeAt(0)+1));reasons.push(`demoted for: ${highs.map(f=>f.id).join(', ')}`);}
 const mediums=findings.filter(f=>f.severity==='medium').length;
 if(mediums>=3&&score<'D'){score=String.fromCharCode(score.charCodeAt(0)+1);reasons.push(`${mediums} medium findings`);}
 const label={A:'good: cloud is used for coordination and hard work only',B:'fair: cloud carries a noticeable part of the routine work',C:'poor: cloud did most of the work; delegation is not paying off',D:'bad: delegation cost more than it saved or policy was violated'}[score];
 return {letter:score,label,reasons};
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
 out.push(`Grade ${report.grade.letter}: ${report.grade.label} (${report.grade.reasons.join('; ')})`);
 out.push('\nSessions');
 out.push(table(['agent','model','class','turns',...tokenHeaders,'span-s'],report.sessions.map(s=>[`${'  '.repeat(s.depth)}${s.agent??'?'}`,s.model,s.class,s.turns,...tokenCells(s.tokens,s.weighted,s.cost),s.elapsedSeconds])));
 out.push('\nTotals by class');
 const classRow=(name,t)=>[name,t.sessions,t.turns,...tokenCells(t.raw,t.weighted,t.cost)];
 out.push(table(['class','sessions','turns',...tokenHeaders],[classRow('Cloud',report.totals.cloud),classRow('Local',report.totals.local),classRow('All',report.totals.all)]));
 out.push(`Cloud share of weighted tokens: ${pct(report.shares.cloudWeighted)}; local share: ${pct(report.shares.localWeighted)}.`);
 out.push('\nBy agent');
 out.push(table(['agent','class','sessions','turns','weighted','cost'],report.byAgent.map(a=>[a.agent,a.class,a.sessions,a.turns,num(a.weighted),money(a.cost)])));
 out.push('\nBy model');
 out.push(table(['model','class','sessions','turns','weighted','cost'],report.byModel.map(m=>[m.model,m.class,m.sessions,m.turns,num(m.weighted),money(m.cost)])));
 if(report.dispatches.length){out.push('\nDispatches');out.push(table(['from','agent','mode','child class','child weighted'],report.dispatches.map(d=>[d.parent,d.agent??'?',d.background?'background':'foreground',d.childClass,num(d.childWeighted)])));}
 out.push('\nFindings');
 if(!report.findings.length)out.push('none');
 for(const f of report.findings)out.push(`[${f.severity}] ${f.title}: ${f.detail}\n  Suggestion: ${f.suggestion}${f.savingWeighted?` Potential local shift: ${num(f.savingWeighted)} weighted tokens.`:''}`);
 out.push('\nNotes');for(const n of report.notes)out.push(`- ${n}`);
 return out.join('\n');
}

export function renderComparison(reports){
 const rows=reports.map(r=>[r.root.id,r.root.agent,r.grade.letter,num(r.totals.cloud.weighted),num(r.totals.local.weighted),pct(r.shares.cloudWeighted),r.totals.all.turns,money(r.totals.cloud.cost),r.root.elapsedSeconds]);
 return 'Comparison\n'+table(['session','root agent','grade','cloud weighted','local weighted','cloud share','turns','cloud cost','span-s'],rows)+'\nLower cloud weighted tokens for the same outcome is the saving; compare only runs of the same task.';
}

/** Agents -> models -> session instances, for a live tree view. */
export function hierarchy(report){
 const agents=new Map();
 for(const s of report.sessions){
  const a=agents.get(s.agent??'unknown')??{agent:s.agent??'unknown',class:s.class,sessions:0,turns:0,weighted:0,cost:0,priced:true,models:new Map()};
  agents.set(a.agent,a);a.sessions++;a.turns+=s.turns;a.weighted+=s.weighted;if(s.cost===null)a.priced=false;else a.cost+=s.cost;
  const m=a.models.get(s.model)??{model:s.model,class:s.class,instances:[],weighted:0,turns:0};a.models.set(s.model,m);
  m.weighted+=s.weighted;m.turns+=s.turns;m.instances.push({id:s.id,title:s.title,parentID:s.parentID,depth:s.depth,turns:s.turns,tokens:s.tokens,weighted:s.weighted,cost:s.cost,errors:s.errors,elapsedSeconds:s.elapsedSeconds});
 }
 return [...agents.values()].map(a=>({...a,cost:a.priced?a.cost:null,priced:undefined,models:[...a.models.values()].sort((x,y)=>y.weighted-x.weighted)})).sort((x,y)=>y.weighted-x.weighted);
}
/** One-line summary for a toast or status line. */
export function summaryLine(report){
 const top=report.findings.find(f=>f.severity==='high'||f.severity==='medium');
 return `Grade ${report.grade.letter}: cloud ${pct(report.shares.cloudWeighted)} / local ${pct(report.shares.localWeighted)} of ${num(report.totals.all.weighted)} weighted tokens, ${report.sessions.length} session(s)`+(top?`. ${top.title}.`:'.');
}
