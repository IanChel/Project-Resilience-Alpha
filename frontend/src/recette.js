// Live recette state — READ ONLY. It is computed strictly from what the backend reports (the remediator's
// /ops/status incidents and the detector's /ops/ml), never from a browser-side guess. The dashboard cannot and
// does not launch the attack, the observer or any host command; it only reads and names what it observes.
//
// Two rules the reviewer looks for:
//  1. "Reprise vérifiée" demands the DOCUMENTED criteria (docs/09-RECETTE-RENDU.md), not an HTTP 200: the incident
//     must be `recovered` AND the witness transaction validated — a transaction id present AND the ledger total back
//     to 200000. That is exactly what the remediator stores when it reaches the `recovered` stage
//     (services/remediator/main.py: update(id,'recovered',{transaction_id,total_cents,ban})); the witness helper
//     refuses to return unless total==200000 and the transaction is committed. A `recovered` incident whose evidence
//     does not carry that proof is reported NON VÉRIFIÉ, not as a success.
//  2. Never fabricate a state. If supervision is unreachable, the step cannot be confirmed → NON VÉRIFIÉ.
export const WITNESS_TOTAL_CENTS=200000;
export const RECETTE_STATES={
  ready:                 {label:'Aucune recette lancée',                                              tone:'muted',verified:false},
  unreachable:          {label:'NON VÉRIFIÉ — supervision injoignable',                                 tone:'muted',verified:false},
  observing:            {label:'Observation en cours — aucun incident',                                 tone:'muted',verified:false},
  anomaly:              {label:'Anomalie détectée',                                                     tone:'warn', verified:false},
  contained:            {label:'Incident pris en charge — confinement en cours',                        tone:'warn', verified:false},
  verifying:            {label:'Vérification de la reprise en cours',                                    tone:'warn', verified:false},
  recovered:            {label:'Reprise vérifiée',                                                       tone:'ok',   verified:true},
  recovered_unconfirmed:{label:'NON VÉRIFIÉ — reprise annoncée sans preuve de transaction témoin',       tone:'warn', verified:false},
  observed:             {label:'Essai témoin — incident consigné sans remédiation',                      tone:'warn', verified:false},
  failed:               {label:'Échec / délai dépassé — revue manuelle requise',                        tone:'bad',  verified:false},
};
export function parseEvidence(text){
  if(text&&typeof text==='object'&&!Array.isArray(text))return text;   // already parsed
  try{const v=JSON.parse(text);return v&&typeof v==='object'&&!Array.isArray(v)?v:{};}catch{return {};}
}
// The documented witness criterion, read from the incident the remediator published. HTTP 200 alone is NOT this.
export function witnessValidated(incident){
  const e=parseEvidence(incident&&incident.evidence);
  return typeof e.transaction_id==='string'&&e.transaction_id.length>0&&e.total_cents===WITNESS_TOTAL_CENTS;
}
// incident: newest entry of /ops/status (or null). remediatorOk/detectorOk: did that probe succeed this cycle.
// detector: the /ops/ml payload ({anomaly,score,status}).
export function recetteModel({incident=null,remediatorOk=false,detector=null,detectorOk=false,runStartedAt=undefined}={}){
  // Do not present an old recovered incident as the result of a new/current run.
  if(runStartedAt===null)return {key:'ready',...RECETTE_STATES.ready};
  if(!remediatorOk) return {key:'unreachable',...RECETTE_STATES.unreachable};
  const status=incident&&incident.status;
  if(status==='failed')       return {key:'failed',       ...RECETTE_STATES.failed,       incidentId:incident.id};
  if(status==='recovered'){
    const ok=witnessValidated(incident);const key=ok?'recovered':'recovered_unconfirmed';
    return {key,...RECETTE_STATES[key],incidentId:incident.id,witness:ok?parseEvidence(incident.evidence):null};
  }
  // `observed` is the remediator's TERMINAL status for a control trial: the incident was detected and
  // journaled with the remediation deliberately inhibited. It is not a recovery and not a failed recovery.
  if(status==='observed')     return {key:'observed',     ...RECETTE_STATES.observed,     incidentId:incident.id};
  if(status==='verifying')    return {key:'verifying',    ...RECETTE_STATES.verifying,    incidentId:incident.id};
  if(status==='containing')   return {key:'contained',    ...RECETTE_STATES.contained,    incidentId:incident.id};
  if(status==='detected'||status==='accepted') return {key:'anomaly',...RECETTE_STATES.anomaly,incidentId:incident.id};
  // no incident in flight: the detector may still be flagging an anomaly (real field of /ops/ml), otherwise idle.
  if(detectorOk&&detector&&detector.anomaly===true) return {key:'anomaly',...RECETTE_STATES.anomaly};
  return {key:'observing',...RECETTE_STATES.observing};
}
