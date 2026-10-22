// OpenCode 2.1.2 server plugin (Promise API). On root-session completion it writes the usage report
// to $XDG_STATE_HOME/opencode-agent-setup/usage/ and logs a one-line summary. Database reads only; no model requests.
// Natural completion coverage: test/natural-completion.py (explicit local inference).
import {Plugin} from '@opencode/plugin';
import {COMPLETION_EVENTS,writeSessionReport} from './report.js';

// OpenCode runs plugins under Bun, where node:sqlite is unavailable; bun:sqlite exposes a compatible prepare/all/get surface.
async function sqliteDriver(){
 const {Database}=await import('bun:sqlite');
 return file=>{const db=new Database(file,{readonly:true});return {prepare:sql=>{const q=db.query(sql);return {all:(...a)=>q.all(...a),get:(...a)=>q.get(...a)};},close:()=>db.close()};};
}

export default Plugin.define({
 id:'agent-usage',
 setup: async (ctx)=>{
  const controller=new AbortController();
  const driver=await sqliteDriver();
  const loop=async()=>{
   for await (const event of ctx.event.subscribe({signal:controller.signal})){
    if(!COMPLETION_EVENTS.has(event.type))continue;
    const data=event.data??event.properties??{};
    const sessionID=data.sessionID;if(!sessionID)continue;
    // Native lifecycle events follow committed session records. Write in this
    // event turn: standalone CLI shutdown can cancel delayed work. Each terminal
    // event is a new checkpoint, including rapid follow-ups in the same session.
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
