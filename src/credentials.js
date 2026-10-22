import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import crypto from 'node:crypto';
export function privateCredential(key,root=path.join(process.env.XDG_STATE_HOME??path.join(os.homedir(),'.local/state'),'opencode-agent-setup','credentials')){
 if(!key||typeof key!=='string')throw Error('No local API key available from the selected source.');
 return {key,file:path.join(root,crypto.randomUUID()+'.key')};
}
export function writeCredential(credential){
 const directory=path.dirname(credential.file);fs.mkdirSync(directory,{recursive:true,mode:0o700});
 if(fs.lstatSync(directory).isSymbolicLink())throw Error('Refusing symbolic link credentials directory');
 fs.chmodSync(directory,0o700);fs.writeFileSync(credential.file,credential.key,{mode:0o600,flag:'wx'});
}
