// Control trial ("essai témoin") model — READ ONLY and pure. Everything it reports comes from the remediator's
// own `control_trial` window in /ops/status and from the host launcher's run state. Nothing is guessed here.
//
// The one rule this file exists to enforce: a control trial must NEVER read as a recovery. A trial deliberately
// inhibits the remediation whose success "Reprise vérifiée" certifies, so its outcomes have their own words —
// an impact, or no impact — and none of them is a success of the protected recette.
export const PROTECTED_MODE='protected';
export const TRIAL_MODE='control';

// How the last trial ended, in the operator's words. An unknown reason is shown as it came, never invented.
export const CLOSED_REASONS={
  incident_observed:'un incident a été observé — remédiation réactivée',
  expired:'échéance atteinte — remédiation réactivée',
  operator_stopped:'arrêté par l’opérateur — remédiation réactivée',
};
export function closedLabel(reason){
  return typeof reason==='string'&&reason?(CLOSED_REASONS[reason]||reason):null;
}

// The remediator's window exactly as the service publishes it. `known:false` means we could not read it: the
// panel says so rather than claiming remediation is active.
export function windowModel({trial=null,remediatorOk=false}={}){
  if(!remediatorOk||!trial||typeof trial!=='object'||Array.isArray(trial))
    return {known:false,active:false,tone:'muted',remaining:null,armedBy:null,closed:null,incidentId:null,
            label:'État de la remédiation NON VÉRIFIÉ — supervision injoignable'};
  if(trial.active===true)
    return {known:true,active:true,tone:'bad',
            label:'Remédiation automatique inhibée — essai témoin en cours',
            remaining:Number.isFinite(trial.remaining_s)?Math.max(0,trial.remaining_s):null,
            armedBy:typeof trial.armed_by==='string'&&trial.armed_by?trial.armed_by:null,
            maxSeconds:Number.isFinite(trial.max_seconds)?trial.max_seconds:null,
            closed:null,incidentId:null};
  return {known:true,active:false,tone:'ok',label:'Remédiation automatique active',
          remaining:null,armedBy:null,closed:closedLabel(trial.closed_reason),
          incidentId:typeof trial.observed_incident_id==='string'&&trial.observed_incident_id?trial.observed_incident_id:null};
}

// A countdown in words, from the seconds the SERVER reported for its own window — never a browser clock.
export function remainingLabel(seconds){
  if(!Number.isFinite(seconds)||seconds<0)return null;
  const whole=Math.ceil(seconds);
  return whole<60?`${whole} s`:`${Math.floor(whole/60)} min ${String(whole%60).padStart(2,'0')} s`;
}

// The launcher's verdict for a finished trial. None of these is a recovery, and none of them is a PASS.
export const TRIAL_OUTCOMES={
  control_impact:{label:'Impact observé sans remédiation',tone:'warn',
    detail:'La charge de requêtes de devis sur /api/quotes a eu un effet mesurable alors que la remédiation était inhibée. C’est l’impact constaté, pas une reprise.'},
  control_no_impact:{label:'Aucun impact mesuré',tone:'muted',
    detail:'Ni rejet de capacité sur la fenêtre, ni paiement fictif refusé : cet essai n’a rien démontré.'},
  control_not_inhibited:{label:'Essai invalide — la remédiation s’est appliquée',tone:'bad',
    detail:'Un incident est allé au-delà de l’observation : l’essai n’a pas comparé ce qu’il devait comparer. À refaire.'},
};
export function trialOutcome(status){
  return TRIAL_OUTCOMES[status]?{key:status,...TRIAL_OUTCOMES[status]}:null;
}
// A control trial never produces the protected recette's verdict, whatever the launcher reports.
export function isTrialStatus(status){return Object.hasOwn(TRIAL_OUTCOMES,status||'');}

// The remediator's terminal status for an incident consigned during a trial. Spelled out wherever it is shown,
// because the bare word could be read as "handled" when the whole point is that it was not.
export const OBSERVED_STATUS='observed';
export function incidentStatusLabel(status){
  return status===OBSERVED_STATUS?'observed (essai témoin, non remédié)':status;
}

// acceptance.py and check_mercredi.py verify a RECOVERY, which a trial inhibits on purpose: their FAIL is
// expected here. Their PASS criteria are untouched — only the way the result is READ changes.
export const EXPECTED_FAILURES=['acceptance','check_mercredi'];
export function expectedFailure(name){return EXPECTED_FAILURES.includes(name);}

// The launcher runs one recette at a time, in either mode. A run also needs the window to be closed: a trial
// still armed would either inhibit a protected recette or stack a second trial on the first, and neither
// result could be read. The launcher must be reachable and settled, never mid-run.
const SETTLED=['idle','complete','no_incident','control_impact','control_no_impact','control_not_inhibited','failed'];
export function canLaunch({bridgeStatus='offline',starting=false,windowActive=false}={}){
  return !starting&&!windowActive&&SETTLED.includes(bridgeStatus);
}
