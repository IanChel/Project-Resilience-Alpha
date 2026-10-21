import React,{useState} from 'react';
import Icon from './icons.jsx';
import {Action,Alert,Badge} from './ui.jsx';
// Two-step operator sign-in, unchanged in behaviour: credentials open a challenge, then the 6-digit code sent by
// e-mail completes it. The handlers resolve to true on success so the form can clear what must not linger.
export default function Login({awaitingCode,busy,error,onRequestCode,onVerify,onBack}){
  const [email,setEmail]=useState(''),[password,setPassword]=useState(''),[code,setCode]=useState('');
  async function submitCredentials(e){e.preventDefault(); if(await onRequestCode({email,password}))setPassword('');}
  async function submitCode(e){e.preventDefault(); if(await onVerify({code}))setCode('');}
  return <main className="flex min-h-screen items-center justify-center p-4">
    <div className="w-full max-w-md space-y-6">
      <div className="flex items-center gap-3">
        <span className="rounded-lg border border-cyan-800 bg-cyan-950/50 p-2 text-cyan-300"><Icon name="shield" className="h-6 w-6"/></span>
        <div>
          <p className="text-lg font-semibold leading-tight">RESILIENCE <span className="text-cyan-300">ALPHA</span></p>
          <p className="meta">EPSI · Workshop national 2026 · Groupe 2</p>
        </div>
      </div>
      <div className="card space-y-5">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-base font-semibold">{awaitingCode?'Vérification en deux étapes':'Connexion opérateur'}</h1>
            <p className="card-hint mt-1">{awaitingCode
              ?'Saisissez le code à 6 chiffres envoyé à votre adresse e-mail.'
              :'Accès réservé à l’opérateur de la console de résilience.'}</p>
          </div>
          <Badge tone="muted">Étape {awaitingCode?'2':'1'} / 2</Badge>
        </div>
        {error&&<Alert>{error}</Alert>}
        {awaitingCode
          ?<form onSubmit={submitCode} className="space-y-4" noValidate>
            <div>
              <label className="field-label" htmlFor="otp">Code de vérification</label>
              <input id="otp" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" maxLength={6}
                required autoFocus value={code} onChange={e=>setCode(e.target.value)}
                className="tnum text-center text-lg tracking-[0.4em]" placeholder="000000"/>
              <p className="meta mt-1.5">Le code expire après 5 minutes.</p>
            </div>
            <Action busy={busy} busyLabel="Vérification…" className="w-full">Valider le code</Action>
            <button type="button" className="secondary w-full" onClick={onBack} disabled={busy}>Changer d’identifiants</button>
          </form>
          :<form onSubmit={submitCredentials} className="space-y-4" noValidate>
            <div>
              <label className="field-label" htmlFor="email">Adresse e-mail</label>
              <input id="email" type="email" autoComplete="username" required autoFocus
                value={email} onChange={e=>setEmail(e.target.value)} placeholder="operateur@exemple.fr"/>
            </div>
            <div>
              <label className="field-label" htmlFor="password">Mot de passe opérateur</label>
              <input id="password" type="password" autoComplete="current-password" required
                value={password} onChange={e=>setPassword(e.target.value)}/>
            </div>
            <Action busy={busy} busyLabel="Envoi du code…" className="w-full">Recevoir un code de connexion</Action>
          </form>}
      </div>
      <p className="meta text-center">Laboratoire pédagogique · comptes, soldes et transactions fictifs.</p>
    </div>
  </main>;
}
