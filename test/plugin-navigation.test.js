import test from 'node:test';
import assert from 'node:assert/strict';
import {createUsageNavigation, latestRoot} from '../plugin/agent-usage/navigation.js';

function fixture(route={type:'session',sessionID:'older-child'}){
 let current=route;let cleared=0;
 const sessions=[{id:'older',time:{updated:10}},{id:'newest',time:{updated:{epochMillis:20}}},{id:'older-child',parentID:'older'}];
 const context={data:{session:{list:()=>sessions,root:id=>id==='older-child'?'older':id}},ui:{router:{current:()=>current,navigate:value=>{current=value;}},dialog:{clear:()=>cleared++}}};
 return {context,navigation:createUsageNavigation(context),current:()=>current,cleared:()=>cleared,sessions};
}

test('usage captures the originating root before navigating away from an older child session',()=>{
 const f=fixture();f.navigation.open();
 assert.equal(f.current().type,'plugin');
 assert.equal(f.current().data.rootID,'older');
 assert.equal(f.navigation.initialRoot(f.current().data),'older');
 assert.notEqual(f.navigation.initialRoot(f.current().data),latestRoot(f.context));
});

test('repeated open preserves the origin and back returns to the original child',()=>{
 const f=fixture();f.navigation.open();const first=structuredClone(f.current());
 f.navigation.open();assert.deepEqual(f.current(),first);assert.equal(f.cleared(),1);
 f.navigation.close();assert.deepEqual(f.current(),{type:'session',sessionID:'older-child'});
 f.navigation.open();assert.equal(f.current().data.rootID,'older');
});

test('home falls back to newest root while explicit newest selection does not change the return route',()=>{
 const f=fixture({type:'home'});f.navigation.open();assert.equal(f.navigation.initialRoot(f.current().data),'newest');
 f.sessions.push({id:'later',time:{updated:new Date(30)}});
 assert.equal(latestRoot(f.context),'later');
 assert.equal(f.navigation.initialRoot(f.current().data),'newest');
 f.navigation.close();assert.deepEqual(f.current(),{type:'home'});
});

test('captured missing session never silently switches to an unrelated newest root',()=>{
 const f=fixture();f.navigation.open();f.sessions.splice(0,1);
 assert.equal(f.navigation.initialRoot(f.current().data),'older');
});
