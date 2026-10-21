import React from 'react';
import Components from './Components.jsx';
import Chrono from './Chrono.jsx';
import {overallHealth} from './components.js';
import {recetteModel} from './recette.js';
import {incidentStatusLabel} from './controlTrial.js';
import {healthLabel,healthTone,detectorLabel,groupDigits,shortId} from './nav.js';
import {Card,Stat,Status,Row,Empty,Badge} from './ui.jsx';
const INCIDENT_TONE={recovered:'ok',failed:'bad',containing:'warn',verifying:'warn',detected:'warn',
  accepted:'warn',observed:'warn'};   // `observed`: consigned during a control trial, deliberately not remediated
// Everything here comes from the three polls the operator can reach: /api/accounts, /ops/status, /ops/ml.
// A value the API did not provide is rendered as a dash by <Stat>, never as a zero.
export default function OverviewPage({probes,ml,ops,snap,clock,onNavigate}){
  const level=overallHealth(probes);
  const incident=ops[0];
  const recette=recetteModel({incident,remediatorOk:!!probes.remediator?.ok,detector:ml,detectorOk:!!probes.detector?.ok});
  const score=typeof ml?.score==='number'?ml.score.toFixed(4):null;
  const total=groupDigits(snap?.total_cents);
  return <div className="space-y-5">
    <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-4">
      <Stat icon="overview" label="Disponibilité des services" value={healthLabel(level)} tone={healthTone(level)}
        hint="3 composants sondés indépendamment"/>
      <Stat icon="supervision" label="Détecteur ML" value={detectorLabel(ml?.status)}
        tone={ml?.status==='monitoring'?'ok':ml?.status?'warn':'muted'}
        hint={score?`Score courant ${score}`:'Aucun score mesuré'}/>
      <Stat icon="ledger" label="Total du registre" value={total?`${total} centimes`:null}
        tone={snap&&snap.total_cents===200000?'ok':snap?'warn':'muted'} hint="Attendu : 200 000 centimes"/>
      <Stat icon="clock" label="Incidents enregistrés" value={probes.remediator?.ok?ops.length:null}
        hint={incident?`Dernier état : ${incidentStatusLabel(incident.status)}`:'Aucun incident traité'}/>
    </div>

    <Components probes={probes}/>
    <Chrono incident={incident} serverNow={clock?.now} fetchedAt={clock?.at} socSignals={ml?.soc_signals}/>

    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Dernière reprise observée" hint="Verdict calculé sur le dernier incident publié par le remédiateur"
        aside={<Badge tone={recette.verified?'ok':'muted'}>{recette.verified?'Vérifiée':'Non vérifiée'}</Badge>}>
        <Status tone={recette.tone} className="text-sm">{recette.label}</Status>
        {recette.key==='observed'&&<p className="meta mt-2">Cet incident a été consigné pendant un essai témoin : la remédiation automatique n’a pas été appliquée. Aucune reprise n’a donc été mesurée.</p>}
        {recette.witness&&<div className="mt-3">
          <Row label="Transaction témoin" value={shortId(recette.witness.transaction_id)} tone="ok"/>
          <Row label="Total du registre" value={`${groupDigits(recette.witness.total_cents)} centimes`} tone="ok"/>
        </div>}
        <p className="meta mt-3">Le lancement de la recette et le détail des contrôles se trouvent sur{' '}
          <button type="button" className="ghost px-1 py-0 text-xs underline" onClick={()=>onNavigate('payment')}>Service paiement</button>.</p>
      </Card>

      <Card title="Derniers incidents" hint={probes.remediator?.ok?`${ops.length} dossier(s) connus`:'Remédiateur injoignable'}
        aside={ops.length>0?<button type="button" className="secondary" onClick={()=>onNavigate('supervision')}>Tout voir</button>:null}>
        {!probes.remediator?.ok
          ?<Empty>Le remédiateur ne répond pas : aucun incident ne peut être affiché.</Empty>
          :ops.length===0
            ?<Empty icon="check">Aucun incident enregistré. La chaîne n’a pas eu à intervenir.</Empty>
            :<ul className="space-y-2">{ops.slice(0,5).map(i=>
              <li key={i.id} className="flex items-center justify-between gap-3 border-b border-slate-800 pb-2 last:border-0 last:pb-0">
                <code className="bg-transparent px-0 text-slate-300">{shortId(i.id)}</code>
                <Status tone={INCIDENT_TONE[i.status]||'muted'} className="text-sm">{incidentStatusLabel(i.status)}</Status>
              </li>)}</ul>}
      </Card>
    </div>
  </div>;
}
