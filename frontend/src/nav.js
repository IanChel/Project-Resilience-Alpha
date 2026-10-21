// Navigation and formatting for the console shell. Pure functions and plain data: no I/O, no clock, no React,
// so the shell's structure and its number formatting are testable without a browser.
export const PAGES=[
  {key:'overview',   icon:'overview',   label:'Vue d’ensemble',           title:'Vue d’ensemble',
   subtitle:'Disponibilité observée, détection et dernière reprise'},
  {key:'payment',    icon:'payment',    label:'Service paiement',         title:'Service paiement',
   subtitle:'Transaction fictive, registre et recette de reprise'},
  {key:'supervision',icon:'supervision',label:'Supervision',              title:'Supervision',
   subtitle:'Détecteur ML, remédiateur, incidents et procédures'},
  {key:'demo',       icon:'demo',       label:'Services de démonstration',title:'Services de démonstration',
   subtitle:'Périmètre fictif de l’entreprise simulée'},
];
export const DEFAULT_PAGE='overview';
export function pageByKey(key){return PAGES.find(p=>p.key===key)||PAGES[0];}
export function isPage(key){return PAGES.some(p=>p.key===key);}

// How the aggregated component health reads on screen. `unknown` is "not polled yet", never "fine".
export const HEALTH={
  up:     {label:'Opérationnel',    tone:'ok'},
  warn:   {label:'Dégradé',         tone:'warn'},
  down:   {label:'Indisponible',    tone:'bad'},
  unknown:{label:'En attente',      tone:'muted'},
};
export function healthLabel(level){return (HEALTH[level]||HEALTH.unknown).label;}
export function healthTone(level){return (HEALTH[level]||HEALTH.unknown).tone;}

// The detector's own status strings (services/detector/main.py), named in French. An unknown value is
// shown as-is rather than guessed at.
export const DETECTOR_STATUS={
  monitoring:'Surveillance active',
  waiting_for_trained_model:'Aucun modèle entraîné',
  telemetry_or_delivery_error:'Erreur de collecte',
};
export function detectorLabel(status){return status?(DETECTOR_STATUS[status]||status):null;}

// Group digits with a non-breaking space: 200000 -> "200 000". Returns null when there is no number to show,
// so a caller shows "—" instead of a fabricated 0.
export function groupDigits(value){
  if(typeof value!=='number'||!Number.isFinite(value))return null;
  const sign=value<0?'-':'';
  return sign+String(Math.trunc(Math.abs(value))).replace(/\B(?=(\d{3})+(?!\d))/g,'\u00a0');
}
export function shortId(id){return typeof id==='string'&&id.length>8?id.slice(0,8):(id||'');}
