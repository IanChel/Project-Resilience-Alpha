import React,{useEffect,useState} from 'react';
import {recetteModel,WITNESS_TOTAL_CENTS} from './recette.js';
const BRIDGE='http://127.0.0.1:8765';
const TONE={ok:'text-green-300',warn:'text-amber-300',bad:'text-rose-300',muted:'text-slate-400'};
const DOT={ok:'●',warn:'●',bad:'●',muted:'○'};
const PHASE={idle:'Prêt',starting:'Démarrage du lanceur',resetting:'Réinitialisation de la politique',restarting:'Redémarrage de payment',waiting_ready:'Vérification du WAF et de payment',starting_observer:'Démarrage de l’observateur',waiting_attack:'Observateur prêt — lancez l’attaque sur le PC Attaquant',checking:'Exécution des contrôles',complete:'Recette terminée',failed:'Recette en échec'};

// The bridge is bound to loopback on the HOST. It accepts only a fixed recipe operation after validating the
// operator bearer token through the WAF. It never accepts a command or starts the attack script.
export default function Recette({token,incident,remediatorOk,detector,detectorOk}){
  const [bridge,setBridge]=useState(null),[bridgeError,setBridgeError]=useState(''),[starting,setStarting]=useState(false);
  async function request(path,method='GET'){
    const response=await fetch(`${BRIDGE}${path}`,{method,headers:{Authorization:`Bearer ${token}`,...(method==='POST'?{'Content-Type':'application/json'}:{})},...(method==='POST'?{body:JSON.stringify({confirmed:true})}:{})});
    const body=await response.json().catch(()=>({}));
    if(!response.ok)throw new Error(body.error==='run_already_active'?'Une recette est déjà en cours.':body.error||`Lanceur local : HTTP ${response.status}`);
    return body;
  }
  useEffect(()=>{
    if(!token)return;
    let alive=true;
    const poll=async()=>{try{const value=await request('/status');if(alive){setBridge(value);setBridgeError('');}}
      catch(e){if(alive){setBridge(null);setBridgeError(e.message.includes('Failed to fetch')?'Lancez le lanceur sur le PC Hôte : py -3.12 scripts/recette_bridge.py. Autorisez l’accès au réseau local si le navigateur le demande.':e.message);}}};
    poll();const id=setInterval(poll,1500);return()=>{alive=false;clearInterval(id);};
  },[token]);
  async function start(){
    if(!window.confirm('Un nouvel essai va supprimer uniquement la politique de confinement, redémarrer payment, puis lancer acceptance. Confirmez que l’attaque précédente est arrêtée et qu’aucune recette n’est en cours. L’attaque devra être lancée manuellement sur le PC Attaquant.'))return;
    setStarting(true);setBridgeError('');
    try{setBridge(await request('/start','POST'));}catch(e){setBridgeError(e.message);}finally{setStarting(false);}
  }
  const hasRun=!!bridge?.started_at;
  const started=bridge?.server_started_at;
  const freshIncident=hasRun&&Number.isFinite(started)&&incident&&Number(incident.created)>=started?incident:null;
  const m=recetteModel({incident:freshIncident,remediatorOk,detector,detectorOk,runStartedAt:hasRun?started:null});
  const tone=TONE[m.tone]||TONE.muted;
  const currentStatus=bridge?.status||'offline';
  const phaseLabel=currentStatus==='waiting_attack'&&freshIncident
    ?`Incident observé — état ${freshIncident.status}`
    :(PHASE[bridge?.phase]||'Non connecté');
  const canStart=!!bridge&&!starting&&['idle','complete','failed'].includes(currentStatus);
  return <section className="card space-y-4" aria-label="Recette">
    <div className="flex flex-wrap items-baseline justify-between gap-3">
      <h2 className="text-xl">Recette <span className="text-sm text-slate-400">état observé et lancement opérateur</span></h2>
      {m.incidentId&&<span className="text-sm text-slate-400">incident {m.incidentId.slice(0,8)}</span>}
    </div>
    <p className={`text-lg ${tone}`}><span aria-hidden="true">{DOT[m.tone]||'○'}</span> {m.label}</p>
    {m.key==='recovered'&&m.witness&&
      <p className="text-sm text-green-300">Transaction témoin {m.witness.transaction_id.slice(0,8)} validée · registre {m.witness.total_cents} centimes (cible {WITNESS_TOTAL_CENTS}).</p>}
    {m.key==='recovered_unconfirmed'&&
      <p className="text-sm text-amber-300">Le remédiateur annonce une reprise mais la preuve ne contient pas la transaction témoin et le total du registre : non validé.</p>}
    {m.key==='unreachable'&&<p className="text-sm text-slate-400">La supervision est injoignable : état de reprise non vérifié.</p>}
    <div className="rounded-lg border border-slate-700 p-3 space-y-2">
      <p className="font-medium">Lanceur Hôte : <span className={currentStatus==='failed'?'text-rose-300':'text-cyan-200'}>{phaseLabel}</span></p>
      {bridge?.exit_code!==null&&bridge?.exit_code!==undefined&&<p className="text-sm text-slate-300">Code de fin : {bridge.exit_code}</p>}
      {hasRun&&<div className="flex flex-wrap gap-3 text-sm">{[['acceptance',bridge.acceptance],['check_mardi',bridge.check_mardi],['check_mercredi',bridge.check_mercredi]].map(([name,value])=><span key={name}>{name} : {value||'en attente'}</span>)}</div>}
      {bridge?.result_file&&<p className="text-xs text-slate-400">Récapitulatif enregistré : runtime/evidence/{bridge.result_file}</p>}
      {bridge?.details?.length>0&&<div className="space-y-1 text-sm" role="status" aria-label="Détails de la recette">
        <p className="font-medium">Détails du dernier résultat</p>
        <ul className="list-disc space-y-1 pl-5 text-slate-300">{bridge.details.slice(-12).map((line,index)=><li key={`${index}-${line}`}>{line}</li>)}</ul>
      </div>}
      {bridgeError&&<p role="alert" className="text-sm text-amber-200">{bridgeError}</p>}
      <button type="button" onClick={start} disabled={!canStart}>
        {starting?'Démarrage…':hasRun?'Réinitialiser et démarrer une nouvelle recette':'Réinitialiser et démarrer la recette'}
      </button>
      <p className="text-xs text-slate-400">Le bouton efface uniquement la politique, redémarre payment, vérifie le WAF, puis lance acceptance et les contrôles. L’attaque doit être lancée à la main sur le PC Attaquant. Gardez le terminal du lanceur ouvert.</p>
    </div>
  </section>;
}
