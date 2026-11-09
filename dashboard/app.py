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


PAGE = """<!doctype html><html><head><meta charset="utf-8"><title>5G Offloading Dashboard</title>
<style>
body{font-family:system-ui,sans-serif;background:#0f172a;color:#e2e8f0;margin:0;padding:16px}
h1{font-size:20px;margin:0 0 12px}
.row{display:flex;gap:12px;flex-wrap:wrap;margin-bottom:12px}
.card{background:#1e293b;border-radius:10px;padding:12px;flex:1;min-width:220px}
.big{font-size:44px;font-weight:700}.mec{color:#34d399}.local{color:#fb923c}
.small{color:#94a3b8;font-size:13px}canvas{width:100%;height:220px;background:#0b1220;border-radius:6px}
table{width:100%;border-collapse:collapse}td,th{padding:4px 6px;text-align:right;font-size:14px}th:first-child,td:first-child{text-align:left}
button{background:#334155;color:#e2e8f0;border:0;border-radius:6px;padding:6px 10px;cursor:pointer}
</style></head><body>
<h1>5G Adaptive Computation Offloading <button onclick="fetch('/reset',{method:'POST'})">reset</button></h1>
<div class="row">
 <div class="card"><div class="small">Current decision</div><div id="dec" class="big">-</div><div id="why" class="small"></div></div>
 <div class="card"><div class="small">Network (laptop to MEC)</div>
  <div>RTT: <b id="rtt">-</b> ms</div><div>MEC CPU: <b id="cpu">-</b> %</div><div>Frame upload: <b id="bytes">-</b> KB</div>
  <div>Last label: <b id="label">-</b></div></div>
 <div class="card"><div class="small">Latency by path</div>
  <table><tr><th></th><th>frames</th><th>mean ms</th><th>p95 ms</th></tr>
  <tr class="mec"><td>MEC</td><td id="mn">-</td><td id="mm">-</td><td id="mp">-</td></tr>
  <tr class="local"><td>LOCAL</td><td id="ln">-</td><td id="lm">-</td><td id="lp">-</td></tr></table></div>
</div>
<div class="row"><div class="card"><div class="small">Per-frame latency (ms): green = MEC, orange = local</div><canvas id="c1" width="900" height="220"></canvas></div>
<div class="card"><div class="small">RTT to MEC (ms)</div><canvas id="c2" width="900" height="220"></canvas></div></div>
<script>
function draw(cv, pts, colors){const g=cv.getContext('2d');const W=cv.width,H=cv.height;g.clearRect(0,0,W,H);
 const v=pts.filter(x=>x!=null);if(!v.length)return;const mx=Math.max(10,...v)*1.1;
 g.strokeStyle='#334155';g.fillStyle='#64748b';g.font='12px sans-serif';
 for(let i=0;i<=4;i++){const y=H-18-(H-28)*i/4;g.beginPath();g.moveTo(40,y);g.lineTo(W,y);g.stroke();g.fillText((mx*i/4).toFixed(0),2,y+4);}
 const n=pts.length,dx=(W-50)/Math.max(1,n-1);let prev=null;
 pts.forEach((p,i)=>{if(p==null){prev=null;return;}const x=44+i*dx,y=H-18-(H-28)*p/mx;
  if(prev){g.strokeStyle='#475569';g.beginPath();g.moveTo(prev[0],prev[1]);g.lineTo(x,y);g.stroke();}
  g.fillStyle=colors[i];g.beginPath();g.arc(x,y,3,0,7);g.fill();prev=[x,y];});}
const f=x=>x==null?'-':x.toFixed(0);
async function tick(){try{const s=await (await fetch('/api/state')).json();const r=s.records;if(!r.length)return;
 const l=r[r.length-1];const d=document.getElementById('dec');d.textContent=l.path;d.className='big '+(l.path=='MEC'?'mec':'local');
 document.getElementById('why').textContent=l.note||'';
 document.getElementById('rtt').textContent=f(l.rtt_ms);document.getElementById('cpu').textContent=f(l.cpu);
 document.getElementById('bytes').textContent=l.bytes?(l.bytes/1024).toFixed(0):'-';document.getElementById('label').textContent=l.label;
 for(const [k,p] of [['m','mec'],['l','local']]){document.getElementById(k+'n').textContent=s[p].n;document.getElementById(k+'m').textContent=f(s[p].mean);document.getElementById(k+'p').textContent=f(s[p].p95);}
 draw(document.getElementById('c1'),r.map(x=>x.latency_ms),r.map(x=>x.path=='MEC'?'#34d399':'#fb923c'));
 draw(document.getElementById('c2'),r.map(x=>x.rtt_ms),r.map(x=>'#60a5fa'));}catch(e){}}
setInterval(tick,1000);tick();
</script></body></html>"""


@app.get("/", response_class=HTMLResponse)
def index():
    return PAGE
