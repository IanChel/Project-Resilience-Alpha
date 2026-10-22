import React from 'react';
import Icon from './icons.jsx';
import {Action, Badge, Status} from './ui.jsx';
import {remainingLabel, trialOutcome, EXPECTED_FAILURES} from './controlTrial.js';
import {shortId} from './nav.js';

// The control-trial surfaces. Both are presentation only: the window state comes from the remediator through
// /ops/status, and the only write either of them triggers is "end the trial now", handled by the shell.

// The warning the shell shows on EVERY page while the remediation is inhibited, with the operator action that
// brings it back immediately. It is deliberately loud and deliberately not dismissible: a trial that nobody
// can see is exactly what this feature must not become.
export default function ControlTrialBanner({window:w,onEnd,busy}){
  if(!w||!w.active)return null;
  const left=remainingLabel(w.remaining);
  return <div role="alert" className="rounded-lg border border-amber-600 bg-amber-950/40 p-4">
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="flex items-start gap-3">
        <Icon name="alert" className="mt-0.5 h-5 w-5 shrink-0 text-amber-300"/>
        <div>
          <p className="font-semibold text-amber-100">Essai témoin en cours — remédiation automatique inhibée</p>
          <p className="mt-1 text-sm text-amber-200">
            Le détecteur continue de mesurer, d’alerter et de journaliser. Le remédiateur n’appliquera aucun
            confinement aux incidents pendant la fenêtre. Le WAF, la connexion opérateur et la limitation des essais restent actifs.
          </p>
          <p className="meta mt-1.5 text-amber-200/80">
            {left?`Réactivation automatique dans ${left}`:'Réactivation automatique à l’échéance de la fenêtre'}
            {w.armedBy?` · armé par ${w.armedBy}`:''}
            {w.maxSeconds?` · plafond du service ${remainingLabel(w.maxSeconds)}`:''}
          </p>
        </div>
      </div>
      <Action busy={busy} busyLabel="Réactivation…" onClick={onEnd} className="secondary shrink-0">
        Réactiver la remédiation maintenant</Action>
    </div>
  </div>;
}

// The second launch action inside the recette card, plus the result of the last trial. Clearly named, clearly
// separate from the protected recette, and never presented as switching security off.
export function TrialLauncher({window:w,status,onStart,starting,canStart,checks}){
  const outcome=trialOutcome(status);
  return <div className="rounded-lg border border-slate-700 p-3 space-y-2">
    <div className="flex flex-wrap items-baseline justify-between gap-2">
      <p className="font-medium">Essai témoin sans remédiation <span className="card-hint">comparaison avec et sans réponse automatique</span></p>
      <Badge tone={w&&w.active?'warn':'muted'}>{w&&w.known?(w.active?'Remédiation inhibée':'Remédiation active'):'État non vérifié'}</Badge>
    </div>
    <p className="text-sm text-slate-300">
      Mesure l’effet de la charge de requêtes de devis sur <code>/api/quotes</code> quand la résolution
      automatique n’intervient pas. Le détecteur détecte et journalise comme d’habitude ; le remédiateur
      n’applique pas son confinement aux incidents pendant toute la fenêtre bornée. Les paiements fictifs sur
      <code>/api/payments</code> servent à mesurer l’impact métier.
    </p>
    {outcome&&<div className="space-y-1">
      <Status tone={outcome.tone} className="text-sm font-medium">{outcome.label}</Status>
      <p className="text-sm text-slate-300">{outcome.detail}</p>
      {checks&&<p className="meta">
        Attendu dans ce mode : {EXPECTED_FAILURES.join(' et ')} en FAIL — ces contrôles vérifient une reprise,
        volontairement inhibée ici. Leurs critères ne sont pas modifiés.
      </p>}
    </div>}
    {w&&w.known&&!w.active&&w.closed&&
      <p className="meta">Dernier essai : {w.closed}{w.incidentId?` · incident ${shortId(w.incidentId)}`:''}</p>}
    <Action busy={starting} busyLabel="Démarrage…" onClick={onStart} disabled={!canStart} className="secondary">
      Lancer un essai témoin sans remédiation</Action>
    <p className="text-xs text-slate-400">
      L’attaque reste lancée à la main sur le PC Attaquant : ce bouton n’émet aucun trafic offensif. La
      remédiation est réactivée à la fin de l’essai, à l’échéance de la fenêtre, si le lanceur échoue, et à tout
      redémarrage du remédiateur. Aucun résultat d’essai témoin n’est marqué PASS.
    </p>
  </div>;
}
