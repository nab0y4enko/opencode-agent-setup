import test from 'node:test';
import assert from 'node:assert/strict';
import {spawnSync} from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
const cli=path.resolve('bin/setup.js');
test('help is read-only and non-interactive wizard refuses before discovery',()=>{
 const help=spawnSync(process.execPath,[cli,'--help'],{encoding:'utf8'});assert.equal(help.status,0);assert.match(help.stdout,/undo/);assert.match(help.stdout,/ports/);
 const run=spawnSync(process.execPath,[cli],{encoding:'utf8',input:''});assert.equal(run.status,1);assert.match(run.stderr,/terminal/);
});
test('offline preview shows exact additions without creating config',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'patcher cli '));const choices=path.join(dir,'choices.json'),config=path.join(dir,'opencode.json');
 fs.writeFileSync(choices,JSON.stringify([{id:'general',model:'omlx/qwen',prompt:'enhance'}]));
 const run=spawnSync(process.execPath,[cli,'preview','--choices',choices,'--config',config],{encoding:'utf8'});
 assert.equal(run.status,0,run.stderr);assert.match(run.stdout,/\+.*assigned scope/);assert.match(run.stdout,/omlx\/qwen/);assert.ok(!fs.existsSync(config));
});
test('preview masks credentials even in single-line configuration',()=>{
 const dir=fs.mkdtempSync(path.join(os.tmpdir(),'patcher secret '));const choices=path.join(dir,'choices.json'),config=path.join(dir,'opencode.json');
 fs.writeFileSync(config,JSON.stringify({providers:{local:{settings:{apiKey:'SENTINEL_SECRET'}}}}));fs.writeFileSync(choices,JSON.stringify([{id:'general',model:'omlx/qwen',prompt:'enhance'}]));
 const result=spawnSync(process.execPath,[cli,'preview','--choices',choices,'--config',config],{encoding:'utf8'});
 assert.equal(result.status,0);assert.equal(result.stdout.includes('SENTINEL_SECRET'),false);assert.match(result.stdout,/REDACTED/);
});
