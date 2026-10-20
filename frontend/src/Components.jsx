import React from 'react';
import {componentHealth} from './components.js';
const DOT={up:'bg-green-400',warn:'bg-amber-400',down:'bg-rose-500',unknown:'bg-slate-500'};
const TEXT={up:'text-green-300',warn:'text-amber-300',down:'text-rose-300',unknown:'text-slate-400'};
// `probes`: {payment, remediator, detector}, each {ok, data} / {ok:false, status} from the last independent poll.
export default function Components({probes}){
  const rows=componentHealth(probes);
  return <section className="card" aria-label="État des composants">
    <h2 className="text-xl mb-3">État des composants</h2>
    <ul className="grid md:grid-cols-3 gap-3">{rows.map(c=>
      <li key={c.key} className="rounded-xl border border-slate-700 p-3">
        <div className="flex items-center gap-2">
          <span className={`inline-block w-2.5 h-2.5 rounded-full ${DOT[c.level]}`} aria-hidden="true"/>
          <strong>{c.label}</strong>
        </div>
        <p className={`text-sm mt-1 ${TEXT[c.level]}`}>{c.detail}</p>
        <p className="text-xs text-slate-500 mt-1">{c.from}</p>
      </li>)}</ul>
  </section>;
}
