"""Minimal demo UI: enter a goal, watch the trace stream live.

FastAPI + one static HTML page. The agent runs in a background thread and pushes
TraceEvents onto a queue; the /stream endpoint relays them to the browser as SSE.
Demo-grade only — single user, no auth, no deploy.
"""

from __future__ import annotations

import json
import queue
import threading
from dataclasses import asdict

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, StreamingResponse

from agent.loop import run_agent

app = FastAPI(title="Deep Research Agent")


@app.get("/")
def index() -> HTMLResponse:
    return HTMLResponse(INDEX_HTML)


@app.get("/stream")
def stream(goal: str) -> StreamingResponse:
    q: queue.Queue = queue.Queue()
    SENTINEL = object()

    def sink(ev):
        q.put(asdict(ev))

    def worker():
        try:
            run_agent(goal, sink=sink)
        except Exception as e:
            q.put({"kind": "error", "step": 0, "data": {"message": str(e)}})
        finally:
            q.put(SENTINEL)

    threading.Thread(target=worker, daemon=True).start()

    def gen():
        while True:
            ev = q.get()
            if ev is SENTINEL:
                yield "event: done\ndata: {}\n\n"
                break
            yield f"data: {json.dumps(ev, default=str)}\n\n"

    return StreamingResponse(gen(), media_type="text/event-stream")


INDEX_HTML = """<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8"/>
<meta name="viewport" content="width=device-width, initial-scale=1"/>
<title>Deep Research Agent</title>
<style>
  :root { --bg:#0f1115; --panel:#171a21; --line:#262b36; --txt:#e6e9ef; --dim:#8b93a3;
          --cyan:#5ec8e6; --green:#6fd08c; --yellow:#e6c25e; --mag:#c08be6; --red:#e6776f; }
  * { box-sizing: border-box; }
  body { margin:0; background:var(--bg); color:var(--txt);
         font:14px/1.5 ui-monospace, SFMono-Regular, Menlo, monospace; }
  header { padding:18px 22px; border-bottom:1px solid var(--line); }
  h1 { margin:0; font-size:16px; }
  .sub { color:var(--dim); font-size:12px; margin-top:4px; }
  form { display:flex; gap:8px; padding:16px 22px; }
  input { flex:1; padding:10px 12px; background:var(--panel); border:1px solid var(--line);
          border-radius:8px; color:var(--txt); font:inherit; }
  button { padding:10px 18px; background:var(--cyan); border:none; border-radius:8px;
           color:#0b0d10; font-weight:700; cursor:pointer; }
  button:disabled { opacity:.5; cursor:default; }
  #trace { padding:0 22px 40px; }
  .step { border-left:2px solid var(--line); margin:14px 0; padding:4px 0 4px 16px; }
  .plan-hd { color:var(--cyan); font-weight:700; }
  .eval { color:var(--dim); white-space:pre-wrap; margin:4px 0; }
  .act { color:var(--mag); margin-top:6px; }
  .subq { color:var(--dim); font-size:12px; margin-left:14px; }
  .obs { margin:4px 0 4px 0; white-space:pre-wrap; }
  .obs.ok { color:var(--green); } .obs.bad { color:var(--yellow); }
  .recovery { color:var(--yellow); font-weight:700; background:#241f12;
              padding:6px 10px; border-radius:6px; margin:6px 0; }
  .budget { color:var(--red); font-weight:700; }
  .err { color:var(--red); }
  .final { border:1px solid var(--green); border-radius:10px; padding:16px 18px;
           margin:20px 0; background:#10160f; }
  .final h2 { margin:0 0 10px; color:var(--green); font-size:14px; }
  .answer { white-space:pre-wrap; }
  .sources { margin-top:12px; color:var(--dim); font-size:12px; }
  .stats { margin-top:10px; color:var(--dim); font-size:12px; }
  .pill { display:inline-block; padding:1px 7px; border-radius:10px; font-size:11px;
          margin-left:6px; }
  .pill.ok { background:#163; } .pill.bad { background:#640; }
  a { color:var(--cyan); }
</style>
</head>
<body>
<header>
  <h1>🔎 Deep Research Agent <span class="sub">model-driven loop · plan → act → observe → re-route → synthesize</span></h1>
  <div class="sub">Sonnet decides every step. Watch it choose tools, hit dead ends, and re-route.</div>
</header>
<form id="f">
  <input id="goal" placeholder="e.g. Competitive brief on Notion: who competes and how do they price?" autocomplete="off"/>
  <button id="go" type="submit">Research</button>
</form>
<div id="trace"></div>

<script>
const traceEl = document.getElementById('trace');
const form = document.getElementById('f');
const goalEl = document.getElementById('goal');
const goBtn = document.getElementById('go');
let es = null, curStep = null;

function el(cls, html){ const d=document.createElement('div'); d.className=cls; d.innerHTML=html; return d; }
function esc(s){ return (s||'').replace(/[&<>]/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c])); }

function stepBox(n){
  if (curStep && curStep.dataset.n == n) return curStep;
  curStep = el('step',''); curStep.dataset.n = n; traceEl.appendChild(curStep); return curStep;
}

function handle(ev){
  const d = ev.data || {};
  if (ev.kind === 'goal'){
    traceEl.appendChild(el('eval', '🎯 <b>'+esc(d.goal)+'</b><br>apify '+(d.apify?'on':'off')));
  } else if (ev.kind === 'plan'){
    const box = stepBox(ev.step);
    box.appendChild(el('plan-hd','── Step '+ev.step+' · PLAN ──'));
    if (d.evaluation) box.appendChild(el('eval', esc(d.evaluation)));
  } else if (ev.kind === 'tool_call'){
    const box = stepBox(ev.step);
    const inp = Object.fromEntries(Object.entries(d.input||{}).filter(([k])=>k!=='subquestion'&&k!=='rationale'));
    box.appendChild(el('act','▶ ACT <b>'+esc(d.tool)+'</b> '+esc(JSON.stringify(inp))));
    if (d.subquestion) box.appendChild(el('subq','↳ '+esc(d.subquestion)));
  } else if (ev.kind === 'observation'){
    const box = stepBox(ev.step);
    const ok = d.quality === 'ok';
    box.appendChild(el('obs '+(ok?'ok':'bad'),'◀ OBSERVE <span class="pill '+(ok?'ok':'bad')+'">'+esc(d.quality)+'</span><br>'+esc(d.summary)));
  } else if (ev.kind === 'recovery'){
    stepBox(ev.step).appendChild(el('recovery','♻ RE-ROUTE: '+esc(d.reason)));
  } else if (ev.kind === 'budget'){
    stepBox(ev.step).appendChild(el('budget','⛔ BUDGET: '+esc(d.reason)));
  } else if (ev.kind === 'error'){
    traceEl.appendChild(el('err','⚠ '+esc(d.message)));
  } else if (ev.kind === 'finish'){
    const box = el('final','');
    box.appendChild(el('h2','✅ FINAL ANSWER'));
    box.appendChild(el('answer', linkify(esc(d.answer))));
    if (d.citations && d.citations.length){
      let s = '<b>Sources</b><br>';
      d.citations.forEach(c=>{ s += '['+c.id+'] '+esc(c.title||'')+' — <a href="'+esc(c.url)+'" target="_blank">'+esc(c.url)+'</a><br>'; });
      box.appendChild(el('sources', s));
    }
    box.appendChild(el('stats','confidence: '+esc(d.confidence||'')+' · gaps: '+esc(d.open_gaps||'—')
      +'<br>steps '+ev.step+' · tokens '+(d.tokens||'?')+' · tool calls '+(d.tool_calls||'?')
      +' · apify '+(d.apify_runs||0)+' · '+(d.elapsed||'?')+'s · stop: '+esc(d.stopped_reason||'')));
    traceEl.appendChild(box);
  }
  window.scrollTo(0, document.body.scrollHeight);
}
function linkify(s){ return s.replace(/(https?:\\/\\/[^\\s)]+)/g,'<a href="$1" target="_blank">$1</a>'); }

form.addEventListener('submit', e=>{
  e.preventDefault();
  const goal = goalEl.value.trim();
  if (!goal) return;
  if (es) es.close();
  traceEl.innerHTML = ''; curStep = null;
  goBtn.disabled = true; goBtn.textContent = 'Researching…';
  es = new EventSource('/stream?goal='+encodeURIComponent(goal));
  es.onmessage = e => { try { handle(JSON.parse(e.data)); } catch(_){} };
  es.addEventListener('done', ()=>{ es.close(); goBtn.disabled=false; goBtn.textContent='Research'; });
  es.onerror = ()=>{ es.close(); goBtn.disabled=false; goBtn.textContent='Research'; };
});
</script>
</body>
</html>
"""
