// Per-component health for the dashboard (sujet 3.1: the jury must observe "les composants").
// Derived ONLY from the polls the operator can actually reach through the WAF: /api/accounts (payment + DB +
// operator auth), /ops/status (remediator), /ops/ml (detector). Each is polled independently, so one component
// being down never hides the others. Pure functions: same input, same output, testable without a browser.

import {groupDigits} from './nav.js';   // one digit grouping for the whole console
// A probe result is {ok:true, data} or {ok:false, status, detail}. `data` is the parsed JSON when ok.
export const COMPONENTS=[
  {key:'payment',   label:'API paiement + base', from:'Base de données et traitement des transactions'},
  {key:'remediator',label:'Moteur de remédiation',from:'Reçoit les alertes et exécute la reprise'},
  {key:'detector',  label:'Détecteur ML',        from:'Modèle d’anomalie branché sur la supervision'},
];
// level: 'up' (green), 'warn' (amber: reachable but not fully ready), 'down' (red: unreachable), 'unknown' (not polled yet)
function detectorDetail(data){
  const s=data&&data.status;
  if(s==='monitoring') return {level:'up',detail:'monitoring'+(typeof data.score==='number'?` · score ${data.score.toFixed(3)}`:'')};
  if(s==='waiting_for_trained_model') return {level:'warn',detail:'aucun modèle entraîné'};
  if(s==='telemetry_or_delivery_error') return {level:'warn',detail:'erreur de collecte (Prometheus/Loki)'};
  return {level:'warn',detail:'état '+(s||'inconnu')};
}
function one(component,probe){
  const base={key:component.key,label:component.label,from:component.from};
  if(!probe) return {...base,level:'unknown',detail:'en attente…'};
  if(!probe.ok) return {...base,level:'down',detail:probe.status?`injoignable (${probe.status})`:'injoignable'};
  if(component.key==='detector') return {...base,...detectorDetail(probe.data)};
  if(component.key==='payment'){
    const total=probe.data&&probe.data.total_cents;
    return {...base,level:'up',detail:typeof total==='number'?`registre ${groupDigits(total)} centimes`:'joignable'};
  }
  return {...base,level:'up',detail:'joignable'};   // remediator: /ops/status answered
}
// probes: {payment, remediator, detector} (any may be undefined before the first poll).
export function componentHealth(probes){
  return COMPONENTS.map(c=>one(c,(probes||{})[c.key]));
}
// One-line summary for a badge: worst level wins, so a single red component is visible at a glance.
export function overallHealth(probes){
  const levels=componentHealth(probes).map(c=>c.level);
  if(levels.includes('down')) return 'down';
  if(levels.includes('unknown')) return 'unknown';
  if(levels.includes('warn')) return 'warn';
  return 'up';
}
