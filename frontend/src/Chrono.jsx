import React,{useEffect,useState} from 'react';
import {chronoModel,socFor,FINAL,TARGET_S,seconds,clock} from './chrono.js';
// `serverNow` and `fetchedAt` come from the last /ops/status poll (server clock, and performance.now() at that moment).
export default function Chrono({incident,serverNow,fetchedAt,socSignals}){
  const [,tick]=useState(0);
  const running=!!incident&&!FINAL.includes(incident.status);
  useEffect(()=>{if(!running)return;const id=setInterval(()=>tick(n=>n+1),100);return()=>clearInterval(id);},[running]);
  const advanced=serverNow==null||fetchedAt==null?null:serverNow+(performance.now()-fetchedAt)/1000;
  const m=chronoModel(incident,advanced);
  if(m.state==='idle')return <section className="card" aria-label="Dernier incident enregistré"><h2 className="text-xl">Dernier incident enregistré</h2><p className="text-slate-400 mt-2">Aucun incident traité. Le chrono démarre à la détection et s'arrête quand le service est rétabli et la transaction témoin validée.</p></section>;
  const tone=m.state==='recovered'?'text-green-300':m.state==='failed'?'text-rose-300':'text-amber-300';
  // An `observed` incident is neither a recovery nor a failed recovery: say exactly that, and never call it one.
  const headline=m.state==='running'?'Reprise en cours…':m.state==='recovered'?'Service rétabli'
    :m.state==='observed'?'Essai témoin — aucune remédiation appliquée':'Échec de la reprise';
  const applied=m.ban?.applied??[];
  const soc=socFor(socSignals,m.id);
  return <section className="card space-y-4" aria-label="Chronologie du dernier incident">
    <div className="flex flex-wrap items-baseline justify-between gap-3"><h2 className="text-xl">Dernier incident enregistré <span className="text-sm text-slate-400">{m.state==='observed'?'essai témoin · détection → consignation, sans remédiation':'chrono de reprise · détection → service rétabli'}</span></h2><span className="text-sm text-slate-400">incident {m.id.slice(0,8)}</span></div>
    <div className="flex flex-wrap items-center gap-4"><strong className={`text-5xl tabular-nums ${tone}`}>{seconds(m.elapsed)}</strong>
      <div><p className={tone}>{headline}</p>
        {m.state==='recovered'&&<p className={m.withinTarget?'text-green-300 text-sm':'text-amber-300 text-sm'}>{m.withinTarget?`Sous ${TARGET_S} s`:`Au-delà de ${TARGET_S} s`}</p>}
        {m.state==='failed'&&<p className="text-rose-300 text-sm">Revue manuelle requise : l'automate n'a pas prouvé la reprise.</p>}
        {m.state==='observed'&&<p className="text-amber-300 text-sm">Incident détecté et journalisé pendant un essai témoin : la remédiation automatique n'a volontairement pas été appliquée. Ni une reprise, ni un échec de reprise.</p>}</div></div>
    <ol className="grid md:grid-cols-4 gap-3">{m.steps.map(step=><li key={step.key} className={`rounded-xl border p-3 ${step.at==null?'border-slate-700 text-slate-500':'border-cyan-700'}`}>
      <p className="text-sm">{step.at==null?'○':'●'} {step.label}</p>
      <p className="tabular-nums text-xs mt-1">{step.at==null?(m.state==='running'?'en attente':'non atteint'):`${clock(step.at)} · +${seconds(step.offset)}`}</p></li>)}</ol>
    {soc&&<p className={`text-sm ${soc.ok===true?'text-green-300':soc.ok===false?'text-rose-300':'text-slate-300'}`}>Corrélation SOC · {soc.text}</p>}
    {applied.length>0&&<p className="text-sm text-cyan-300">Adresse bannie temporairement : {applied.join(', ')} ({m.ban.ttl_s} s)</p>}
  </section>;
}
