
async function apiGet(url){ const r = await fetch(url); if(!r.ok) throw new Error(await r.text()); return r.json(); }
async function apiPost(url, payload){ const r = await fetch(url,{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify(payload)}); const j = await r.json(); if(!r.ok || j.ok===false) throw new Error(j.error||JSON.stringify(j)); return j; }
function monthDays(month){ const [y,m]=month.split('-').map(Number); const days=new Date(y,m,0).getDate(); const arr=[]; for(let i=1;i<=days;i++){ const d=new Date(y,m-1,i); arr.push({iso:d.toISOString().slice(0,10), dow:d.toLocaleDateString(undefined,{weekday:'short'})}); } return arr; }
function esc(s){ return String(s??'').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c])); }
