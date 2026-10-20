import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import Chrono from './Chrono.jsx';
import Components from './Components.jsx';
import './style.css';
function App(){
 const [token,T]=useState(''),[password,P]=useState(''),[error,E]=useState(''),[amount,A]=useState('100'),[snap,S]=useState(null),[ops,O]=useState([]),[ml,M]=useState(null),[question,Q]=useState('Comment vérifier la reprise du paiement ?'),[answer,R]=useState(null),[busy,B]=useState(false),[tx,X]=useState(null),[clock,K]=useState(null),[probes,PR]=useState({});
 async function api(path,body,extra={}){
   const r=await fetch(path,{method:body?'POST':'GET',headers:{'Content-Type':'application/json',...(token?{Authorization:'Bearer '+token}:{}),...extra},...(body?{body:JSON.stringify(body)}:{})});
   let data; try{data=await r.json();}catch{data={};}   // a 403 from the WAF or a 502/504 is not JSON: show the status, not a parse error
   if(!r.ok)throw new Error(`${r.status} — ${data.detail||r.statusText||'Service indisponible'}`);return data;
 }
 // Probe one component without throwing: a failure returns a status, so one component being down never hides the others.
 async function probe(path){
   try{const r=await fetch(path,{headers:{Authorization:'Bearer '+token}});let data;try{data=await r.json();}catch{data={};}
     return r.ok?{ok:true,data}:{ok:false,status:r.status,detail:data.detail};}
   catch{return {ok:false,detail:'réseau'};}
 }
 async function login(e){e.preventDefault();try{let data=await api('/auth/token',{username:'alice',password});T(data.access_token);P('');E('');}catch(e){E(e.message);}}
 useEffect(()=>{if(!token)return;let alive=true;const refresh=async()=>{
   const [p,o,m]=await Promise.all([probe('/api/accounts'),probe('/ops/status'),probe('/ops/ml')]);
   if(!alive)return;
   PR({payment:p,remediator:o,detector:m});
   if(p.ok)S(p.data); if(o.ok){O(o.data.incidents);K({now:o.data.now,at:performance.now()});} if(m.ok)M(m.data);
   E(p.ok||o.ok||m.ok?'':'Supervision injoignable — voir l’état des composants.');   // a success clears the transient error; a total failure names where to look
 };refresh();const id=setInterval(refresh,2000);return()=>{alive=false;clearInterval(id);};},[token]);
 async function pay(){B(true);E('');X(null);try{const t=await api('/api/payments',{amount_cents:Number(amount),recipient:'merchant'},{'Idempotency-Key':Array.from(crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('')});X(t.transaction.id);}catch(e){E(e.message);}finally{B(false);}}
 async function ask(){B(true);try{R(await api('/rag/ask',{question}));}catch(e){E(e.message);}finally{B(false);}}
 return <main className="max-w-7xl mx-auto p-6 space-y-6">
  <header className="flex flex-wrap justify-between gap-4 items-center border-b border-slate-700 pb-5"><div><p className="text-cyan-300 text-sm tracking-widest">EPSI · WORKSHOP NATIONAL 2026</p><h1 className="text-3xl font-bold">RESILIENCE<span className="text-cyan-300"> ALPHA</span></h1></div><span className="border border-amber-500 text-amber-300 rounded-full px-4 py-2">LABORATOIRE · DONNÉES FICTIVES</span></header>
  {!token?<form onSubmit={login} className="card max-w-md space-y-4"><h2 className="text-xl">Connexion opérateur · alice</h2><label className="block">Mot de passe du laboratoire<input type="password" value={password} onChange={e=>P(e.target.value)} required autoComplete="current-password"/></label><button>Se connecter</button></form>:<>
  <div className="grid md:grid-cols-3 gap-4"><section className="card"><p className="text-slate-400">État du détecteur ML</p><strong>{ml?.status||'Chargement…'}</strong><p className="text-sm">Score : {ml?.score?.toFixed(4)??'Modèle non entraîné'}</p></section><section className="card"><p className="text-slate-400">Dernière reprise</p><strong className="text-cyan-300">{ops[0]?.status||'Aucun incident traité'}</strong></section><section className="card"><p className="text-slate-400">Conservation du registre</p><strong>{snap?`${snap.total_cents} centimes`:'En attente'}</strong><p className="text-sm">Total attendu : 200 000 centimes</p></section></div>
  <Components probes={probes}/>
  <Chrono incident={ops[0]} serverNow={clock?.now} fetchedAt={clock?.at} socSignals={ml?.soc_signals}/>
  <div className="grid md:grid-cols-2 gap-4"><section className="card space-y-4"><h2 className="text-xl">Transaction fictive</h2><label className="block">Montant en centimes<input type="number" min="1" max="100000" value={amount} onChange={e=>A(e.target.value)}/></label><button disabled={busy} onClick={pay}>Payer le marchand fictif</button>{tx&&<p className="text-green-300 break-all">Transaction confirmée : {tx}</p>}<div>{snap?.accounts.map(a=><p key={a.id}>{a.id} : {a.cents} centimes</p>)}</div></section>
  <section className="card space-y-3"><h2 className="text-xl">Assistant documentaire local</h2><textarea value={question} onChange={e=>Q(e.target.value)}/><button disabled={busy} onClick={ask}>Consulter les procédures</button>{answer&&<div><p className="whitespace-pre-wrap">{answer.answer}</p><p className="text-xs text-cyan-300">{answer.sources.map(s=>s.file+'#'+s.chunk).join(' · ')}</p></div>}</section></div>
  <section className="card"><h2 className="text-xl mb-3">Chronologie des remédiations</h2><div className="overflow-auto"><table className="w-full text-sm text-left"><thead><tr><th>Incident</th><th>État vérifié</th><th>Preuve</th></tr></thead><tbody>{ops.map(i=><tr key={i.id} className="border-t border-slate-700"><td className="py-3">{i.id.slice(0,8)}</td><td>{i.status}</td><td className="max-w-md break-all">{i.evidence}</td></tr>)}</tbody></table></div></section>
  <button onClick={()=>{T('');S(null);PR({});E('');}}>Déconnexion</button></>}
  {error&&<p role="alert" className="rounded-lg border border-rose-600 text-rose-300 p-4">{error}</p>}
  <footer className="text-sm text-slate-400">Une reprise est validée uniquement après une transaction contrôlée et la vérification du registre.</footer>
 </main>;
}
createRoot(document.getElementById('root')).render(<App/>);
