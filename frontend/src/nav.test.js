// Run with: node --test frontend/src/nav.test.js (no dependency, not part of the Vite bundle).
import test from 'node:test';
import assert from 'node:assert/strict';
import {readFileSync} from 'node:fs';
import {PAGES,DEFAULT_PAGE,pageByKey,isPage,HEALTH,healthLabel,healthTone,DETECTOR_STATUS,detectorLabel,groupDigits,shortId} from './nav.js';

test('the console exposes exactly the four requested sections, each with a title and a subtitle',()=>{
  assert.deepEqual(PAGES.map(p=>p.key),['overview','payment','supervision','demo']);
  for(const page of PAGES){
    assert.ok(page.label&&page.title&&page.subtitle&&page.icon,page.key);
  }
  assert.equal(DEFAULT_PAGE,'overview');
});
test('an unknown page falls back to the first one instead of rendering nothing',()=>{
  assert.equal(pageByKey('supervision').title,'Supervision');
  assert.equal(pageByKey('does-not-exist').key,'overview');
  assert.equal(pageByKey(undefined).key,'overview');
  assert.equal(isPage('demo'),true); assert.equal(isPage('nope'),false);
});
test('health never reads "operational" when nothing has been polled yet',()=>{
  assert.equal(healthLabel('up'),'Opérationnel');
  assert.equal(healthLabel('warn'),'Dégradé');
  assert.equal(healthLabel('down'),'Indisponible');
  assert.equal(healthLabel('unknown'),'En attente');
  assert.equal(healthLabel(undefined),'En attente');          // no data is not good news
  assert.equal(healthTone('up'),'ok'); assert.equal(healthTone('down'),'bad');
  assert.equal(healthTone('whatever'),'muted');
  assert.deepEqual(Object.keys(HEALTH),['up','warn','down','unknown']);
});
test('the detector status is translated, and an unknown status is shown as received',()=>{
  assert.equal(detectorLabel('monitoring'),'Surveillance active');
  assert.equal(detectorLabel('waiting_for_trained_model'),'Aucun modèle entraîné');
  assert.equal(detectorLabel('telemetry_or_delivery_error'),'Erreur de collecte');
  assert.equal(detectorLabel('something_new'),'something_new');   // never silently relabelled
  assert.equal(detectorLabel(undefined),null);                    // the caller renders a dash
  assert.equal(Object.keys(DETECTOR_STATUS).length,3);
});
test('digit grouping, and no number means no value (never a fabricated zero)',()=>{
  assert.equal(groupDigits(200000),'200\u00a0000');
  assert.equal(groupDigits(100000),'100\u00a0000');
  assert.equal(groupDigits(100),'100');
  assert.equal(groupDigits(0),'0');
  assert.equal(groupDigits(-1234),'-1\u00a0234');
  assert.equal(groupDigits(1234567),'1\u00a0234\u00a0567');
  for(const bad of [null,undefined,'200000',NaN,Infinity]) assert.equal(groupDigits(bad),null,String(bad));
});
test('short ids stay short but never break a value that is already short',()=>{
  assert.equal(shortId('9f1c2e7a-0000-4000-8000-000000000000'),'9f1c2e7a');
  assert.equal(shortId('abc'),'abc');
  assert.equal(shortId(''),''); assert.equal(shortId(null),''); assert.equal(shortId(undefined),'');
});
test('the navigation model stays pure: no clock, no I/O, no React',()=>{
  const src=readFileSync(new URL('./nav.js',import.meta.url),'utf8');
  assert.doesNotMatch(src,/Date\.now|performance\.now|new Date\(|fetch\s*\(|from 'react'/);
});
