import React,{useEffect,useState} from 'react';
import {createRoot} from 'react-dom/client';
import Login from './Login.jsx';
import Sidebar from './Sidebar.jsx';
import Topbar from './Topbar.jsx';
import OverviewPage from './OverviewPage.jsx';
import PaymentPage from './PaymentPage.jsx';
import SupervisionPage from './SupervisionPage.jsx';
import DemoServicesPage from './DemoServicesPage.jsx';
import ControlTrialBanner from './ControlTrial.jsx';
import {overallHealth} from './components.js';
import {windowModel} from './controlTrial.js';
import {pageByKey,DEFAULT_PAGE} from './nav.js';
import {Alert} from './ui.jsx';
import './style.css';
function App(){
 // session
 const [token,setToken]=useState(''),[challengeId,setChallengeId]=useState(''),[account,setAccount]=useState(''),[pendingEmail,setPendingEmail]=useState('');
 // two error channels: an action failure must stay readable, and not be wiped by the next 2 s supervision poll
 const [actionError,setActionError]=useState(''),[supervisionError,setSupervisionError]=useState(''),[busy,setBusy]=useState(false);
 // observed data
 const [snap,setSnap]=useState(null),[ops,setOps]=useState([]),[ml,setMl]=useState(null),[clock,setClock]=useState(null),[probes,setProbes]=useState({});
 // The control-trial window as the REMEDIATOR reports it, read on the same poll as the incidents: it is the
 // service that enforces the inhibition, so it is the only thing allowed to say whether one is armed.
 const [trial,setTrial]=useState(null);
 // shell + forms
 const [page,setPage]=useState(DEFAULT_PAGE),[navOpen,setNavOpen]=useState(false);
 const [amount,setAmount]=useState('100'),[tx,setTx]=useState(null);
 const [question,setQuestion]=useState('Comment vérifier la reprise du paiement ?'),[answer,setAnswer]=useState(null);
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
 async function requestCode({email,password}){
   setBusy(true);setActionError('');
   try{const data=await api('/auth/operator/challenge',{email,password});setChallengeId(data.challenge_id);setPendingEmail(email);return true;}
   catch(e){setActionError(e.message);return false;}finally{setBusy(false);}
 }
 async function verifyCode({code}){
   setBusy(true);setActionError('');
   try{const data=await api('/auth/operator/verify',{challenge_id:challengeId,code});
     setToken(data.access_token);setAccount(pendingEmail);setChallengeId('');setPendingEmail('');return true;}
   catch(e){setActionError(e.message);return false;}finally{setBusy(false);}
 }
 useEffect(()=>{if(!token)return;let alive=true;const refresh=async()=>{
   const [p,o,m]=await Promise.all([probe('/api/accounts'),probe('/ops/status'),probe('/ops/ml')]);
   if(!alive)return;
   setProbes({payment:p,remediator:o,detector:m});
   if(p.ok)setSnap(p.data); if(o.ok){setOps(o.data.incidents);setClock({now:o.data.now,at:performance.now()});setTrial(o.data.control_trial||null);} if(m.ok)setMl(m.data);
   setSupervisionError(p.ok||o.ok||m.ok?'':'Supervision injoignable — voir l’état des composants.');   // a success clears the transient error; a total failure names where to look
 };refresh();const id=setInterval(refresh,2000);return()=>{alive=false;clearInterval(id);};},[token]);
 async function pay(){setBusy(true);setActionError('');setTx(null);
   try{const t=await api('/api/payments',{amount_cents:Number(amount),recipient:'merchant'},{'Idempotency-Key':Array.from(crypto.getRandomValues(new Uint8Array(16)),x=>x.toString(16).padStart(2,'0')).join('')});setTx(t.transaction.id);}
   catch(e){setActionError(e.message);}finally{setBusy(false);}}
 async function ask(){setBusy(true);setActionError('');
   try{setAnswer(await api('/rag/ask',{question}));}catch(e){setActionError(e.message);}finally{setBusy(false);}}
 // Bring the automatic remediation back now. `stop` is the ONLY write the browser makes to the window: a trial
 // is armed by the host launcher after its own confirmation, never straight from here.
 async function endTrial(){setBusy(true);setActionError('');
   try{setTrial(await api('/ops/control-trial',{action:'stop'}));}catch(e){setActionError(e.message);}finally{setBusy(false);}}
 function logout(){
   setToken('');setAccount('');setChallengeId('');setPendingEmail('');
   setSnap(null);setOps([]);setMl(null);setClock(null);setProbes({});setTrial(null);
   setTx(null);setAnswer(null);setActionError('');setSupervisionError('');
   setPage(DEFAULT_PAGE);setNavOpen(false);
 }
 if(!token)return <Login awaitingCode={!!challengeId} busy={busy} error={actionError}
   onRequestCode={requestCode} onVerify={verifyCode}
   onBack={()=>{setChallengeId('');setPendingEmail('');setActionError('');}}/>;
 const current=pageByKey(page),health=overallHealth(probes);
 const trialWindow=windowModel({trial,remediatorOk:!!probes.remediator?.ok});
 const navigate=key=>{setPage(key);setNavOpen(false);};
 return <div className="min-h-screen">
  <Sidebar current={current.key} onNavigate={navigate} health={health} open={navOpen} onClose={()=>setNavOpen(false)}/>
  <div className="lg:pl-64">
   <Topbar title={current.title} subtitle={current.subtitle} health={health}
     onMenu={()=>setNavOpen(true)} onLogout={logout} account={account}/>
   <main className="mx-auto max-w-7xl space-y-5 p-4 sm:p-6">
    {/* Shown on every page while the remediation is inhibited: a trial nobody can see is what this must never become. */}
    <ControlTrialBanner window={trialWindow} onEnd={endTrial} busy={busy}/>
    {actionError&&<Alert>{actionError}</Alert>}
    {supervisionError&&<Alert tone="warn">{supervisionError}</Alert>}
    {current.key==='overview'&&<OverviewPage probes={probes} ml={ml} ops={ops} snap={snap} clock={clock} onNavigate={navigate}/>}
    {current.key==='payment'&&<PaymentPage amount={amount} onAmount={setAmount} onPay={pay} busy={busy} tx={tx} snap={snap}
      probes={probes} token={token} incident={ops[0]} ml={ml} clock={clock} trialWindow={trialWindow}/>}
    {current.key==='supervision'&&<SupervisionPage probes={probes} ml={ml} ops={ops} clock={clock}
      question={question} onQuestion={setQuestion} onAsk={ask} answer={answer} busy={busy} trialWindow={trialWindow}/>}
    {current.key==='demo'&&<DemoServicesPage/>}
   </main>
  </div>
 </div>;
}
createRoot(document.getElementById('root')).render(<App/>);
