#!/usr/bin/env python3
"""
mindmap-canvas (web engine) — drop-in замена Tk-версии.

Одиночный файл: stdlib http-сервер + Chrome в режиме --app (отдельное окно без
браузера). Закрытие окна завершает процесс → будит агента (та же механика, что
у Tk). CLI и формат экспорта идентичны Tk-версии:

  --nodes "A::B::C"  --title "тема"  --load file.json
  --export-file PATH (дефолт /tmp/mindmap-export.txt)  --no-signal

Что даёт веб: кириллица нативно, зум/пан колесом, inline-переименование,
undo/redo из коробки, подписи связей на плашках.
Fallback без Chrome: ~/bin/mindmap-canvas-tk.py
"""
import json, os, re, shutil, socket, subprocess, sys, tempfile, threading, time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

HOME = os.path.expanduser("~")
SAVE_PATH = f"{HOME}/.mindmap_canvas.json"
EXPORT_PATH = "/tmp/mindmap-export.txt"
if "--export-file" in sys.argv:
    _i = sys.argv.index("--export-file")
    if _i + 1 < len(sys.argv):
        EXPORT_PATH = sys.argv[_i + 1]
NO_SIGNAL = "--no-signal" in sys.argv

W, H = 1160, 700  # логический размер сцены (для % в экспорте)


def _arg(name, default=""):
    if name in sys.argv:
        i = sys.argv.index(name)
        if i + 1 < len(sys.argv):
            return sys.argv[i + 1]
    return default


def initial_state():
    import math, random
    state = {"title": _arg("--title", ""), "w": W, "h": H,
             "nodes": [], "conns": [], "groups": []}
    load = _arg("--load")
    if load and os.path.exists(load):
        data = json.load(open(load, encoding="utf-8"))
        state["nodes"] = [{"name": n["name"], "x": n.get("x", 100), "y": n.get("y", 100),
                           "d": n.get("d", ""), "qn": n.get("qn", False)}
                          for n in data.get("nodes", [])]
        state["conns"] = [{"f": c["f"], "t": c["t"], "y": c.get("y", "arrow"),
                           "l": c.get("l", ""), "e": c.get("e", False)}
                          for c in data.get("conns", [])
                          if c.get("f") is not None and c.get("t") is not None]
        state["groups"] = [{"name": g.get("name") or "Group", "nodes": g.get("nodes", [])}
                           for g in data.get("groups", []) if g.get("nodes")]
    nodes_arg = _arg("--nodes")
    if nodes_arg:
        for k, n in enumerate([x.strip() for x in re.split(r"::|\||\n", nodes_arg) if x.strip()]):
            desc = ""
            if " — " in n:  # «Имя — бытовая фраза» → фраза уходит в hover-подсказку
                n, desc = (s.strip() for s in n.split(" — ", 1))
            a = k * 2.39996 + random.uniform(-.08, .08)
            r = min(W, H) * .30 + random.uniform(-20, 20)
            state["nodes"].append({"name": n, "x": W // 2 + r * __import__("math").cos(a),
                                   "y": H // 2 + r * __import__("math").sin(a), "d": desc})
    return state


STATE = initial_state()
STATE_LOCK = threading.Lock()


def zone(px, py, w, h):
    col = "left" if px < w * 0.34 else ("right" if px > w * 0.66 else "mid")
    row = "top" if py < h * 0.34 else ("bottom" if py > h * 0.66 else "mid")
    return f"{row}-{col}"


def write_export():
    with STATE_LOCK:
        s = json.loads(json.dumps(STATE))
    nodes, conns, groups = s["nodes"], s["conns"], s["groups"]
    if not nodes:
        return
    w, h = s.get("w") or W, s.get("h") or H
    letter = lambda i: chr(65 + i) if i < 26 else f"N{i}"
    lines = ["[MINDMAP EXPORT]", "=== NODES ==="]
    for i, n in enumerate(nodes):
        lines.append(f"  {letter(i)}: {n['name']}")
    lines += ["", "=== POSITIONS (для сохранения твоего расположения на ASCII-схеме) ==="]
    for i, n in enumerate(nodes):
        lines.append(f"  {letter(i)}: x={round(100 * n['x'] / w)}% y={round(100 * n['y'] / h)}% "
                     f"zone={zone(n['x'], n['y'], w, h)}")
    def end(v):
        if isinstance(v, str) and v.startswith("g"):
            gi = int(v[1:])
            return f"[{groups[gi]['name']}]" if gi < len(groups) else "?"
        return letter(v) if isinstance(v, int) and v < len(nodes) else "?"
    real = [c for c in conns if c.get("y") not in ("fix", "q")]
    if real:
        lines += ["", "=== CONNECTIONS ==="]
        for c in real:
            arrow = ("=>" if c.get("e") else "->") if c["y"] == "arrow" else ("==" if c.get("e") else "--")
            tail = f" : {c['l']}" if c.get("l") else ""
            lines.append(f"  {end(c['f'])} {arrow} {end(c['t'])}{tail}")
    if groups:
        lines += ["", "=== GROUPS ==="]
        for g in groups:
            ms = [letter(i) for i in g["nodes"] if i < len(nodes)]
            lines.append(f"  [{g['name']}]: {', '.join(ms)}")
    with open(EXPORT_PATH, "w", encoding="utf-8") as f:
        f.write("\n".join(lines))


HTML = r"""<!doctype html>
<html><head><meta charset="utf-8"><title>Mindmap</title><style>
:root{--bg:#1e1e24;--fg:#e2e8f0;--bar:#141419;--fill:#2a2b36;--outl:#3f4257;
 --sel:#f9e2af;--arrow:#f38ba8;--line:#a6e3a1;--fix:#f9e2af;--grp:#57b8c0;--dim:#6c7086}
*{box-sizing:border-box;margin:0}
body{background:var(--bg);color:var(--fg);font:14px Ubuntu,sans-serif;overflow:hidden;
 user-select:none;height:100vh;display:flex;flex-direction:column}
#bar{background:var(--bar);padding:5px 8px;display:flex;gap:6px;align-items:center;flex:0 0 auto}
#bar button,#bar label{background:var(--fill);color:var(--fg);border:0;border-radius:4px;
 padding:4px 10px;cursor:pointer;font:12px Ubuntu}
#bar label{display:flex;align-items:center;gap:4px}
#bar label.on{outline:2px solid var(--sel)}
#bar input[type=radio]{display:none}
#mArrow{color:var(--arrow)}#mLine{color:var(--line)}#mGroup{color:var(--grp)}
#ttl{margin-left:auto;color:var(--dim);font-size:12px}
#wrap{flex:1;position:relative;overflow:hidden;cursor:default}
#scene{position:absolute;left:0;top:0;transform-origin:0 0}
svg{position:absolute;left:0;top:0;overflow:visible}
.node{position:absolute;background:var(--fill);border:2px solid var(--outl);border-radius:8px;
 padding:8px 14px;max-width:190px;min-width:70px;text-align:center;font:bold 13px Ubuntu;
 cursor:grab;transform:translate(-50%,-50%);white-space:pre-wrap;word-wrap:break-word}
.node.sel{border-color:var(--sel);border-width:3px}
.node.qn{border-style:dashed;border-color:#fab387;color:#fab387;font-weight:normal;
 min-width:200px;max-width:280px;text-align:left;font-size:12px}
.node[contenteditable=true]{cursor:text;user-select:text;outline:1px dashed var(--sel)}
#status{background:var(--bar);color:var(--dim);font-size:12px;padding:4px 10px;flex:0 0 auto}
#rubber{position:absolute;border:1px dashed var(--grp);display:none;pointer-events:none}
#tip{position:fixed;background:var(--bar);border:1px solid var(--outl);color:var(--fg);
 padding:6px 10px;border-radius:6px;max-width:280px;font-size:12px;line-height:1.35;
 display:none;pointer-events:none;z-index:9}
.modal{position:fixed;inset:0;background:#0008;display:flex;align-items:center;justify-content:center}
.modal>div{background:var(--bar);padding:16px;border-radius:8px;display:flex;flex-direction:column;gap:10px}
.modal textarea{background:var(--fill);color:var(--fg);border:0;padding:8px;font:13px Ubuntu;width:420px;height:220px}
</style></head><body>
<div id="bar">
 <button onclick="addNode()">+ Node</button><button onclick="importDlg()">Import</button>
 <label id="mArrow" class="on"><input type="radio" name="m" value="arrow" checked>C →</label>
 <label id="mLine"><input type="radio" name="m" value="line">V —</label>
 <label id="mGroup"><input type="radio" name="m" value="group">B □</label>
 <button onclick="undo()">Undo</button><button onclick="redo()">Redo</button>
 <button onclick="push(true)">Export</button><button onclick="saveF()">Save</button>
 <button onclick="loadF()">Load</button><button onclick="resetView()">⌂</button>
 <span id="ttl"></span>
</div>
<div id="wrap"><div id="scene"><svg id="svg" width="6000" height="4000" viewBox="-2000 -2000 6000 4000" style="left:-2000px;top:-2000px"></svg><div id="layer"></div></div><div id="rubber"></div></div>
<div id="tip"></div>
<div id="status">C=arrow V=line B=group | ЛКМ=тащить ПКМ=связать 2xЛКМ=имя/метка СКМ по ноду=«не понял» | Ctrl+Z/Y колесо=зум</div>
<script>
const S = __STATE__;
const wrap=document.getElementById('wrap'),scene=document.getElementById('scene'),
      svg=document.getElementById('svg'),layer=document.getElementById('layer'),
      rub=document.getElementById('rubber'),status=document.getElementById('status');
document.getElementById('ttl').textContent=S.title||'';
if(S.title)document.title='Mindmap — '+S.title;
let view={x:0,y:0,k:1}, sel=new Set(), selEdge=-1, mode='arrow';
let undoS=[],redoS=[];
const msg=t=>{status.textContent=t};
const snap=()=>JSON.stringify({nodes:S.nodes,conns:S.conns,groups:S.groups});
const pushUndo=s=>{undoS.push(s||snap());if(undoS.length>100)undoS.shift();redoS=[]};
function restore(s){const d=JSON.parse(s);S.nodes=d.nodes;S.conns=d.conns;S.groups=d.groups;
 sel.clear();selEdge=-1;render();push()}
function undo(){if(!undoS.length)return msg('Nothing to undo');redoS.push(snap());restore(undoS.pop());msg('Undone')}
function redo(){if(!redoS.length)return msg('Nothing to redo');undoS.push(snap());restore(redoS.pop());msg('Redone')}
document.querySelectorAll('#bar input[type=radio]').forEach(r=>r.onchange=()=>{
 mode=r.value;document.querySelectorAll('#bar label').forEach(l=>l.classList.remove('on'));
 r.parentElement.classList.add('on')});
function setMode(m){mode=m;document.querySelectorAll('#bar input[type=radio]').forEach(r=>{
 r.checked=r.value===m;r.parentElement.classList.toggle('on',r.value===m)})}

let pushT=null;
function push(now){clearTimeout(pushT);const go=()=>fetch('/state',{method:'POST',
 body:JSON.stringify(S)}).then(()=>{if(now)msg('Exported!')}).catch(()=>{});
 now?go():pushT=setTimeout(go,250)}
addEventListener('beforeunload',()=>navigator.sendBeacon('/state',JSON.stringify(S)));
function saveF(){fetch('/save',{method:'POST',body:JSON.stringify(S)}).then(()=>msg('Saved'))}
function loadF(){fetch('/loadfile').then(r=>r.json()).then(d=>{if(!d.nodes)return msg('Нет сохранёнки');
 pushUndo();S.nodes=d.nodes;S.conns=d.conns||[];S.groups=d.groups||[];render();push();msg('Loaded')})}

const gC=i=>{const g=S.groups[i];if(!g||!g.nodes.length)return{x:0,y:0};let x1=1e9,y1=1e9,x2=-1e9,y2=-1e9;
 g.nodes.forEach(j=>{const n=S.nodes[j];if(!n)return;const e=nodeEl(j),hw=e?e.offsetWidth/2:60,hh=e?e.offsetHeight/2:20;
 x1=Math.min(x1,n.x-hw);y1=Math.min(y1,n.y-hh);x2=Math.max(x2,n.x+hw);y2=Math.max(y2,n.y+hh)});
 return{x:(x1+x2)/2,y:(y1+y2)/2,x1:x1-30,y1:y1-30,x2:x2+30,y2:y2+30}};
const endC=v=>typeof v==='string'?gC(+v.slice(1)):(S.nodes[v]||{x:0,y:0});
const nodeEl=i=>layer.querySelector('.node[data-i="'+i+'"]');

function render(){
 layer.innerHTML='';svg.innerHTML=defs();
 S.nodes.forEach((n,i)=>{const d=document.createElement('div');d.className='node';d.dataset.i=i;
  d.textContent=n.name;d.style.left=n.x+'px';d.style.top=n.y+'px';
  if(n.qn)d.classList.add('qn');
  if(sel.has(i))d.classList.add('sel');layer.appendChild(d)});
 drawShapes()}
function defs(){const m=(id,c)=>'<marker id="'+id+'" viewBox="0 0 10 10" refX="9" refY="5" '+
 'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'+
 '<path d="M0,0L10,5L0,10z" fill="'+c+'"/></marker>';
 return '<defs>'+m('ma','var(--arrow)')+m('mf','var(--fix)')+'</defs>'}
function drawShapes(){
 [...svg.querySelectorAll('.sh')].forEach(e=>e.remove());
 const NS='http://www.w3.org/2000/svg';
 const el=(t,at)=>{const e=document.createElementNS(NS,t);for(const k in at)e.setAttribute(k,at[k]);
  e.classList.add('sh');return e};
 S.groups.forEach((g,gi)=>{const b=gC(gi);if(b.x1===undefined)return;
  svg.appendChild(el('rect',{x:b.x1,y:b.y1,width:b.x2-b.x1,height:b.y2-b.y1,fill:'none',
   stroke:'var(--grp)','stroke-width':2,'stroke-dasharray':'8 4','data-g':gi}));
  const t=el('text',{x:b.x1+8,y:b.y1-8,fill:'var(--grp)','font-style':'italic','font-size':13,'data-g':gi});
  t.textContent=g.name;svg.appendChild(t)});
 S.conns.forEach((c,ci)=>{
  const a=endC(c.f),b=endC(c.t);if(!a||!b)return;
  const col=c.y==='fix'?'var(--fix)':c.y==='q'?'#fab387':c.y==='arrow'?'var(--arrow)':'var(--line)';
  const dx=b.x-a.x,dy=b.y-a.y,L=Math.hypot(dx,dy)||1,ux=dx/L,uy=dy/L;
  const sh=(v,s)=>{if(typeof v==='string')return 12;const e=nodeEl(v);if(!e)return 12;
   const hw=e.offsetWidth/2+4,hh=e.offsetHeight/2+4;
   return Math.min(Math.abs(ux)>1e-6?hw/Math.abs(ux):1e9,Math.abs(uy)>1e-6?hh/Math.abs(uy):1e9)};
  const x1=a.x+ux*sh(c.f),y1=a.y+uy*sh(c.f),x2=b.x-ux*sh(c.t),y2=b.y-uy*sh(c.t);
  const at={x1,y1,x2,y2,stroke:col,'stroke-width':(c.e?5:3),'data-c':ci};
  if(c.y==='fix')at['stroke-dasharray']='7 4';
  if(c.y==='q'){at['stroke-dasharray']='3 5';at['stroke-width']=2}
  if(c.y!=='line'&&c.y!=='q')at['marker-end']=c.y==='fix'?'url(#mf)':'url(#ma)';
  if(ci===selEdge)at['stroke-width']=(c.e?7:5);
  at['class']='sh vis';
  svg.appendChild(el('line',at));
  svg.appendChild(el('line',{x1,y1,x2,y2,stroke:'rgba(0,0,0,0)','stroke-width':14,
   'pointer-events':'stroke','data-c':ci}));
  if(c.l){const mx=(x1+x2)/2,my=(y1+y2)/2-12;
   const t=el('text',{x:mx,y:my,fill:col,'font-size':13,'font-weight':'bold','text-anchor':'middle','data-c':ci});
   t.textContent=c.l;svg.appendChild(t);
   const bb=t.getBBox();
   const r=el('rect',{x:bb.x-5,y:bb.y-2,width:bb.width+10,height:bb.height+4,
    fill:'var(--bg)',stroke:col,'stroke-width':1,'data-c':ci});
   svg.insertBefore(r,t)}})}
/* выделение — на месте, БЕЗ render(): пересборка DOM между двумя кликами
   ломает нативный dblclick (Chrome не шлёт его по замещённому элементу) */
function updateSel(){
 layer.querySelectorAll('.node').forEach(e=>e.classList.toggle('sel',sel.has(+e.dataset.i)));
 svg.querySelectorAll('line.vis').forEach(e=>{const ci=+e.dataset.c,c=S.conns[ci];if(!c)return;
  e.setAttribute('stroke-width',ci===selEdge?(c.e?7:5):(c.e?5:3))})}
function applyView(){scene.style.transform='translate('+view.x+'px,'+view.y+'px) scale('+view.k+')'}
function resetView(){view={x:0,y:0,k:1};applyView()}
const toScene=(cx,cy)=>({x:(cx-view.x)/view.k,y:(cy-view.y)/view.k});

function addNode(name,x,y){pushUndo();
 S.nodes.push({name:name||'узел',x:x||S.w/2,y:y||S.h/2});render();push();
 if(!name)editNode(S.nodes.length-1,true)}
function editNode(i,isNew){const e=nodeEl(i);if(!e)return;const old=S.nodes[i].name;
 e.contentEditable=true;e.focus();
 const rng=document.createRange();rng.selectNodeContents(e);
 const s=getSelection();s.removeAllRanges();s.addRange(rng);
 const done=ok=>{e.contentEditable=false;const v=e.textContent.trim();
  if(ok&&v&&v!==old){if(!isNew)pushUndo();S.nodes[i].name=v}
  else if(!ok&&isNew){S.nodes.splice(i,1)}
  else S.nodes[i].name=v||old;render();push()};
 e.onblur=()=>done(true);
 e.onkeydown=ev=>{ev.stopPropagation();
  if(ev.key==='Enter'){ev.preventDefault();e.onblur=null;done(true)}
  if(ev.key==='Escape'){e.onblur=null;done(false)}}}
function importDlg(){const m=document.createElement('div');m.className='modal';
 m.innerHTML='<div><b>One per line:</b><textarea></textarea><button>Import</button></div>';
 document.body.appendChild(m);const ta=m.querySelector('textarea');ta.focus();
 m.querySelector('button').onclick=()=>{const t=ta.value.trim();
  if(t){pushUndo();t.split('\n').forEach((ln,k)=>{ln=ln.trim();if(!ln)return;
   if(ln.includes(' — '))ln=ln.split(' — ')[0];
   const a=(S.nodes.length)*2.39996,r=Math.min(S.w,S.h)*.3;
   S.nodes.push({name:ln,x:S.w/2+r*Math.cos(a),y:S.h/2+r*Math.sin(a)})});
  render();push()}m.remove()};
 m.onclick=ev=>{if(ev.target===m)m.remove()}}

/* hover-подсказка: бытовая фраза объекта (нод несёт её с собой, ноль ожидания) */
const tip=document.getElementById('tip');
wrap.addEventListener('mousemove',ev=>{
 const nd=ev.target.closest&&ev.target.closest('.node');
 const d=nd&&!nd.isContentEditable?S.nodes[+nd.dataset.i]?.d:'';
 if(d){tip.textContent=d;tip.style.display='block';
  tip.style.left=Math.min(ev.clientX+14,innerWidth-300)+'px';tip.style.top=(ev.clientY+16)+'px'}
 else tip.style.display='none'});

let drag=null,rubberOn=null,panOn=null,dragSnap=null,moved=false;
wrap.addEventListener('mousedown',ev=>{
 const nd=ev.target.closest('.node');
 if(ev.button===1&&nd){ev.preventDefault();  // СКМ по ноду = «не понял», пометить ?
  const n=S.nodes[+nd.dataset.i];
  if(!/\?$/.test(n.name)){pushUndo();n.name+=' ?';render();push();msg('Помечено «?» - переформулирую после закрытия')}
  return}
 if(ev.button===1||(ev.button===0&&ev.altKey)){panOn={x:ev.clientX,y:ev.clientY};ev.preventDefault();return}
 if(ev.button!==0)return;
 selEdge=-1;
 if(nd){const i=+nd.dataset.i;
  if(!sel.has(i)){sel.clear();sel.add(i)}
  drag={type:'n',last:toScene(ev.clientX,ev.clientY)};dragSnap=snap();moved=false;updateSel();return}
 const gid=ev.target.dataset&&ev.target.dataset.g;
 if(gid!==undefined&&gid!==''&&ev.target.classList.contains('sh')){
  sel.clear();sel.add('g'+gid);drag={type:'g',gi:+gid,last:toScene(ev.clientX,ev.clientY)};
  dragSnap=snap();moved=false;updateSel();return}
 const cid=ev.target.dataset&&ev.target.dataset.c;
 if(cid!==undefined&&cid!==''){sel.clear();selEdge=+cid;updateSel();return}
 sel.clear();updateSel();
 rubberOn={x:ev.clientX,y:ev.clientY};
 Object.assign(rub.style,{display:'block',left:ev.clientX+'px',top:ev.clientY+'px',width:0,height:0})});
addEventListener('mousemove',ev=>{
 if(panOn){view.x+=ev.clientX-panOn.x;view.y+=ev.clientY-panOn.y;panOn={x:ev.clientX,y:ev.clientY};applyView();return}
 if(rubberOn){const x=Math.min(ev.clientX,rubberOn.x),y=Math.min(ev.clientY,rubberOn.y);
  Object.assign(rub.style,{left:x+'px',top:y+'px',width:Math.abs(ev.clientX-rubberOn.x)+'px',
   height:Math.abs(ev.clientY-rubberOn.y)+'px'});return}
 if(!drag)return;
 const p=toScene(ev.clientX,ev.clientY),dx=p.x-drag.last.x,dy=p.y-drag.last.y;
 if(dx||dy)moved=true;
 const move=i=>{const n=S.nodes[i];if(!n)return;n.x+=dx;n.y+=dy;
  const e=nodeEl(i);if(e){e.style.left=n.x+'px';e.style.top=n.y+'px'}};
 if(drag.type==='g')S.groups[drag.gi].nodes.forEach(move);
 else sel.forEach(v=>{if(typeof v==='number')move(v);
  else S.groups[+v.slice(1)].nodes.forEach(move)});
 drag.last=p;drawShapes()});
addEventListener('mouseup',ev=>{
 panOn=null;
 if(rubberOn){rub.style.display='none';
  const a=toScene(Math.min(ev.clientX,rubberOn.x),Math.min(ev.clientY,rubberOn.y)),
        b=toScene(Math.max(ev.clientX,rubberOn.x),Math.max(ev.clientY,rubberOn.y));
  rubberOn=null;
  const inside=S.nodes.map((n,i)=>n.x>=a.x&&n.x<=b.x&&n.y>=a.y&&n.y<=b.y?i:-1).filter(i=>i>=0);
  if(inside.length){sel.clear();inside.forEach(i=>sel.add(i));msg('Selected '+inside.length);
   if(mode==='group'){const nm=prompt('Group name (or Cancel):');
    pushUndo();S.groups.push({name:(nm||'Group').trim()||'Group',nodes:inside});push()}
   render()}
  return}
 if(drag){if(moved&&dragSnap){undoS.push(dragSnap);if(undoS.length>100)undoS.shift();redoS=[];push()}
  drag=null;dragSnap=null;moved=false}});
wrap.addEventListener('contextmenu',ev=>{
 ev.preventDefault();
 const nd=ev.target.closest('.node');
 const gid=!nd&&ev.target.classList&&ev.target.classList.contains('sh')?ev.target.dataset.g:undefined;
 let tgt=null;
 if(nd)tgt=+nd.dataset.i;else if(gid!==undefined&&gid!=='')tgt='g'+gid;
 if(tgt===null||!sel.size)return;
 const src=[...sel][0];if(src===tgt)return;
 pushUndo();S.conns.push({f:src,t:tgt,y:mode==='arrow'?'arrow':'line',l:'',e:false});
 sel.clear();render();push();msg('Connected')});
wrap.addEventListener('dblclick',ev=>{
 const nd=ev.target.closest('.node');
 if(nd){editNode(+nd.dataset.i);return}
 const cid=ev.target.dataset&&ev.target.dataset.c;
 if(cid!==undefined&&cid!==''){const c=S.conns[+cid];
  const init=(c.l||'')+(c.e?'!':'');
  const lb=prompt("Метка связи ('!' в конце = жирная, пусто = убрать):",init);
  if(lb===null)return;pushUndo();
  c.e=lb.trim().endsWith('!');c.l=lb.trim().replace(/!+$/,'').trim();render();push();return}
 const p=toScene(ev.clientX,ev.clientY);addNode(null,p.x,p.y)});
wrap.addEventListener('wheel',ev=>{ev.preventDefault();
 const k=Math.min(2.5,Math.max(.35,view.k*(ev.deltaY<0?1.12:.9)));
 view.x=ev.clientX-(ev.clientX-view.x)*k/view.k;
 view.y=ev.clientY-(ev.clientY-view.y)*k/view.k;view.k=k;applyView()},{passive:false});
addEventListener('keydown',ev=>{
 if(ev.target.isContentEditable||/TEXTAREA|INPUT/.test(ev.target.tagName))return;
 const k=ev.key.toLowerCase();
 if(ev.ctrlKey&&k==='z'&&!ev.shiftKey){ev.preventDefault();undo();return}
 if(ev.ctrlKey&&(k==='y'||(k==='z'&&ev.shiftKey))){ev.preventDefault();redo();return}
 if(ev.ctrlKey&&k==='e'){ev.preventDefault();push(true);return}
 if(ev.ctrlKey&&k==='s'){ev.preventDefault();saveF();return}
 if(k==='c')setMode('arrow');if(k==='v')setMode('line');if(k==='b')setMode('group');
 if(ev.key==='Delete'){
  if(selEdge>=0){pushUndo();S.conns.splice(selEdge,1);selEdge=-1;render();push();return}
  if(!sel.size)return;pushUndo();
  const gs=[...sel].filter(v=>typeof v==='string').map(v=>+v.slice(1));
  gs.sort((a,b)=>b-a).forEach(gi=>{
   S.conns=S.conns.filter(c=>c.f!=='g'+gi&&c.t!=='g'+gi);
   S.conns.forEach(c=>{['f','t'].forEach(kk=>{if(typeof c[kk]==='string'&&+c[kk].slice(1)>gi)c[kk]='g'+(+c[kk].slice(1)-1)})});
   S.groups.splice(gi,1)});
  const ns=[...sel].filter(v=>typeof v==='number').sort((a,b)=>b-a);
  ns.forEach(i=>{
   S.conns=S.conns.filter(c=>c.f!==i&&c.t!==i);
   S.conns.forEach(c=>{['f','t'].forEach(kk=>{if(typeof c[kk]==='number'&&c[kk]>i)c[kk]--})});
   S.groups.forEach(g=>{g.nodes=g.nodes.filter(j=>j!==i).map(j=>j>i?j-1:j)});
   S.nodes.splice(i,1)});
  S.groups=S.groups.filter(g=>g.nodes.length);
  sel.clear();render();push()}});
render();push();
</script></body></html>"""


class Handler(BaseHTTPRequestHandler):
    def log_message(self, *a): pass

    def _send(self, body, ctype="text/html; charset=utf-8", code=200):
        b = body.encode() if isinstance(body, str) else body
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(b)))
        self.end_headers()
        self.wfile.write(b)

    def do_GET(self):
        if self.path == "/":
            with STATE_LOCK:
                page = HTML.replace("__STATE__", json.dumps(STATE, ensure_ascii=False))
            self._send(page)
        elif self.path == "/loadfile":
            try:
                self._send(open(SAVE_PATH, encoding="utf-8").read(), "application/json")
            except OSError:
                self._send("{}", "application/json")
        else:
            self._send("nope", code=404)

    def do_POST(self):
        n = int(self.headers.get("Content-Length", 0))
        raw = self.rfile.read(n)
        try:
            data = json.loads(raw)
        except ValueError:
            return self._send("bad", code=400)
        if self.path == "/state":
            with STATE_LOCK:
                STATE.update({k: data[k] for k in ("nodes", "conns", "groups") if k in data})
            write_export()
            self._send("ok", "text/plain")
        elif self.path == "/save":
            with open(SAVE_PATH, "w", encoding="utf-8") as f:
                json.dump({k: data.get(k, []) for k in ("nodes", "conns", "groups")},
                          f, indent=2, ensure_ascii=False)
            self._send("ok", "text/plain")
        else:
            self._send("nope", code=404)


def find_chrome():
    for b in ("google-chrome", "google-chrome-stable", "chromium", "chromium-browser"):
        p = shutil.which(b)
        if p:
            return p
    return None


def main():
    chrome = find_chrome()
    if not chrome:
        sys.exit("Chrome/Chromium не найден. Fallback: ~/bin/mindmap-canvas-tk.py")
    srv = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    port = srv.server_address[1]
    threading.Thread(target=srv.serve_forever, daemon=True).start()

    profile = tempfile.mkdtemp(prefix="mindmap-chrome-")
    try:
        proc = subprocess.Popen(
            [chrome, f"--app=http://127.0.0.1:{port}/", "--window-size=1220,820",
             f"--user-data-dir={profile}", "--no-first-run", "--no-default-browser-check",
             "--disable-session-crashed-bubble"],
            stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        proc.wait()
    finally:
        write_export()
        srv.shutdown()
        shutil.rmtree(profile, ignore_errors=True)
    if not NO_SIGNAL:
        try:
            time.sleep(0.3)
            subprocess.run(["xdotool", "type", "--delay", "20", "Мой вариант готов, прочитай"],
                           timeout=3, capture_output=True)
            time.sleep(0.15)
            subprocess.run(["xdotool", "key", "Return"], timeout=3, capture_output=True)
        except Exception:
            pass


if __name__ == "__main__":
    main()
