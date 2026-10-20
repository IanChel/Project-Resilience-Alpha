// Run with: node --test frontend/src/recette.test.js (no dependency, not part of the Vite bundle).
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {recetteModel,witnessValidated,parseEvidence,WITNESS_TOTAL_CENTS} from './recette.js';
const incident=(status,evidence='{}')=>({id:'9f1c2e7a-0000-4000-8000-000000000000',status,evidence});
const run=over=>recetteModel({remediatorOk:true,detectorOk:true,...over});

test('supervision unreachable is NON VÉRIFIÉ, never a guessed state',()=>{
  const m=recetteModel({remediatorOk:false,incident:incident('recovered',JSON.stringify({transaction_id:'t',total_cents:WITNESS_TOTAL_CENTS}))});
  assert.equal(m.key,'unreachable'); assert.equal(m.verified,false);
  assert.match(m.label,/NON VÉRIFIÉ/);                                   // even a recovered incident is not trusted when we could not read it
});
test('no incident and no anomaly: observation in progress, not a success',()=>{
  const m=run({incident:null});
  assert.equal(m.key,'observing'); assert.equal(m.verified,false);
});
test('before a run, old incident history is not presented as the current recette result',()=>{
  const m=recetteModel({runStartedAt:null,incident:incident('recovered',JSON.stringify({transaction_id:'old',total_cents:WITNESS_TOTAL_CENTS})),remediatorOk:true});
  assert.equal(m.key,'ready');assert.equal(m.verified,false);assert.match(m.label,/Aucune recette lancée/);
});
test('the detector flagging an anomaly before any incident shows "anomalie détectée"',()=>{
  assert.equal(run({incident:null,detector:{anomaly:true}}).key,'anomaly');
  assert.equal(run({incident:null,detector:{anomaly:false}}).key,'observing');
  assert.equal(run({incident:null,detector:{anomaly:true},detectorOk:false}).key,'observing'); // an unreadable detector invents nothing
});
test('the incident lifecycle maps to the live states',()=>{
  assert.equal(run({incident:incident('detected')}).key,'anomaly');
  assert.equal(run({incident:incident('accepted')}).key,'anomaly');
  assert.equal(run({incident:incident('containing')}).key,'contained');
  assert.equal(run({incident:incident('verifying')}).key,'verifying');
  assert.equal(run({incident:incident('failed')}).key,'failed');
});
test('"Reprise vérifiée" ONLY with the documented witness: recovered AND transaction id AND total back to 200000',()=>{
  const good=JSON.stringify({transaction_id:'4d2f...','total_cents':WITNESS_TOTAL_CENTS,ban:{}});
  const m=run({incident:incident('recovered',good)});
  assert.equal(m.key,'recovered'); assert.equal(m.verified,true); assert.equal(m.label,'Reprise vérifiée');
  assert.equal(m.witness.total_cents,WITNESS_TOTAL_CENTS);
});
test('a recovered incident WITHOUT the witness proof is NON VÉRIFIÉ, never a success (HTTP 200 is not enough)',()=>{
  for(const ev of [
    '{}',                                                        // no proof at all
    JSON.stringify({transaction_id:'t'}),                        // id but no ledger total
    JSON.stringify({total_cents:WITNESS_TOTAL_CENTS}),           // total but no transaction id
    JSON.stringify({transaction_id:'t',total_cents:199900}),     // wrong total: ledger not whole
    JSON.stringify({transaction_id:'',total_cents:WITNESS_TOTAL_CENTS}), // empty id
    'garbage not json',
  ]){
    const m=run({incident:incident('recovered',ev)});
    assert.equal(m.key,'recovered_unconfirmed',ev); assert.equal(m.verified,false,ev); assert.match(m.label,/NON VÉRIFIÉ/,ev);
  }
});
test('witnessValidated is strict on the exact total and a real id',()=>{
  assert.equal(witnessValidated(incident('recovered',JSON.stringify({transaction_id:'t',total_cents:WITNESS_TOTAL_CENTS}))),true);
  assert.equal(witnessValidated(incident('recovered',JSON.stringify({transaction_id:'t',total_cents:WITNESS_TOTAL_CENTS+1}))),false);
  assert.equal(witnessValidated(incident('recovered','{}')),false);
  assert.equal(witnessValidated(null),false);
  assert.equal(WITNESS_TOTAL_CENTS,200000);
});
test('parseEvidence tolerates anything and accepts an already-parsed object',()=>{
  for(const bad of ['not json','null','[1,2]','"text"','42','',undefined,null]) assert.deepEqual(parseEvidence(bad),{});
  assert.deepEqual(parseEvidence({transaction_id:'t'}),{transaction_id:'t'});
});
test('the panel calls only the fixed loopback bridge and never accepts or launches arbitrary commands',()=>{
  const model=readFileSync(new URL('./recette.js',import.meta.url),'utf8');
  const view=readFileSync(new URL('./Recette.jsx',import.meta.url),'utf8');
  assert.match(view,/http:\/\/127\.0\.0\.1:8765/);
  assert.match(view,/fetch\s*\(`\$\{BRIDGE\}\$\{path\}`/);
  assert.match(view,/Authorization:`Bearer \$\{token\}`/);
  assert.doesNotMatch(view,/attack_lab\.py.*spawn|spawn.*attack_lab\.py|shell\s*:/s);
  assert.match(view,/manuellement sur le PC Attaquant/); // the attack remains a manual action on the other PC
  assert.doesNotMatch(model,/fetch\s*\(|XMLHttpRequest|new WebSocket|\beval\s*\(|new Function\s*\(/);
});
