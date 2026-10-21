import React from 'react';
import Icon,{Spinner} from './icons.jsx';
// Shared presentation primitives, so the pages stay about data and not about Tailwind strings.
export const TONE_TEXT={ok:'text-emerald-300',warn:'text-amber-300',bad:'text-rose-300',muted:'text-slate-400',accent:'text-cyan-200'};
export const TONE_DOT ={ok:'bg-emerald-400',warn:'bg-amber-400',bad:'bg-rose-500',muted:'bg-slate-500',accent:'bg-cyan-400'};

export function Dot({tone='muted',className=''}){
  return <span aria-hidden="true" className={`inline-block h-2 w-2 shrink-0 rounded-full ${TONE_DOT[tone]||TONE_DOT.muted} ${className}`}/>;
}
// A status word with its dot. The text carries the meaning, so the colour is never the only signal.
export function Status({tone='muted',children,className=''}){
  return <span className={`inline-flex items-center gap-2 ${TONE_TEXT[tone]||TONE_TEXT.muted} ${className}`}>
    <Dot tone={tone}/>{children}</span>;
}
export function Badge({tone='muted',children}){
  const ring={ok:'border-emerald-700 text-emerald-300',warn:'border-amber-700 text-amber-300',
    bad:'border-rose-700 text-rose-300',muted:'border-slate-700 text-slate-300',accent:'border-cyan-700 text-cyan-200'};
  return <span className={`inline-flex shrink-0 items-center whitespace-nowrap rounded-full border px-2.5 py-0.5 text-xs font-medium ${ring[tone]||ring.muted}`}>{children}</span>;
}
export function Card({title,hint,aside,children,label,className=''}){
  return <section aria-label={label||title} className={`card ${className}`}>
    {(title||aside)&&<div className="card-head">
      <div><h2 className="card-title">{title}</h2>{hint&&<p className="card-hint mt-0.5">{hint}</p>}</div>
      {aside}
    </div>}
    {children}
  </section>;
}
// A headline figure. `value` of null renders an explicit dash: no data is never shown as zero.
export function Stat({label,value,hint,tone='muted',icon}){
  return <div className="card">
    <div className="flex items-center justify-between gap-3">
      <p className="text-sm text-slate-400">{label}</p>
      {icon&&<Icon name={icon} className="h-4 w-4 text-slate-500"/>}
    </div>
    <p className={`mt-2 text-2xl font-semibold tnum ${TONE_TEXT[tone]||'text-slate-100'}`}>{value==null?'—':value}</p>
    {hint&&<p className="meta mt-1">{hint}</p>}
  </div>;
}
// A labelled line in a definition list of observed values.
export function Row({label,value,tone}){
  return <div className="kv">
    <span className="text-sm text-slate-400">{label}</span>
    <span className={`text-sm tnum ${tone?TONE_TEXT[tone]:'text-slate-100'}`}>{value==null?'—':value}</span>
  </div>;
}
// What a panel shows when the API gave nothing: a reason, never an invented value.
export function Empty({children,icon='alert'}){
  return <p className="flex items-start gap-2 rounded-lg border border-dashed border-slate-700 p-4 text-sm text-slate-400">
    <Icon name={icon} className="mt-0.5 h-4 w-4 shrink-0 text-slate-500"/><span>{children}</span></p>;
}
// A button that shows its own loading state and stays disabled while it works.
export function Action({busy,children,busyLabel,className='',...rest}){
  return <button {...rest} disabled={busy||rest.disabled} className={className} aria-busy={busy?'true':undefined}>
    {busy&&<Spinner/>}{busy&&busyLabel?busyLabel:children}</button>;
}
export function Alert({children,tone='bad'}){
  const skin=tone==='bad'?'border-rose-800 bg-rose-950/40 text-rose-200':'border-amber-800 bg-amber-950/30 text-amber-200';
  return <div role="alert" className={`flex items-start gap-3 rounded-lg border p-4 text-sm ${skin}`}>
    <Icon name="alert" className="mt-0.5 h-4 w-4 shrink-0"/><span>{children}</span></div>;
}
