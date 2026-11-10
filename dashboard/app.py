"""Dashboard container: the laptop POSTs one small record per frame to /report; the page polls /api/state."""
import statistics
from collections import deque

from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse

app = FastAPI()
records = deque(maxlen=600)


@app.post("/report")
async def report(req: Request):
    records.append(await req.json())
    return {"n": len(records)}


@app.post("/reset")
def reset():
    records.clear()
    return {"ok": True}


def _stats(rs):
    lat = [r["latency_ms"] for r in rs]
    if not lat:
        return {"n": 0, "mean": None, "p95": None}
    s = sorted(lat)
    return {"n": len(lat), "mean": statistics.fmean(lat), "p95": s[min(len(s) - 1, int(0.95 * len(s)))]}


@app.get("/api/state")
def state():
    rs = list(records)
    return {
        "records": rs[-200:],
        "mec": _stats([r for r in rs if r["path"] == "MEC"]),
        "local": _stats([r for r in rs if r["path"] == "LOCAL"]),
        "total": len(rs),
    }


PAGE = r"""<!doctype html><html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1"><title>5G Adaptive Offloading</title>
<style>
:root{--bg:#0b1020;--panel:#131a2e;--panel2:#18213a;--line:#25304f;--text:#e8ecf7;--mute:#8d99b8;
--mec:#22c55e;--loc:#f59e0b;--rtt:#38bdf8;--bad:#ef4444}
*{box-sizing:border-box}
body{margin:0;background:radial-gradient(1200px 600px at 10% -10%,#17224a 0,var(--bg) 60%);color:var(--text);
font-family:Inter,system-ui,Segoe UI,Roboto,sans-serif;padding:22px 26px}
header{display:flex;align-items:center;justify-content:space-between;gap:12px;margin-bottom:18px;flex-wrap:wrap}
h1{margin:0;font-size:22px;letter-spacing:.2px}h1 small{display:block;color:var(--mute);font-weight:400;font-size:13px;margin-top:3px}
.right{display:flex;gap:10px;align-items:center}
.pill{display:inline-flex;align-items:center;gap:8px;padding:7px 13px;border-radius:999px;background:var(--panel);border:1px solid var(--line);font-size:13px;font-weight:600}
.dot{width:9px;height:9px;border-radius:50%;background:var(--mute)}.live .dot{background:var(--mec);box-shadow:0 0 0 0 rgba(34,197,94,.6);animation:p 1.6s infinite}
@keyframes p{70%{box-shadow:0 0 0 9px rgba(34,197,94,0)}100%{box-shadow:0 0 0 0 rgba(34,197,94,0)}}
button{background:var(--panel);color:var(--mute);border:1px solid var(--line);border-radius:10px;padding:7px 12px;cursor:pointer;font-size:13px}
button:hover{color:var(--text)}
.grid{display:grid;gap:14px}.card{background:linear-gradient(180deg,var(--panel),var(--panel2));border:1px solid var(--line);border-radius:16px;padding:16px 18px}
.lbl{color:var(--mute);font-size:12px;letter-spacing:.8px;text-transform:uppercase;margin-bottom:6px}
.hero{display:grid;grid-template-columns:1.25fr 1fr;gap:14px;margin-bottom:14px}
.hero .where{font-size:50px;font-weight:800;line-height:1.05;letter-spacing:-.5px}
.hero.mec .where{color:var(--mec)}.hero.loc .where{color:var(--loc)}
.why{font-size:19px;margin-top:12px;line-height:1.4}.saw{margin-top:12px;color:var(--mute);font-size:14px}.saw b{color:var(--text)}
.meter .row{display:flex;align-items:center;gap:10px;margin:10px 0}.meter .nm{width:92px;font-size:13px;color:var(--mute)}
.bar{flex:1;height:22px;background:#0d1329;border-radius:8px;overflow:hidden}.bar i{display:block;height:100%;border-radius:8px;transition:width .5s}
.meter .v{width:78px;text-align:right;font-weight:700;font-size:18px}.meter .hint{font-size:13px;color:var(--mute);margin-top:6px;line-height:1.4}
.kpis{grid-template-columns:repeat(6,1fr);margin-bottom:14px}
.kpi .n{font-size:32px;font-weight:800;letter-spacing:-.5px}.kpi .u{font-size:14px;color:var(--mute);font-weight:500;margin-left:3px}.kpi .s{font-size:12px;color:var(--mute);margin-top:3px}
.charts{grid-template-columns:1.6fr 1fr;margin-bottom:14px}canvas{width:100%;height:250px;display:block}
.legend{display:flex;gap:14px;flex-wrap:wrap;color:var(--mute);font-size:12px;margin-top:8px}.legend span::before{content:"";display:inline-block;width:10px;height:10px;border-radius:50%;margin-right:6px;vertical-align:-1px;background:var(--c)}
.legend .ln::before{border-radius:2px;height:3px;vertical-align:3px;width:16px}
table{width:100%;border-collapse:collapse;font-size:14px}th{color:var(--mute);font-size:12px;text-transform:uppercase;letter-spacing:.7px;text-align:left;padding:6px 8px;border-bottom:1px solid var(--line)}
td{padding:9px 8px;border-bottom:1px solid #1d2744}tr:last-child td{border:0}td.num{font-variant-numeric:tabular-nums}
.tag{display:inline-block;min-width:78px;text-align:center;padding:3px 10px;border-radius:8px;font-weight:700;font-size:12px}
.tag.MEC{background:rgba(34,197,94,.15);color:var(--mec)}.tag.LOCAL{background:rgba(245,158,11,.15);color:var(--loc)}
.empty{color:var(--mute);padding:30px;text-align:center}
@media(max-width:1100px){.hero,.charts{grid-template-columns:1fr}.kpis{grid-template-columns:repeat(3,1fr)}}
</style></head><body>
<header>
 <h1>5G Adaptive Computation Offloading<small>Each camera frame is processed on the laptop or sent over 5G to the MEC server, whichever is faster right now.</small></h1>
 <div class="right"><span class="pill" id="net"><span class="dot"></span><span id="nettxt">Waiting for data</span></span>
 <span class="pill" id="livepill"><span class="dot"></span><span id="livetxt">No data</span></span>
 <button onclick="fetch('/reset',{method:'POST'})">Reset</button></div>
</header>

<div class="hero" id="hero">
 <div class="card"><div class="lbl">This frame is running on</div><div class="where" id="where">&ndash;</div>
  <div class="why" id="why">Start the controller to see live decisions.</div>
  <div class="saw" id="saw"></div></div>
 <div class="card meter"><div class="lbl">Estimated time per frame</div>
  <div class="row"><div class="nm">MEC server</div><div class="bar"><i id="bm" style="width:0;background:var(--mec)"></i></div><div class="v" id="vm">&ndash;</div></div>
  <div class="row"><div class="nm">Laptop</div><div class="bar"><i id="bl" style="width:0;background:var(--loc)"></i></div><div class="v" id="vl">&ndash;</div></div>
  <div class="hint" id="hint">The shorter bar wins. Server time includes the upload over 5G and the network round trip.</div></div>
</div>

<div class="grid kpis">
 <div class="card kpi"><div class="lbl">Latency now</div><div><span class="n" id="k1">&ndash;</span><span class="u">ms</span></div><div class="s">this frame, end to end</div></div>
 <div class="card kpi"><div class="lbl">Average latency</div><div><span class="n" id="k2">&ndash;</span><span class="u">ms</span></div><div class="s">last 30 frames</div></div>
 <div class="card kpi"><div class="lbl">Network RTT</div><div><span class="n" id="k3">&ndash;</span><span class="u">ms</span></div><div class="s">laptop to MEC over 5G</div></div>
 <div class="card kpi"><div class="lbl">MEC server load</div><div><span class="n" id="k4">&ndash;</span><span class="u">%</span></div><div class="s">CPU on the VM</div></div>
 <div class="card kpi"><div class="lbl">Sent to server</div><div><span class="n" id="k5">&ndash;</span><span class="u">%</span></div><div class="s">of last 30 frames</div></div>
 <div class="card kpi"><div class="lbl">Frames processed</div><div><span class="n" id="k6">&ndash;</span></div><div class="s" id="k6s"></div></div>
</div>

<div class="grid charts">
 <div class="card"><div class="lbl">Latency per frame</div><canvas id="c1"></canvas>
  <div class="legend"><span style="--c:var(--mec)">frame on MEC</span><span style="--c:var(--loc)">frame on laptop</span>
  <span class="ln" style="--c:var(--mec)">server estimate</span><span class="ln" style="--c:var(--loc)">laptop estimate</span></div></div>
 <div class="card"><div class="lbl">Network round-trip time (ms)</div><canvas id="c2"></canvas>
  <div class="legend"><span class="ln" style="--c:var(--rtt)">RTT to MEC server</span></div></div>
</div>

<div class="card"><div class="lbl">Frame-by-frame decisions</div>
 <table><thead><tr><th>Frame</th><th>Ran on</th><th>Latency</th><th>RTT</th><th>Camera saw</th><th>Why</th></tr></thead><tbody id="rows"></tbody></table>
 <div class="empty" id="empty">Waiting for frames&hellip;</div></div>

<script>
const $=id=>document.getElementById(id);
const fmt=(x,d=0)=>(x==null||isNaN(x))?'–':Number(x).toFixed(d);
const esc=s=>String(s==null?'':s).replace(/[&<>"]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;'}[c]));
const C={mec:'#22c55e',loc:'#f59e0b',rtt:'#38bdf8',grid:'#25304f',txt:'#8d99b8'};
function setup(cv){const d=window.devicePixelRatio||1,w=cv.clientWidth,h=cv.clientHeight;
 if(cv.width!==Math.round(w*d)||cv.height!==Math.round(h*d)){cv.width=Math.round(w*d);cv.height=Math.round(h*d);}
 const g=cv.getContext('2d');g.setTransform(d,0,0,d,0,0);g.clearRect(0,0,w,h);return [g,w,h];}
function frame(g,w,h,mx,L,T,B,R){g.strokeStyle=C.grid;g.fillStyle=C.txt;g.font='12px system-ui';g.lineWidth=1;
 for(let i=0;i<=4;i++){const y=T+(h-T-B)*i/4;g.beginPath();g.moveTo(L,y);g.lineTo(w-R,y);g.stroke();g.fillText(Math.round(mx*(1-i/4)),4,y+4);}}
function chart1(r){const cv=$('c1'),[g,w,h]=setup(cv),L=42,T=8,B=8,R=8;if(!r.length)return;
 const vals=[];r.forEach(x=>{vals.push(x.latency_ms);if(x.ema_mec)vals.push(x.ema_mec);if(x.ema_local)vals.push(x.ema_local);});
 const mx=Math.max(60,...vals)*1.1,X=i=>L+(w-L-R)*(r.length<2?.5:i/(r.length-1)),Y=v=>T+(h-T-B)*(1-v/mx);
 frame(g,w,h,mx,L,T,B,R);
 for(const [k,c] of [['ema_mec',C.mec],['ema_local',C.loc]]){g.strokeStyle=c;g.lineWidth=2;g.setLineDash([6,5]);g.globalAlpha=.9;g.beginPath();let s=false;
  r.forEach((x,i)=>{if(x[k]==null){return;}const px=X(i),py=Y(x[k]);if(!s){g.moveTo(px,py);s=true;}else g.lineTo(px,py);});g.stroke();}
 g.setLineDash([]);g.globalAlpha=1;
 r.forEach((x,i)=>{g.fillStyle=x.path==='MEC'?C.mec:C.loc;g.beginPath();g.arc(X(i),Y(x.latency_ms),4,0,7);g.fill();});}
function chart2(r){const cv=$('c2'),[g,w,h]=setup(cv),L=42,T=8,B=8,R=8;if(!r.length)return;
 const vals=r.map(x=>x.rtt_ms).filter(v=>v!=null);const mx=Math.max(40,...vals)*1.1;
 const X=i=>L+(w-L-R)*(r.length<2?.5:i/(r.length-1)),Y=v=>T+(h-T-B)*(1-v/mx);frame(g,w,h,mx,L,T,B,R);
 g.strokeStyle=C.rtt;g.lineWidth=2.5;g.lineJoin='round';g.beginPath();let s=false;
 r.forEach((x,i)=>{if(x.rtt_ms==null){s=false;return;}const px=X(i),py=Y(x.rtt_ms);if(!s){g.moveTo(px,py);s=true;}else g.lineTo(px,py);});g.stroke();
 r.forEach((x,i)=>{if(x.rtt_ms==null){g.fillStyle='#ef4444';g.beginPath();g.arc(X(i),h-B-4,4,0,7);g.fill();}});}
function mean(a){return a.length?a.reduce((p,c)=>p+c,0)/a.length:null;}
async function tick(){let s;try{s=await (await fetch('/api/state',{cache:'no-store'})).json();}catch(e){$('livetxt').textContent='Disconnected';$('livepill').classList.remove('live');return;}
 const r=s.records;if(!r.length){return;}const l=r[r.length-1],last30=r.slice(-30);
 const fresh=(Date.now()/1000-l.ts)<6;$('livepill').className='pill'+(fresh?' live':'');$('livetxt').textContent=fresh?'Live':'Paused';
 const onMec=l.path==='MEC';$('hero').className='hero '+(onMec?'mec':'loc');
 $('where').textContent=onMec?'MEC SERVER':'LAPTOP (LOCAL)';$('why').textContent=l.reason||l.note||'';
 $('saw').innerHTML=l.label?'Camera saw: <b>'+esc(l.label)+'</b>'+(l.conf!=null?' ('+Math.round(l.conf*100)+'% confidence)':''):'';
 const em=l.ema_mec,el=l.ema_local,mx=Math.max(em||0,el||0,1);
 $('bm').style.width=(em?em/mx*100:0)+'%';$('bl').style.width=(el?el/mx*100:0)+'%';$('vm').textContent=em?fmt(em)+' ms':'–';$('vl').textContent=el?fmt(el)+' ms':'–';
 if(em&&el){const d=Math.abs(em-el),f=em<el?'The server is':'The laptop is';$('hint').textContent=f+' about '+fmt(d)+' ms faster per frame ('+fmt(d/Math.max(em,el)*100)+'%). The shorter bar wins.';}
 let ns='GOOD',cls='#22c55e';if(l.rtt_ms==null){ns='NO LINK';cls='#ef4444';}else if(em&&el&&em>el){ns='CONGESTED';cls='#f59e0b';}
 $('nettxt').textContent='Network: '+ns;$('net').querySelector('.dot').style.background=cls;
 $('k1').textContent=fmt(l.latency_ms);$('k2').textContent=fmt(mean(last30.map(x=>x.latency_ms)));$('k3').textContent=fmt(l.rtt_ms);
 const cpu=[...r].reverse().find(x=>x.cpu!=null);$('k4').textContent=cpu?fmt(cpu.cpu):'–';
 $('k5').textContent=fmt(last30.filter(x=>x.path==='MEC').length/last30.length*100);$('k6').textContent=s.total;
 $('k6s').textContent='server '+s.mec.n+' · laptop '+s.local.n;
 chart1(r.slice(-80));chart2(r.slice(-80));
 const rows=r.slice(-10).reverse().map(x=>'<tr><td class="num">#'+x.frame+'</td><td><span class="tag '+x.path+'">'+(x.path==='MEC'?'SERVER':'LAPTOP')+'</span></td><td class="num">'+fmt(x.latency_ms)+' ms</td><td class="num">'+(x.rtt_ms==null?'–':fmt(x.rtt_ms)+' ms')+'</td><td>'+esc(x.label)+'</td><td>'+esc(x.reason||x.note)+'</td></tr>').join('');
 $('rows').innerHTML=rows;$('empty').style.display='none';}
setInterval(tick,800);tick();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE
