import React from 'react';
import Components from './Components.jsx';
import Chrono from './Chrono.jsx';
import {socFor} from './chrono.js';
import {incidentStatusLabel,remainingLabel} from './controlTrial.js';
import {detectorLabel,shortId} from './nav.js';
import {Card,Row,Status,Empty,Action,Badge} from './ui.jsx';
const INCIDENT_TONE={recovered:'ok',failed:'bad',containing:'warn',verifying:'warn',detected:'warn',
  accepted:'warn',observed:'warn'};   // `observed`: consigned during a control trial, deliberately not remediated
// A signal is printed from the fields the detector actually sent, so a new rule shows up without being renamed here.
function signalText(signal){
  return Object.entries(signal).filter(([k])=>k!=='rule')
    .map(([k,v])=>`${k} : ${typeof v==='object'?JSON.stringify(v):v}`).join(' · ');
}
export default function SupervisionPage({probes,ml,ops,clock,question,onQuestion,onAsk,answer,busy,trialWindow}){
  const detectorOk=!!probes.detector?.ok;
  const remediatorOk=!!probes.remediator?.ok;
  const features=ml&&ml.features&&typeof ml.features==='object'?Object.entries(ml.features):[];
  const signals=Array.isArray(ml?.soc_signals)?ml.soc_signals:[];
  return <div className="space-y-5">
    <Components probes={probes}/>

    <Card title="Réponse automatique" hint="Fenêtre d’essai témoin publiée par le remédiateur dans /ops/status"
      aside={<Badge tone={trialWindow?.known?(trialWindow.active?'warn':'ok'):'muted'}>
        {trialWindow?.known?(trialWindow.active?'Inhibée':'Active'):'Non vérifiée'}</Badge>}>
      <Status tone={trialWindow?.tone||'muted'} className="text-sm">{trialWindow?.label||'État non vérifié'}</Status>
      {trialWindow?.active&&<div className="mt-3">
        <Row label="Réactivation automatique dans" value={remainingLabel(trialWindow.remaining)}/>
        <Row label="Armé par" value={trialWindow.armedBy}/>
        <Row label="Plafond du service" value={remainingLabel(trialWindow.maxSeconds)}/>
      </div>}
      {trialWindow?.known&&!trialWindow.active&&<p className="meta mt-2">
        {trialWindow.closed
          ?`Dernier essai témoin : ${trialWindow.closed}${trialWindow.incidentId?` · incident ${shortId(trialWindow.incidentId)}`:''}.`
          :'Aucun essai témoin depuis le dernier démarrage du remédiateur.'}</p>}
    </Card>

    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Détecteur ML" hint="Lecture de /ops/ml"
        aside={detectorOk?<Badge tone={ml?.status==='monitoring'?'ok':'warn'}>{detectorLabel(ml?.status)||'état inconnu'}</Badge>:null}>
        {!detectorOk
          ?<Empty>Le détecteur est injoignable : ni score ni configuration ne peuvent être affichés.</Empty>
          :<div>
            <Row label="État" value={detectorLabel(ml?.status)} tone={ml?.status==='monitoring'?'ok':'warn'}/>
            <Row label="Score courant" value={typeof ml?.score==='number'?ml.score.toFixed(4):null}
              tone={typeof ml?.score==='number'?undefined:'muted'}/>
            <Row label="Observations consécutives requises" value={ml?.config?.consecutive}/>
            <Row label="Paramètre nu" value={ml?.config?.nu}/>
            {typeof ml?.score!=='number'&&<p className="meta mt-3">
              Aucun score n’est mesuré en ce moment : la valeur affichée reste vide plutôt qu’une mesure périmée.</p>}
          </div>}
      </Card>

      <Card title="Caractéristiques observées" hint="Les features transmises au modèle">
        {!detectorOk||features.length===0
          ?<Empty>Aucune caractéristique disponible : le détecteur n’a pas publié de mesure.</Empty>
          :<div>{features.map(([name,value])=>
            <Row key={name} label={name} value={typeof value==='number'?value.toFixed(4):String(value)}/>)}</div>}
      </Card>
    </div>

    <Card title="Signaux du SOC" hint="Corrélations calculées sur les journaux (Loki)">
      {!detectorOk
        ?<Empty>Détecteur injoignable : corrélation indisponible.</Empty>
        :signals.length===0
          ?<Empty>Aucun signal corrélé pour l’instant.</Empty>
          :<ul className="space-y-2">{signals.map((signal,index)=>{
            const correlated=signal.rule==='incident_correlation'?socFor(signals,signal.incident_id):null;
            const tone=correlated?(correlated.ok===true?'ok':correlated.ok===false?'bad':'muted'):'muted';
            return <li key={`${index}-${signal.rule}`} className="border-b border-slate-800 pb-2 last:border-0 last:pb-0">
              <Status tone={tone} className="text-sm font-medium">{signal.rule}</Status>
              <p className="meta mt-1 break-words">{correlated?correlated.text:signalText(signal)}</p>
            </li>;})}</ul>}
    </Card>

    <Chrono incident={ops[0]} serverNow={clock?.now} fetchedAt={clock?.at} socSignals={ml?.soc_signals}/>

    <Card title="Dossiers d’incident" hint="Chronologie des remédiations publiée par le remédiateur">
      {!remediatorOk
        ?<Empty>Le remédiateur ne répond pas : aucun dossier ne peut être affiché.</Empty>
        :ops.length===0
          ?<Empty icon="check">Aucun incident enregistré.</Empty>
          :<div className="overflow-x-auto">
            <table>
              <thead><tr><th>Incident</th><th>État vérifié</th><th>Étapes atteintes</th><th>Preuve</th></tr></thead>
              <tbody>{ops.map(i=>
                <tr key={i.id} className="border-t border-slate-800 align-top">
                  <td className="py-2 font-mono text-xs text-slate-300">{shortId(i.id)}</td>
                  <td className="py-2"><Status tone={INCIDENT_TONE[i.status]||'muted'} className="text-sm">{incidentStatusLabel(i.status)}</Status></td>
                  <td className="py-2 meta">{Object.keys(i.stages||{}).join(' → ')||'—'}</td>
                  <td className="max-w-md break-all py-2 font-mono text-xs text-slate-400">{i.evidence}</td>
                </tr>)}</tbody>
            </table>
          </div>}
    </Card>

    <Card title="Assistant documentaire local" hint="Réponses sourcées dans les procédures du dépôt, modèle exécuté en local">
      <div className="space-y-3">
        <div>
          <label className="field-label" htmlFor="question">Question sur les procédures</label>
          <textarea id="question" rows={3} value={question} onChange={e=>onQuestion(e.target.value)}/>
        </div>
        <Action busy={busy} busyLabel="Consultation…" onClick={onAsk}>Consulter les procédures</Action>
        {answer&&<div className="rounded-lg border border-slate-800 bg-slate-950 p-4">
          <p className="whitespace-pre-wrap text-sm text-slate-100">{answer.answer}</p>
          {answer.sources?.length>0
            ?<p className="meta mt-2 text-cyan-200">{answer.sources.map(s=>`${s.file}#${s.chunk}`).join(' · ')}</p>
            :<p className="meta mt-2">Aucune source citée : l’information est absente du corpus.</p>}
        </div>}
      </div>
    </Card>
  </div>;
}
