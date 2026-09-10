import React, {useEffect, useState} from 'react';
import {BACKEND_URL} from '../config';
export default function PayPicker({amount=0}:{amount?:number}){
  const [d,setD]=useState<any>(null);
  useEffect(()=>{fetch(`${BACKEND_URL}/api/pay`).then(r=>r.json()).then(setD).catch(()=>{});},[]);
  if(!d) return <div>Loading payment options…</div>;
  const btn:React.CSSProperties={padding:'12px 16px',border:'1px solid #333',borderRadius:8,textDecoration:'none',color:'#fff',background:'#111',cursor:'pointer',textAlign:'center'};
  return (<div style={{display:'grid',gap:12,padding:16}}>
    <a href={`${d.cashapp.url}/${amount||''}`} target="_blank" rel="noreferrer" style={btn}>Pay with Cash App (${d.cashapp.tag})</a>
    <button onClick={()=>navigator.clipboard.writeText(d.chime.tag)} style={btn}>Pay with Chime — copy ${d.chime.tag}</button>
    {d.lightning.enabled ? <a href={`lightning:${d.lightning.address}`} style={btn}>Bitcoin Lightning ⚡ {d.lightning.address}</a> : <div style={{opacity:.6}}>Bitcoin Lightning coming soon</div>}
  </div>);
}
