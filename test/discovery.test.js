import test from 'node:test';
import assert from 'node:assert/strict';
import { normalizeModels, proposedLocalProvider, supportedVersion } from '../src/native.js';
test('model discovery never returns provider settings or credentials',()=>{
 const result=normalizeModels([{providerID:'openai',id:'strong',settings:{apiKey:'SECRET'},variants:[{id:'high',settings:{apiKey:'OTHER'}}],enabled:true,capabilities:{tools:true}}]);
 assert.equal(JSON.stringify(result).includes('SECRET'),false);assert.equal(result[0].variants[0].id,'high');
});
test('local provider preserves endpoint port and uses environment reference for credentials',()=>{
 const changes=proposedLocalProvider('http://127.0.0.1:8000/v1','Qwen/test','OMLX_API_KEY');
 assert.ok(JSON.stringify(changes).includes('127.0.0.1:8000/v1'));assert.ok(JSON.stringify(changes).includes('{env:OMLX_API_KEY}'));
 assert.throws(()=>proposedLocalProvider('https://cloud.example/v1','qwen','OMLX_API_KEY'),/loopback/);
 assert.throws(()=>proposedLocalProvider('http://localhost:8000/v1','qwen','bad key'),/environment/);
});
test('unknown executable versions are inspection-only',()=>{assert.equal(supportedVersion('opencode v2.1.2'),true);assert.equal(supportedVersion('opencode v2.2.0'),false);});
test('local discovery rejects non-loopback before any credential-bearing request',async()=>{
 const {localModels}=await import('../src/native.js');const original=globalThis.fetch;let calls=0;
 globalThis.fetch=async()=>{calls++;return {ok:false,status:401};};
 try{await assert.rejects(localModels('https://attacker.example/v1','sentinel'),/loopback/);assert.equal(calls,0);}finally{globalThis.fetch=original;}
});
test('local discovery never follows credential-bearing redirects',async()=>{
 const {localModels}=await import('../src/native.js');const original=globalThis.fetch;let redirect;
 globalThis.fetch=async(url,opts)=>{redirect=opts.redirect;return {ok:true,json:async()=>({data:[{id:'qwen'}]})};};
 try{await localModels('http://127.0.0.1:8000/v1','sentinel');assert.equal(redirect,'error');}finally{globalThis.fetch=original;}
});
