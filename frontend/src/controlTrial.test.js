// Run with: node --test frontend/src/controlTrial.test.js (no dependency, not part of the Vite bundle).
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {windowModel,remainingLabel,trialOutcome,isTrialStatus,closedLabel,canLaunch,
        expectedFailure,EXPECTED_FAILURES,TRIAL_OUTCOMES,TRIAL_MODE,PROTECTED_MODE} from './controlTrial.js';
import {recetteModel} from './recette.js';

test('an unreadable window is NON VÉRIFIÉ: the panel never claims remediation is active',()=>{
  for(const over of [{remediatorOk:false,trial:{active:false}},{remediatorOk:true,trial:null},
                     {remediatorOk:true,trial:'nope'},{remediatorOk:true,trial:[1]},{}]){
    const m=windowModel(over);
    assert.equal(m.known,false,JSON.stringify(over));
    assert.equal(m.active,false,JSON.stringify(over));
    assert.match(m.label,/NON VÉRIFIÉ/);
  }
});
test('an armed window is reported as remediation INHIBITED, with the server countdown and who armed it',()=>{
  const m=windowModel({remediatorOk:true,trial:{active:true,remaining_s:42.4,armed_by:'alice',max_seconds:300}});
  assert.equal(m.known,true); assert.equal(m.active,true); assert.equal(m.tone,'bad');
  assert.match(m.label,/inhibée/); assert.equal(m.remaining,42.4);
  assert.equal(m.armedBy,'alice'); assert.equal(m.maxSeconds,300);
});
test('a closed window says remediation is ACTIVE and how the last trial ended',()=>{
  const m=windowModel({remediatorOk:true,trial:{active:false,closed_reason:'incident_observed',
                                                observed_incident_id:'9f1c2e7a',remaining_s:null}});
  assert.equal(m.active,false); assert.equal(m.tone,'ok');
  assert.equal(m.label,'Remédiation automatique active');
  assert.match(m.closed,/incident a été observé/); assert.equal(m.incidentId,'9f1c2e7a');
});
test('a window missing its numbers degrades to null instead of inventing a countdown',()=>{
  const m=windowModel({remediatorOk:true,trial:{active:true,remaining_s:null,armed_by:'',max_seconds:'300'}});
  assert.equal(m.active,true); assert.equal(m.remaining,null);
  assert.equal(m.armedBy,null); assert.equal(m.maxSeconds,null);
  assert.equal(remainingLabel(m.remaining),null);
});
test('a negative remaining time is never shown as a countdown',()=>{
  const m=windowModel({remediatorOk:true,trial:{active:true,remaining_s:-5}});
  assert.equal(m.remaining,0); assert.equal(remainingLabel(m.remaining),'0 s');
});
test('closedLabel passes an unknown reason through rather than guessing',()=>{
  assert.equal(closedLabel('operator_stopped'),'arrêté par l’opérateur — remédiation réactivée');
  assert.equal(closedLabel('something_new'),'something_new');
  for(const empty of ['',null,undefined,7]) assert.equal(closedLabel(empty),null);
});
test('remainingLabel reads as a duration, in seconds then minutes',()=>{
  assert.equal(remainingLabel(0),'0 s');
  assert.equal(remainingLabel(41.2),'42 s');
  assert.equal(remainingLabel(60),'1 min 00 s');
  assert.equal(remainingLabel(190),'3 min 10 s');
  for(const bad of [null,undefined,NaN,-1,'60']) assert.equal(remainingLabel(bad),null);
});

test('a trial outcome is NEVER a recovery and NEVER a PASS',()=>{
  for(const [key,value] of Object.entries(TRIAL_OUTCOMES)){
    const o=trialOutcome(key);
    assert.equal(o.key,key);
    assert.equal(o.verified,undefined);                       // no trial result carries a verified recovery
    assert.doesNotMatch(value.label,/Reprise vérifiée|PASS/);
    assert.doesNotMatch(value.detail,/reprise réussie|PASS/);
  }
  assert.match(TRIAL_OUTCOMES.control_impact.detail,/pas une reprise/);
  assert.equal(trialOutcome('complete'),null);                // a protected run's status is not a trial outcome
  assert.equal(trialOutcome('recovered'),null);
  assert.equal(trialOutcome(undefined),null);
});
test('an observed impact is distinguished from both a success and a protected failure',()=>{
  assert.equal(trialOutcome('control_impact').tone,'warn');          // an impact is a finding, not an error
  assert.equal(trialOutcome('control_no_impact').tone,'muted');      // nothing measured: nothing claimed
  assert.equal(trialOutcome('control_not_inhibited').tone,'bad');     // the premise broke: the run is invalid
  assert.match(trialOutcome('control_not_inhibited').detail,/À refaire/);
});
test('isTrialStatus tells the two kinds of run apart',()=>{
  for(const key of Object.keys(TRIAL_OUTCOMES)) assert.equal(isTrialStatus(key),true);
  for(const other of ['complete','no_incident','failed','waiting_attack','',null,undefined])
    assert.equal(isTrialStatus(other),false);
});
test('the checks that verify a recovery are the ones expected to fail in a trial',()=>{
  assert.deepEqual(EXPECTED_FAILURES,['acceptance','check_mercredi']);
  assert.equal(expectedFailure('acceptance'),true);
  assert.equal(expectedFailure('check_mercredi'),true);
  assert.equal(expectedFailure('check_mardi'),false);          // M7 measures the load: it is expected to PASS
  assert.equal(expectedFailure('reset_policy'),false);
});

test('nothing can be launched while a trial is armed, or while the launcher is busy',()=>{
  assert.equal(canLaunch({bridgeStatus:'idle'}),true);
  assert.equal(canLaunch({bridgeStatus:'idle',windowActive:true}),false);   // remediation is still inhibited
  assert.equal(canLaunch({bridgeStatus:'idle',starting:true}),false);
  for(const busy of ['running','waiting_attack','checking','offline'])
    assert.equal(canLaunch({bridgeStatus:busy}),false,busy);
  for(const settled of ['complete','no_incident','failed','control_impact','control_no_impact','control_not_inhibited'])
    assert.equal(canLaunch({bridgeStatus:settled}),true,settled);
  assert.equal(canLaunch(),false);                                          // no launcher reached yet
});
test('the two mode names are the ones the launcher and the bridge accept',()=>{
  assert.equal(PROTECTED_MODE,'protected');
  assert.equal(TRIAL_MODE,'control');
});

test('the protected recette model is untouched by the trial model',()=>{
  // The existing verdict must keep behaving exactly as recette.test.js pins it: a trial adds a mode, it does
  // not reinterpret the protected run.
  const witness=JSON.stringify({transaction_id:'4d2f',total_cents:200000});
  const m=recetteModel({incident:{id:'i','status':'recovered',evidence:witness},remediatorOk:true,detectorOk:true});
  assert.equal(m.key,'recovered'); assert.equal(m.verified,true);
  assert.equal(isTrialStatus(m.key),false);
});
test('an incident `observed` by a trial is not reported as a recovery by the recette model',()=>{
  // `observed` is the remediator's terminal status for a control trial: detected and journaled, not remedied.
  const m=recetteModel({incident:{id:'i','status':'observed',evidence:'{}'},remediatorOk:true,detectorOk:true});
  assert.equal(m.verified,false);
  assert.notEqual(m.key,'recovered');
  assert.doesNotMatch(m.label,/Reprise vérifiée/);
});

test('the model is pure: no clock, no network, no React',()=>{
  const source=readFileSync(new URL('./controlTrial.js',import.meta.url),'utf8');
  assert.doesNotMatch(source,/fetch\s*\(|XMLHttpRequest|new WebSocket|\beval\s*\(|new Function\s*\(/);
  assert.doesNotMatch(source,/Date\.now|new Date\(|performance\.now/);      // the countdown comes from the server
  assert.doesNotMatch(source,/from 'react'|setTimeout|setInterval/);
});
test('the browser can only END a trial, never arm one, and never chooses its duration',()=>{
  const source=readFileSync(new URL('./controlTrial.js',import.meta.url),'utf8');
  const view=readFileSync(new URL('./ControlTrial.jsx',import.meta.url),'utf8');
  const shell=readFileSync(new URL('./main.jsx',import.meta.url),'utf8');
  for(const text of [source,view,shell])
    assert.doesNotMatch(text,/seconds\s*:\s*\d/);                      // the launcher derives it, the service caps it
  assert.match(shell,/'\/ops\/control-trial',\{action:'stop'\}/);       // the one write: bring remediation back
  for(const text of [source,view,shell])
    assert.doesNotMatch(text,/action:\s*'start'/);                      // arming goes through the host launcher only
});
test('the trial is launched through the confirmed launcher flow, with its own confirmation',()=>{
  const recette=readFileSync(new URL('./Recette.jsx',import.meta.url),'utf8');
  assert.match(recette,/window\.confirm\(CONFIRM\[mode\]\)/);           // one explicit confirmation per mode
  assert.match(recette,/CONFIRM=\{/);
  const confirmText=recette.split('CONFIRM={')[1].split('};')[0];
  assert.match(confirmText,/ESSAI TÉMOIN SANS REMÉDIATION/);
  assert.match(confirmText,/restent ACTIFS/);                           // not presented as switching security off
  assert.match(confirmText,/réactivée/);                                // says how remediation comes back
  assert.match(confirmText,/manuellement sur le PC Attaquant/);         // the attack stays a manual action
  assert.doesNotMatch(recette,/attack_lab\.py/);                        // the panel launches no offensive traffic
});
