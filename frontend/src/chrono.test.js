// Run with: node --test frontend/src/chrono.test.js (no dependency, not part of the Vite bundle).
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {chronoModel,parseEvidence,seconds,clock,STEPS,TARGET_S} from './chrono.js';
const incident=(status,stages,extra={})=>({id:'9f1c2e7a-0000-4000-8000-000000000000',status,created:stages.accepted??stages.detected,updated:Math.max(...Object.values(stages)),evidence:'{}',stages,...extra});
const RUNNING={detected:1000,accepted:1000.4,containing:1000.5};
const DONE={...RUNNING,verifying:1006.8,recovered:1014.2};

test('no incident, or no detection time: nothing runs, nothing is shown at zero',()=>{
  assert.deepEqual(chronoModel(undefined,1000),{state:'idle'});
  assert.deepEqual(chronoModel(null,1000),{state:'idle'});
  assert.deepEqual(chronoModel({id:'x',status:'accepted'},1000),{state:'idle'});
  assert.deepEqual(chronoModel(incident('accepted',{accepted:1000}),1005),{state:'idle'});   // no `detected`: cannot start a chrono
  assert.deepEqual(chronoModel(incident('containing',RUNNING),null),{state:'idle'});         // no server clock yet
});
test('a running incident is measured from the detection, on the server clock',()=>{
  const m=chronoModel(incident('containing',RUNNING),1003.2);
  assert.equal(m.state,'running'); assert.ok(Math.abs(m.elapsed-3.2)<1e-9); assert.equal(m.withinTarget,null);
  const later=chronoModel(incident('containing',RUNNING),1012.2);
  assert.ok(Math.abs(later.elapsed-12.2)<1e-9);                                              // it moves only because the server clock moved
  assert.deepEqual(m.steps.map(s=>s.key),['detected','containing','verifying','recovered']);
  assert.deepEqual(m.steps.map(s=>s.at),[1000,1000.5,null,null]);
  assert.deepEqual(m.steps.map(s=>s.offset===null?null:Math.round(s.offset*10)/10),[0,0.5,null,null]);
});
test('the chrono starts at the detector\'s alert time, not when the remediator received it',()=>{
  const m=chronoModel(incident('accepted',{detected:1000,accepted:1002.5}),1003);
  assert.ok(Math.abs(m.elapsed-3)<1e-9);                                                      // 3 s since detection, not 0.5 s since reception
});
test('a recovered incident is frozen at witness-transaction time, whatever the clock says',()=>{
  for(const now of [1014.2,1500,99999]){
    const m=chronoModel(incident('recovered',DONE),now);
    assert.equal(m.state,'recovered'); assert.ok(Math.abs(m.elapsed-14.2)<1e-9); assert.equal(m.withinTarget,true);
  }
  assert.deepEqual(chronoModel(incident('recovered',DONE),1100).steps.map(s=>s.at),[1000,1000.5,1006.8,1014.2]);
});
test('the 60 s target is judged on the measured time',()=>{
  assert.equal(TARGET_S,60);
  assert.equal(chronoModel(incident('recovered',{...DONE,recovered:1059.9}),2000).withinTarget,true);
  assert.equal(chronoModel(incident('recovered',{...DONE,recovered:1060}),2000).withinTarget,false);
  assert.equal(chronoModel(incident('recovered',{...DONE,recovered:1075}),2000).withinTarget,false);
});
test('a failed incident stops at the failure and says which steps were reached',()=>{
  const m=chronoModel(incident('failed',{...RUNNING,failed:1021.3}),5000);
  assert.equal(m.state,'failed'); assert.ok(Math.abs(m.elapsed-21.3)<1e-9); assert.equal(m.withinTarget,null);
  assert.deepEqual(m.steps.map(s=>s.at),[1000,1000.5,null,null]);
});
test('an incident older than the stage log still works from created/updated',()=>{
  const old={id:'x',status:'recovered',created:50,updated:61.5,evidence:'{}',stages:{detected:50,recovered:61.5}};
  assert.ok(Math.abs(chronoModel(old,999).elapsed-11.5)<1e-9);
});
test('the ban is read from the evidence, and bad evidence is harmless',()=>{
  const ban={enabled:true,eligible:['192.168.137.20'],applied:['192.168.137.20'],ttl_s:300};
  assert.deepEqual(chronoModel(incident('recovered',DONE,{evidence:JSON.stringify({transaction_id:'t',ban})}),0).ban,ban);
  for(const bad of ['not json','null','[1,2]','"text"','42','']) assert.deepEqual(parseEvidence(bad),{});
  assert.equal(chronoModel(incident('recovered',DONE,{evidence:'garbage'}),0).ban,null);
});
test('formatting',()=>{
  assert.equal(seconds(14.2),'14,2 s'); assert.equal(seconds(0),'0,0 s');
  assert.match(clock(1000.5),/^\d\d:\d\d:\d\d\.\d{3}$/);
  assert.equal(STEPS.length,4);
});
test('no browser-side counter: the model and the component never read the browser clock to measure time',()=>{
  const model=readFileSync(new URL('./chrono.js',import.meta.url),'utf8').replace(/\/\/.*$/gm,'');
  assert.doesNotMatch(model,/Date\.now|performance\.now|new Date\(\)|setInterval|setTimeout/);
  const view=readFileSync(new URL('./Chrono.jsx',import.meta.url),'utf8').replace(/\/\/.*$/gm,'');
  assert.doesNotMatch(view,/Date\.now|new Date\(/);
  assert.match(view,/serverNow\+\(performance\.now\(\)-fetchedAt\)\/1000/);              // only ever used to advance the SERVER clock between polls
  assert.doesNotMatch(readFileSync(new URL('./main.jsx',import.meta.url),'utf8'),/Date\.now|new Date\(\)/);
});
