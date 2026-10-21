import React,{useEffect,useRef,useState} from 'react';
import Icon from './icons.jsx';
import {healthLabel,healthTone} from './nav.js';
import {Status} from './ui.jsx';
// Thin header: where you are, the one global state worth seeing everywhere, and the session menu.
export default function Topbar({title,subtitle,health,onMenu,onLogout,account}){
  const [menu,setMenu]=useState(false);
  const box=useRef(null);
  useEffect(()=>{
    if(!menu)return;
    const onKey=e=>{if(e.key==='Escape')setMenu(false);};
    const onClick=e=>{if(box.current&&!box.current.contains(e.target))setMenu(false);};
    window.addEventListener('keydown',onKey); window.addEventListener('mousedown',onClick);
    return()=>{window.removeEventListener('keydown',onKey); window.removeEventListener('mousedown',onClick);};
  },[menu]);
  return <header className="sticky top-0 z-20 border-b border-slate-800 bg-slate-950/90 backdrop-blur">
    <div className="flex items-center gap-3 px-4 py-3 sm:px-6">
      <button type="button" className="icon-btn lg:hidden" onClick={onMenu} aria-label="Ouvrir la navigation"><Icon name="menu"/></button>
      <div className="min-w-0 flex-1">
        <h1 className="truncate text-lg font-semibold leading-tight">{title}</h1>
        {subtitle&&<p className="meta truncate">{subtitle}</p>}
      </div>
      <Status tone={healthTone(health)} className="hidden text-sm sm:inline-flex">{healthLabel(health)}</Status>
      <div className="relative" ref={box}>
        <button type="button" className="secondary" aria-haspopup="menu" aria-expanded={menu}
          onClick={()=>setMenu(v=>!v)}>
          <span className="hidden max-w-[12rem] truncate sm:inline">{account||'Session opérateur'}</span>
          <span className="sm:hidden">Session</span>
          <Icon name="chevron" className={`h-4 w-4 transition-transform ${menu?'rotate-180':''}`}/>
        </button>
        {menu&&<div role="menu" aria-label="Session"
          className="absolute right-0 mt-2 w-60 rounded-lg border border-slate-800 bg-slate-900 p-2 shadow-xl shadow-slate-950/50">
          <p className="px-2 py-1.5 meta break-all">{account?`Connecté : ${account}`:'Opérateur authentifié (code de vérification validé)'}</p>
          <button type="button" role="menuitem" className="ghost w-full justify-start" onClick={()=>{setMenu(false);onLogout();}}>
            <Icon name="logout" className="h-4 w-4"/>Se déconnecter</button>
        </div>}
      </div>
    </div>
  </header>;
}
