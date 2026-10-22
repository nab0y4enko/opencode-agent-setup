// Writes the end-of-session usage report for a root session. Shared by the Bun server plugin and Node tests.
import fs from 'node:fs';
import path from 'node:path';
import {openDatabase,loadTree,getSession,analyze,render,summaryLine,stateDirectory,defaultDatabasePath} from '../../src/usage.js';

export const COMPLETION_EVENTS=new Set(['session.execution.succeeded','session.execution.failed','session.execution.interrupted']);
export function reportDirectory(){return path.join(stateDirectory(),'usage');}

/** Returns {written, summary, files} or {skipped:reason}. Child sessions are skipped: their tokens are counted in the root report. */
export function writeSessionReport(sessionID,{database=defaultDatabasePath(),driver,directory=reportDirectory()}={}){
 const db=openDatabase(database,driver?{driver}:{});
 try{
  const session=getSession(db,sessionID);
  if(!session)return {skipped:'session not found'};
  if(session.parentID)return {skipped:'child session'};
  const report=analyze(loadTree(db,sessionID));
  fs.mkdirSync(directory,{recursive:true,mode:0o700});
  const text=render(report);const files={text:path.join(directory,`${sessionID}.txt`),json:path.join(directory,`${sessionID}.json`),latest:path.join(directory,'latest.txt')};
  fs.writeFileSync(files.text,text,{mode:0o600});fs.writeFileSync(files.json,JSON.stringify(report,null,2),{mode:0o600});fs.writeFileSync(files.latest,text,{mode:0o600});
  return {written:true,summary:summaryLine(report),routing:report.routing,files};
 }finally{db.close();}
}
