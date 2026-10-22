import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import {privateCredential,writeCredential} from '../src/credentials.js';
test('credential file is private, not written until apply, and refuses replacement',()=>{
 const root=fs.mkdtempSync(path.join(os.tmpdir(),'credential-test-'));
 const c=privateCredential('secret-value',root);assert.ok(!fs.existsSync(c.file));
 writeCredential(c);assert.equal(fs.readFileSync(c.file,'utf8'),'secret-value');assert.equal(fs.statSync(c.file).mode&0o777,0o600);
 assert.throws(()=>writeCredential(c),/exist|EEXIST/);fs.rmSync(root,{recursive:true});
});
