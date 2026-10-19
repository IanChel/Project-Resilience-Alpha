// What the recovery chrono shows, computed ONLY from timestamps the backend recorded (incident.stages) and from
// the server clock (`now`). Nothing here starts a timer when the page opens: a browser-side counter that measures
// nothing is exactly what a careful reviewer looks for. While an incident runs, the caller advances the server
// clock by the time since the last poll, so the display moves smoothly between the 2 s refreshes.
export const TARGET_S=60;
export const STEPS=[
  {key:'detected',label:'Détection (alerte du ML)'},
  {key:'containing',label:'Remédiation lancée'},
  {key:'verifying',label:'Healthcheck OK'},
  {key:'recovered',label:'Transaction témoin validée'},
];
const FINAL=['recovered','failed'];
export function parseEvidence(text){
  try{const value=JSON.parse(text);return value&&typeof value==='object'&&!Array.isArray(value)?value:{};}catch{return {};}
}
const isTime=value=>typeof value==='number'&&Number.isFinite(value);
// incident: one entry of /ops/status (newest first). serverNow: the server clock, in seconds.
export function chronoModel(incident,serverNow){
  if(!incident||!incident.stages||!isTime(incident.stages.detected))return {state:'idle'};
  const stages=incident.stages,start=stages.detected,done=FINAL.includes(incident.status);
  const end=done?(isTime(stages[incident.status])?stages[incident.status]:incident.updated):serverNow;
  if(!isTime(end))return {state:'idle'};
  const elapsed=Math.max(0,end-start);
  const state=done?incident.status:'running';
  return {
    state,id:incident.id,elapsed,
    withinTarget:state==='recovered'?elapsed<TARGET_S:null,
    steps:STEPS.map(step=>({...step,at:isTime(stages[step.key])?stages[step.key]:null,
      offset:isTime(stages[step.key])?Math.max(0,stages[step.key]-start):null})),
    ban:parseEvidence(incident.evidence).ban??null,
  };
}
export const seconds=value=>`${value.toFixed(1).replace('.',',')} s`;
export function clock(ts){
  const date=new Date(ts*1000),pad=(n,w=2)=>String(n).padStart(w,'0');
  return `${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}.${pad(date.getMilliseconds(),3)}`;
}
