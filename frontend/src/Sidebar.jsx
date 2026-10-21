import React,{useEffect,useRef} from 'react';
import Icon from './icons.jsx';
import {PAGES,healthLabel,healthTone} from './nav.js';
import {Status,Badge} from './ui.jsx';
// Permanent rail on desktop, off-canvas drawer below `lg`. The drawer traps nothing but closes on Escape and on
// a click outside, and the first entry takes focus when it opens, so it is usable from the keyboard alone.
export default function Sidebar({current,onNavigate,health,open,onClose}){
  const first=useRef(null);
  useEffect(()=>{
    if(!open)return;
    first.current?.focus();
    const onKey=e=>{if(e.key==='Escape')onClose();};
    window.addEventListener('keydown',onKey);
    return()=>window.removeEventListener('keydown',onKey);
  },[open,onClose]);
  return <>
    {open&&<div className="fixed inset-0 z-30 bg-slate-950/80 lg:hidden" aria-hidden="true" onClick={onClose}/>}
    <aside aria-label="Navigation principale"
      className={`fixed inset-y-0 left-0 z-40 flex w-72 flex-col border-r border-slate-800 bg-slate-900 transition-transform duration-200 lg:w-64 lg:visible lg:translate-x-0 ${open?'visible translate-x-0':'invisible -translate-x-full'}`}>
      <div className="flex items-start justify-between gap-2 border-b border-slate-800 px-5 py-4">
        <div className="flex items-start gap-3">
          <span className="mt-0.5 rounded-lg border border-cyan-800 bg-cyan-950/50 p-1.5 text-cyan-300"><Icon name="shield"/></span>
          <div>
            <p className="text-sm font-semibold leading-tight">RESILIENCE <span className="text-cyan-300">ALPHA</span></p>
            <p className="meta mt-0.5">Console de résilience</p>
          </div>
        </div>
        <button type="button" className="icon-btn lg:hidden" onClick={onClose} aria-label="Fermer la navigation"><Icon name="close"/></button>
      </div>
      <div className="space-y-2 border-b border-slate-800 px-5 py-4">
        <p className="meta uppercase tracking-wider">Environnement</p>
        <Badge tone="warn">Démonstration · données fictives</Badge>
        <Status tone={healthTone(health)} className="text-sm">{healthLabel(health)}</Status>
      </div>
      <nav className="flex-1 overflow-y-auto p-3">
        <ul className="space-y-1">{PAGES.map((page,index)=>{
          const active=page.key===current;
          return <li key={page.key}>
            <button type="button" ref={index===0?first:null} aria-current={active?'page':undefined}
              onClick={()=>onNavigate(page.key)}
              className={`nav-item ${active?'nav-item-active':''}`}>
              <Icon name={page.icon} className="h-[18px] w-[18px] shrink-0"/>
              <span className="truncate text-left">{page.label}</span>
            </button>
          </li>;})}</ul>
      </nav>
      <p className="border-t border-slate-800 px-5 py-4 meta">
        Une reprise n’est validée qu’après une transaction témoin et la vérification du registre.</p>
    </aside>
  </>;
}
