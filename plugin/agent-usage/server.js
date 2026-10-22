// OpenCode 2.1.2 server plugin (Promise API). On root-session completion it writes the usage report
// to $XDG_STATE_HOME/opencode-agent-setup/usage/ and logs a one-line summary. Read-only; no model requests.
// UNVERIFIED against a running OpenCode: see docs/test-report.md.
import {Plugin} from '@opencode/plugin';
import {COMPLETION_EVENTS,writeSessionReport} from './report.js';

// OpenCode runs plugins under Bun, where node:sqlite is unavailable; bun:sqlite exposes a compatible prepare/all/get surface.
async function sqliteDriver(){
 const {Database}=await import('bun:sqlite');
 return file=>{const db=new Database(file,{readonly:true});return {prepare:sql=>{const q=db.query(sql);return {all:(...a)=>q.all(...a),get:(...a)=>q.get(...a)};},close:()=>db.close()};};
}
const SETTLE_MS=750; // let the final turn's token record reach the database before reading it

export default Plugin.define({
 id:'agent-usage',
 setup: async (ctx)=>{
  const controller=new AbortController();
  const driver=await sqliteDriver();
  const seen=new Map();
  const loop=async()=>{
   for await (const event of ctx.event.subscribe({signal:controller.signal})){
    if(!COMPLETION_EVENTS.has(event.type))continue;
    const data=event.data??event.properties??{};
    const sessionID=data.sessionID;if(!sessionID)continue;
    const last=seen.get(sessionID);const now=Date.now();if(last&&now-last<2000)continue;seen.set(sessionID,now);
    await new Promise(resolve=>setTimeout(resolve,SETTLE_MS));
    try{
     const result=writeSessionReport(sessionID,{driver});
     if(result.written)console.log(`agent-usage: ${result.summary} Report: ${result.files.text}`);
    }catch(error){console.error(`agent-usage: report failed for ${sessionID}: ${error.message}`);}
   }
  };
  loop().catch(error=>{if(!controller.signal.aborted)console.error(`agent-usage: event loop stopped: ${error.message}`);});
  return ()=>controller.abort();
 },
});
