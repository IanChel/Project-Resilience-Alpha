import React from 'react';
// A small hand-rolled icon set: the project has only react/react-dom, and a few 24px glyphs are not worth a
// dependency. One consistent grid, 1.5 stroke, currentColor, decorative by default (aria-hidden).
const PATHS={
  overview:   'M4 13h7V4H4v9Zm9 7h7v-9h-7v9ZM4 20h7v-5H4v5Zm9-11h7V4h-7v5Z',
  payment:    'M3 9h18M3 7.5A2.5 2.5 0 0 1 5.5 5h13A2.5 2.5 0 0 1 21 7.5v9A2.5 2.5 0 0 1 18.5 19h-13A2.5 2.5 0 0 1 3 16.5v-9ZM7 14h3',
  supervision:'M3 12h3.5l2-5 3.5 11 2.5-7 1.5 3H21',
  demo:       'M12 3 4 7v10l8 4 8-4V7l-8-4Zm0 0v18M4 7l8 4 8-4',
  menu:       'M4 7h16M4 12h16M4 17h16',
  close:      'M6 6l12 12M18 6 6 18',
  logout:     'M15 4h3a2 2 0 0 1 2 2v12a2 2 0 0 1-2 2h-3M10 8l-4 4 4 4M6 12h10',
  chevron:    'M6 9l6 6 6-6',
  shield:     'M12 3 5 6v5.5c0 4 2.9 7.6 7 8.5 4.1-.9 7-4.5 7-8.5V6l-7-3Z',
  check:      'M5 13l4 4L19 7',
  alert:      'M12 9v4m0 3h.01M10.3 4.3 2.6 17.6A1.6 1.6 0 0 0 4 20h16a1.6 1.6 0 0 0 1.4-2.4L13.7 4.3a1.6 1.6 0 0 0-2.8 0Z',
  clock:      'M12 7v5l3 2M21 12a9 9 0 1 1-18 0 9 9 0 0 1 18 0Z',
  ledger:     'M7 4h10a2 2 0 0 1 2 2v14l-3-2-2 2-2-2-2 2-3-2V6a2 2 0 0 1 2-2Zm1 5h8M8 13h5',
};
export default function Icon({name,className='h-5 w-5',title}){
  const d=PATHS[name];
  if(!d)return null;
  return <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"
    strokeLinejoin="round" className={className} aria-hidden={title?undefined:'true'}
    role={title?'img':undefined} focusable="false">{title?<title>{title}</title>:null}<path d={d}/></svg>;
}
// An indeterminate spinner for a button that is working. Decorative: the button's text says what is happening.
export function Spinner({className='h-4 w-4'}){
  return <svg viewBox="0 0 24 24" className={`${className} animate-spin`} aria-hidden="true" focusable="false">
    <circle cx="12" cy="12" r="9" fill="none" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3"/>
    <path d="M21 12a9 9 0 0 0-9-9" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"/>
  </svg>;
}
