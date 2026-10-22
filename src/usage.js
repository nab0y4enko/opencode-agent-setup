// Read-only token/model/agent usage report built from OpenCode's own session records.
// Numbers come from the per-message token counts OpenCode stores; findings are heuristics, not billing.
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {normalizeMessage} from './usage-analysis.js';
export * from './usage-analysis.js';


export function defaultDatabasePath(){return path.join(process.env.XDG_DATA_HOME??path.join(os.homedir(),'.local/share'),'opencode','opencode.db');}

export function stateDirectory(){return path.join(process.env.XDG_STATE_HOME??path.join(os.homedir(),'.local/state'),'opencode-agent-setup');}
/** Default driver: Node's built-in SQLite. Bun callers pass {driver} built on bun:sqlite instead (see plugin/agent-usage/server.js). */
function nodeDriver(file){
 const sqlite=typeof process.getBuiltinModule==='function'?process.getBuiltinModule('node:sqlite'):null;
 if(!sqlite?.DatabaseSync)throw Error('node:sqlite is unavailable in this runtime; pass a driver.');
 return new sqlite.DatabaseSync(file,{readOnly:true});
}
export function openDatabase(file=defaultDatabasePath(),{driver=nodeDriver}={}){
 if(!fs.existsSync(file))throw Error(`OpenCode database not found: ${file}`);
 const raw=driver(file);
 const tables=new Set(raw.prepare("select name from sqlite_master where type='table'").all().map(r=>r.name));
 const session=tables.has('session_v2')?'session_v2':tables.has('session')?'session':null;
 const message=tables.has('session_message')?'session_message':tables.has('message')?'message':null;
 if(!session||!message){raw.close();throw Error('Unrecognized OpenCode database layout; no session tables found.');}
 return {raw,tables:{session,message},close:()=>raw.close()};
}

function rowToSession(r){
 let model=null;try{model=r.model?JSON.parse(r.model):null;}catch{model=null;}
 return {id:r.id,parentID:r.parent_id??null,agent:r.agent??null,model,directory:r.directory,title:r.title??'',created:r.time_created,updated:r.time_updated,compacting:r.time_compacting??null};
}
const sessionColumns='id,parent_id,agent,model,directory,title,time_created,time_updated,time_compacting';

export function listRoots(db,{directory,limit=10}={}){
 const where=directory?'where parent_id is null and directory = ?':'where parent_id is null';
 const stmt=db.raw.prepare(`select ${sessionColumns} from ${db.tables.session} ${where} order by time_updated desc limit ?`);
 return (directory?stmt.all(directory,limit):stmt.all(limit)).map(rowToSession);
}
export function findRoot(db,{directory}={}){return listRoots(db,{directory,limit:1})[0]??null;}
export function getSession(db,id){const row=db.raw.prepare(`select ${sessionColumns} from ${db.tables.session} where id = ?`).get(id);return row?rowToSession(row):null;}
function parseMessage(sessionID,row){
 let d;try{d=JSON.parse(row.data);}catch{return null;}
 return normalizeMessage(sessionID,d,{id:row.id,created:row.time_created,completed:row.time_updated,type:row.type});
}

export function loadTree(db,rootId){
 const byId=db.raw.prepare(`select ${sessionColumns} from ${db.tables.session} where id = ?`);
 const children=db.raw.prepare(`select ${sessionColumns} from ${db.tables.session} where parent_id = ? order by time_created`);
 const rootRow=byId.get(rootId);if(!rootRow)throw Error(`Session not found: ${rootId}`);
 const sessions=[];const queue=[rowToSession(rootRow)];
 while(queue.length){const s=queue.shift();sessions.push(s);queue.push(...children.all(s.id).map(rowToSession));}
 const timeColumn=db.tables.message==='session_message'?'seq':'time_created';
 const typeFilter=db.tables.message==='session_message'?"and type in ('assistant','compaction')":'';
 const messagesFor=db.raw.prepare(`select id, data, time_created, time_updated${db.tables.message==='session_message'?', type':''} from ${db.tables.message} where session_id = ? ${typeFilter} order by ${timeColumn}`);
 const messages=[];
 for(const s of sessions)for(const row of messagesFor.all(s.id)){const m=parseMessage(s.id,row);if(m)messages.push(m);}
 return {root:sessions[0],sessions,messages};
}

