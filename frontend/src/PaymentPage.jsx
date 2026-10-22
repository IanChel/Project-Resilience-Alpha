import React from 'react';
import Recette from './Recette.jsx';
import Chrono from './Chrono.jsx';
import {groupDigits,shortId} from './nav.js';
import {Card,Row,Action,Empty,Badge,Status} from './ui.jsx';
// The payment workspace: run a fictitious transaction, read the ledger the API returns, drive the recette and
// read the recovery chrono. No value here is computed in the browser; all of it comes from /api/accounts.
export default function PaymentPage({amount,onAmount,onPay,busy,paymentResult,snap,probes,token,incident,ml,clock,trialWindow}){
  const paymentOk=!!probes.payment?.ok;
  const amountValue=Number(amount);
  const amountValid=Number.isInteger(amountValue)&&amountValue>=1&&amountValue<=100000;
  const total=groupDigits(snap?.total_cents);
  const intact=snap&&snap.total_cents===200000;
  return <div className="space-y-5">
    <div className="grid gap-4 lg:grid-cols-2">
      <Card title="Transaction fictive" hint="Paiement vers le marchand fictif, avec clé d’idempotence">
        <div className="space-y-4">
          <div>
            <label className="field-label" htmlFor="amount">Montant en centimes</label>
            <input id="amount" type="number" min="1" max="100000" className="tnum"
              value={amount} onChange={e=>onAmount(e.target.value)}/>
            <p className="meta mt-1.5">Entre 1 et 100 000 centimes.</p>
          </div>
          <Action busy={busy} busyLabel="Paiement en cours…" onClick={onPay} disabled={!amountValid}>
            Payer le marchand fictif</Action>
          {probes.payment&&!paymentOk&&<p className="meta">La supervision ne joint pas l’API paiement. Tu peux tenter un paiement pour obtenir sa réponse réelle.</p>}
          {paymentResult?.kind==='success'&&<div role="status" className="rounded-lg border border-emerald-800 bg-emerald-950/30 p-3">
            <Status tone="ok" className="text-sm">Transaction réussie — confirmation du serveur reçue</Status>
            <p className="mt-1 break-all font-mono text-xs text-emerald-200">Référence : {paymentResult.transactionId}</p>
          </div>}
          {paymentResult?.kind==='failure'&&<div role="alert" className="rounded-lg border border-rose-800 bg-rose-950/30 p-3">
            <Status tone="bad" className="text-sm">Transaction échouée</Status>
            <p className="mt-1 text-sm text-rose-200">{paymentResult.message}</p>
          </div>}
        </div>
      </Card>

      <Card title="État du registre" hint="Soldes renvoyés par l’API paiement"
        aside={snap?<Badge tone={intact?'ok':'warn'}>{intact?'Registre intact':'Écart constaté'}</Badge>:null}>
        {!snap
          ?<Empty>Aucun instantané du registre : l’API paiement n’a pas encore répondu.</Empty>
          :<div>
            {snap.accounts?.map(a=><Row key={a.id} label={a.id} value={`${groupDigits(a.cents)} centimes`}/>)}
            <Row label="Total" value={`${total} centimes`} tone={intact?'ok':'warn'}/>
            <Row label="Total attendu" value="200 000 centimes"/>
          </div>}
      </Card>
    </div>

    <Recette token={token} incident={incident} remediatorOk={!!probes.remediator?.ok} detector={ml} detectorOk={!!probes.detector?.ok}
      trialWindow={trialWindow}/>
    <Chrono incident={incident} serverNow={clock?.now} fetchedAt={clock?.at} socSignals={ml?.soc_signals}/>

    <Card title="Dernières transactions" hint="Les 20 dernières écritures renvoyées par l’API">
      {!snap?.transactions?.length
        ?<Empty>Aucune transaction renvoyée par l’API.</Empty>
        :<div className="overflow-x-auto">
          <table>
            <thead><tr><th>Identifiant</th><th>Montant</th><th>Bénéficiaire</th><th>Horodatage serveur</th></tr></thead>
            <tbody>{snap.transactions.map(t=>
              <tr key={t.id} className="border-t border-slate-800">
                <td className="py-2 font-mono text-xs text-slate-300">{shortId(t.id)}</td>
                <td className="tnum py-2">{groupDigits(t.amount)}</td>
                <td className="py-2 text-slate-300">{t.recipient}</td>
                <td className="py-2 meta">{t.created}</td>
              </tr>)}</tbody>
          </table>
        </div>}
    </Card>
  </div>;
}
