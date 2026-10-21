// node --test frontend/src/components.test.js
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {componentHealth,overallHealth,COMPONENTS} from './components.js';
const ok=data=>({ok:true,data});
const down=status=>({ok:false,status});
const by=rows=>Object.fromEntries(rows.map(r=>[r.key,r]));

test('three components, derived from the three operator-reachable polls',()=>{
  assert.deepEqual(COMPONENTS.map(c=>c.key),['payment','remediator','detector']);
});
test('before the first poll every component is unknown, not down',()=>{
  const rows=componentHealth({});
  assert.deepEqual(rows.map(r=>r.level),['unknown','unknown','unknown']);
  assert.equal(overallHealth({}),'unknown');
  assert.equal(componentHealth(undefined).length,3);   // no probes object at all
});
test('all reachable: everything up',()=>{
  const probes={payment:ok({total_cents:200000}),remediator:ok({incidents:[],now:1}),detector:ok({status:'monitoring',score:-0.4})};
  const rows=by(componentHealth(probes));
  assert.equal(rows.payment.level,'up'); assert.match(rows.payment.detail,/200 000/);   // grouped like everywhere else in the console
  assert.equal(rows.remediator.level,'up');
  assert.equal(rows.detector.level,'up'); assert.match(rows.detector.detail,/monitoring.*-0\.400/);
  assert.equal(overallHealth(probes),'up');
});
test('a component that fails its poll is down, and does NOT hide the others',()=>{
  const probes={payment:ok({total_cents:200000}),remediator:down(502),detector:ok({status:'monitoring',score:0})};
  const rows=by(componentHealth(probes));
  assert.equal(rows.payment.level,'up');                 // still shown
  assert.equal(rows.remediator.level,'down'); assert.match(rows.remediator.detail,/502/);
  assert.equal(rows.detector.level,'up');
  assert.equal(overallHealth(probes),'down');            // worst level wins
});
test('the detector carries its model state as a warning, not a failure',()=>{
  const d=s=>by(componentHealth({detector:ok({status:s})})).detector;
  assert.equal(d('monitoring').level,'up');
  assert.deepEqual([d('waiting_for_trained_model').level,d('waiting_for_trained_model').detail],['warn','aucun modèle entraîné']);
  assert.equal(d('telemetry_or_delivery_error').level,'warn');
  assert.equal(d('something_new').level,'warn');         // unknown status is a warning, never silently up
});
test('a reachable payment with no total still reads as up',()=>{
  assert.equal(by(componentHealth({payment:ok({})})).payment.level,'up');
});
test('overall health degrades on the worst component',()=>{
  assert.equal(overallHealth({payment:ok({}),remediator:ok({}),detector:ok({status:'waiting_for_trained_model'})}),'warn');
  assert.equal(overallHealth({payment:ok({}),remediator:undefined,detector:ok({status:'monitoring'})}),'unknown');
});
test('the model and the panel never read a clock or invent a component',()=>{
  const model=readFileSync(new URL('./components.js',import.meta.url),'utf8');
  assert.doesNotMatch(model,/Date\.now|performance\.now|fetch\(/);           // pure: no I/O, no time
  const view=readFileSync(new URL('./Components.jsx',import.meta.url),'utf8');
  assert.match(view,/componentHealth\(probes\)/);                            // the panel derives from the model, nothing else
  assert.doesNotMatch(view,/fetch\(/);
});
