#!/usr/bin/env python3
"""
mindmap-canvas — 2D graph editor.

C=arrow V=line B=group  LMB=drag  RMB=connect
2xLMB на линии=метка ('!' в конце = жирная/emphasized)
Ctrl+Z=undo  Ctrl+E=export  close=auto-export

--nodes "A::B::C" (разделители :: | или перенос)  --title "тема"  --load file.json
Экспорт: /tmp/mindmap-export.txt   ->/-- обычная   =>/== жирная   ": метка" после связи
"""
import tkinter as tk
from tkinter import messagebox, simpledialog
import tkinter.font as tkFont
import json, os, sys, math, random, copy, subprocess

def _round_rect_coords(cx, cy, w, h, r, steps=12):
    l = cx - w//2; t = cy - h//2
    pts = []
    def arc(cx, cy, sa, ea):
        for i in range(1, steps+1):
            a = sa + (ea-sa)*i/steps
            pts.append(cx + r*math.cos(a))
            pts.append(cy + r*math.sin(a))
    pts.append(l + r); pts.append(t); pts.append(l + w - r); pts.append(t)
    arc(l + w - r, t + r, -math.pi/2, 0)
    pts.append(l + w); pts.append(t + r); pts.append(l + w); pts.append(t + h - r)
    arc(l + w - r, t + h - r, 0, math.pi/2)
    pts.append(l + w - r); pts.append(t + h); pts.append(l + r); pts.append(t + h)
    arc(l + r, t + h - r, math.pi/2, math.pi)
    pts.append(l); pts.append(t + h - r); pts.append(l); pts.append(t + r)
    arc(l + r, t + r, math.pi, 3*math.pi/2)
    return pts

HOME = os.path.expanduser("~")
SAVE_PATH = f"{HOME}/.mindmap_canvas.json"

_theme = "dark"  # force dark

if _theme == "dark":
    BG          = "#1e1e24"
    FG          = "#e2e8f0"
    BAR_BG      = "#141419"
    NODE_FILL   = "#2a2b36"
    NODE_OUTL   = "#3f4257"
    NODE_SEL    = "#f9e2af"
    CONN_ARROW  = "#f38ba8"
    CONN_LINE   = "#a6e3a1"
    GROUP_C     = "#57b8c0"
    STATUS_FG   = "#6c7086"
    BTN_BG      = "#2a2b36"
    BTN_FG      = "#e2e8f0"
else:
    BG          = "#f8f9fa"
    FG          = "#1a202c"
    BAR_BG      = "#edf2f7"
    NODE_FILL   = "#ffffff"
    NODE_OUTL   = "#e2e8f0"
    NODE_SEL    = "#cc8800"
    CONN_ARROW  = "#e53e3e"
    CONN_LINE   = "#38a169"
    GROUP_C     = "#319795"
    STATUS_FG   = "#718096"
    BTN_BG      = "#ffffff"
    BTN_FG      = "#1a202c"

FONT = ("Sans", 9)
FONT_BOLD = ("Ubuntu", 11, "bold")  # разработан для читаемости на экране, кириллица


class Node:
    def __init__(self, ca, x, y, name):
        self.ca, self.name = ca, name
        self.x, self.y, self.selected = x, y, False
        self.font_obj = tkFont.Font(font=FONT_BOLD)
        tw = self.font_obj.measure(name)
        self.w = max(100, tw + 32)
        self.h = max(38, 28)
        self.shape = self.label = None
        self._draw()

    def _draw(self):
        r = 8
        pts = _round_rect_coords(self.x, self.y, self.w, self.h, r, steps=8)
        self.shape = self.ca.create_polygon(
            *pts, fill=NODE_FILL, outline=NODE_OUTL, width=2, tags="node")
        self.label = self.ca.create_text(
            self.x, self.y, text=self.name, fill=FG,
            font=FONT_BOLD, width=self.w - 20, justify=tk.CENTER, tags="node")

    def select(self, b):
        self.selected = b
        self.ca.itemconfig(self.shape, outline=NODE_SEL if b else NODE_OUTL, width=3 if b else 2)

    def move(self, dx, dy):
        self.x += dx; self.y += dy
        self.ca.move(self.shape, dx, dy)
        self.ca.move(self.label, dx, dy)

    def rename(self, n):
        self.name = n
        self.ca.delete(self.shape); self.ca.delete(self.label)
        self._draw()

    def contains(self, px, py):
        dx = (px - self.x) / max(self.w/2, 1)
        dy = (py - self.y) / max(self.h/2, 1)
        return dx*dx + dy*dy <= 1.2

    def in_rect(self, x1, y1, x2, y2):
        x1,x2=sorted((x1,x2)); y1,y2=sorted((y1,y2))
        rx, ry = self.w//2, self.h//2
        return self.x+rx>=x1 and self.x-rx<=x2 and self.y+ry>=y1 and self.y-ry<=y2


class GroupBox:
    is_group = True
    def __init__(self, ca, nodes, name=None):
        self.ca, self.nodes, self.name = ca, list(nodes), name or "Group"
        self.font = tkFont.Font(family="Ubuntu", size=9, slant="italic")
        self.selected = False
        self.rect_id = self.label_id = None
        self.x = self.y = 0
        self._recalc()
        self._draw()

    def _recalc(self):
        if not self.nodes: return
        pad = 30
        xs = [n.x for n in self.nodes]; ys = [n.y for n in self.nodes]
        self.x1 = min(xs)-pad; self.y1 = min(ys)-pad
        self.x2 = max(xs)+pad; self.y2 = max(ys)+pad
        self.x = (self.x1+self.x2)//2; self.y = (self.y1+self.y2)//2

    def _draw(self):
        if not self.nodes: return
        self._recalc()
        self.rect_id = self.ca.create_rectangle(
            self.x1, self.y1, self.x2, self.y2,
            outline=GROUP_C, width=2, dash=(8,4), tags="group")
        self.label_id = self.ca.create_text(
            self.x1+10, self.y1-8, anchor="sw",
            text=self.name, fill=GROUP_C, font=self.font, tags="group")

    def redraw(self):
        if self.rect_id: self.ca.delete(self.rect_id)
        if self.label_id: self.ca.delete(self.label_id)
        self._draw()

    def move(self, dx, dy):
        for n in self.nodes: n.move(dx, dy)
        self._recalc()
        if self.rect_id and self.label_id:
            self.ca.delete(self.rect_id); self.ca.delete(self.label_id)
            self._draw()

    def select(self, b):
        self.selected = b
        if self.rect_id:
            self.ca.itemconfig(self.rect_id, outline=NODE_SEL if b else GROUP_C, width=3 if b else 2)

    def contains(self, px, py):
        if self.x1 <= px <= self.x2 and self.y1 <= py <= self.y2:
            return True
        # также лейбл сверху
        if self.label_id:
            lx1, ly1 = self.x1 + 10, self.y1 - 8
            lb = self.font.measure(self.name)
            return lx1 <= px <= lx1 + lb + 4 and ly1 - 12 <= py <= ly1 + 4
        return False

    def cx(self): return self.x
    def cy(self): return self.y


class Connection:
    def __init__(self, ca, a, b, typ="arrow", label="", emph=False):
        self.ca, self.a, self.b, self.typ = ca, a, b, typ
        self.label, self.emph = label, emph
        self.id = self.label_id = None
        self._draw()

    def _ends(self):
        ax = self.a.cx() if hasattr(self.a,'cx') else self.a.x
        ay = self.a.cy() if hasattr(self.a,'cy') else self.a.y
        bx = self.b.cx() if hasattr(self.b,'cx') else self.b.x
        by = self.b.cy() if hasattr(self.b,'cy') else self.b.y
        return ax, ay, bx, by

    def _draw(self):
        c = CONN_ARROW if self.typ=="arrow" else CONN_LINE
        a = tk.LAST if self.typ=="arrow" else None
        ax, ay, bx, by = self._ends()
        self.id = self.ca.create_line(
            ax, ay, bx, by, fill=c, width=5 if self.emph else 3, arrow=a,
            smooth=True, splinesteps=36, tags="conn")
        if self.label:
            mx, my = (ax+bx)//2, (ay+by)//2
            self.label_id = self.ca.create_text(
                mx, my-10, text=self.label, fill=c,
                font=("Ubuntu", 9, "italic"), tags="conn")

    def redraw(self):
        self.delete(); self._draw()

    def delete(self):
        if self.id: self.ca.delete(self.id); self.id = None
        if self.label_id: self.ca.delete(self.label_id); self.label_id = None

    def touches(self, o): return self.a is o or self.b is o

    def near(self, px, py, tol=9):
        ax, ay, bx, by = self._ends()
        dx, dy = bx-ax, by-ay
        L2 = dx*dx + dy*dy
        if L2 == 0: return math.hypot(px-ax, py-ay) <= tol
        t = max(0, min(1, ((px-ax)*dx + (py-ay)*dy) / L2))
        return math.hypot(px-(ax+t*dx), py-(ay+t*dy)) <= tol


class Snapshot:
    def __init__(self, nodes, conns, groups):
        self.nodes = copy.deepcopy(nodes)
        self.conns = copy.deepcopy(conns)
        self.groups = copy.deepcopy(groups)


class App:
    def __init__(self, root):
        self.root = root
        root.title("Mindmap Canvas")
        root.geometry("1000x700")
        root.configure(bg=BG)
        self.nodes = []
        self.conns = []
        self.groups = []
        self.sel = None
        self.selected = set()
        self.drag = None
        self.drag_xy = None
        self.rubber = None
        self.undo_stack = []
        self.undo_limit = 50
        self._build()
        self._bind()

    def _snap(self):
        idx = {id(n):i for i,n in enumerate(self.nodes)}
        nd = [{"name":n.name,"x":n.x,"y":n.y,"d":getattr(n,'desc','')} for n in self.nodes]
        cd = []
        for c in self.conns:
            ai, bi = idx.get(id(c.a),-1), idx.get(id(c.b),-1)
            if ai>=0 and bi>=0: cd.append({"f":ai,"t":bi,"y":c.typ,"l":c.label,"e":c.emph})
        gd = []
        for g in self.groups:
            members = [idx.get(id(n),-1) for n in g.nodes if id(n) in idx]
            gd.append({"name":g.name,"nodes":members})
        self.undo_stack.append(Snapshot(nd, cd, gd))
        if len(self.undo_stack) > self.undo_limit: self.undo_stack.pop(0)

    def _restore(self, s):
        for c in self.conns: c.delete()
        for g in self.groups:
            if g.rect_id: self.ca.delete(g.rect_id)
            if g.label_id: self.ca.delete(g.label_id)
        for n in self.nodes: self.ca.delete(n.shape); self.ca.delete(n.label)
        self.nodes.clear(); self.conns.clear(); self.groups.clear(); self.sel = None; self.selected.clear()
        for nd in s.nodes:
            n = Node(self.ca, nd["x"], nd["y"], nd["name"])
            self.nodes.append(n)
        for cd in s.conns:
            if cd["f"]<len(self.nodes) and cd["t"]<len(self.nodes):
                self.conns.append(Connection(self.ca, self.nodes[cd["f"]], self.nodes[cd["t"]],
                    cd.get("y","arrow"), cd.get("l",""), cd.get("e",False)))
        for gd in s.groups:
            ms = [self.nodes[i] for i in gd["nodes"] if i<len(self.nodes)]
            if ms: self.groups.append(GroupBox(self.ca, ms, gd.get("name")))

    def undo(self, e=None):
        if not self.undo_stack: return self._msg("Nothing to undo")
        self._restore(self.undo_stack.pop()); self._msg("Undone")

    def _build(self):
        bar = tk.Frame(self.root, bg=BAR_BG, height=34)
        bar.pack(fill=tk.X, side=tk.TOP)
        def bt(text, cmd):
            tk.Button(bar, text=text, command=cmd, bg=BTN_BG, fg=BTN_FG,
                relief=tk.FLAT, padx=8, pady=2, cursor="hand2",
                font=("Helvetica", 9)).pack(side=tk.LEFT, padx=3, pady=3)
        bt("+ Node", self._dlg_add)
        bt("Import", self._dlg_import)
        self.mode = tk.StringVar(value="arrow")
        for v,t,c in [("arrow","C →",CONN_ARROW),("line","V —",CONN_LINE),("group","B □",GROUP_C)]:
            tk.Radiobutton(bar, text=t, variable=self.mode, value=v,
                bg=BAR_BG, fg=c, selectcolor=BTN_BG, indicatoron=False,
                activebackground=BAR_BG, activeforeground=c,
                font=("Helvetica",9), padx=6, relief=tk.FLAT, cursor="hand2"
            ).pack(side=tk.LEFT, padx=1)
        bt("Undo", self.undo)
        bt("Export", self.export)
        bt("Save", self.save)
        bt("Load", self.load)
        bt("Clear", self._clear)
        self.ca = tk.Canvas(self.root, bg=BG, highlightthickness=0, height=600)
        self.ca.pack(fill=tk.BOTH, expand=True)
        self.status = tk.Label(self.root,
            text="C=arrow V=line B=group | LMB=drag RMB=connect 2xLMB(линия)=метка | Ctrl+Z Ctrl+E",
            bg=BAR_BG, fg=STATUS_FG, anchor=tk.W, padx=10,
            font=("Helvetica", 9))
        self.status.pack(fill=tk.X, side=tk.BOTTOM)

    def _bind(self):
        self.root.protocol("WM_DELETE_WINDOW", self._close)
        self.ca.bind("<Button-1>", self._lmb)
        self.ca.bind("<B1-Motion>", self._drag)
        self.ca.bind("<ButtonRelease-1>", self._up)
        self.ca.bind("<Button-3>", self._rmb)
        self.ca.bind("<Double-Button-1>", self._dbl)
        self.root.bind("<Delete>", self._del)
        self.root.bind("<Control-z>", self.undo)
        self.root.bind("<Control-s>", lambda e: self.save())
        self.root.bind("<Control-e>", lambda e: self.export())
        for k in "cC": self.root.bind(k, lambda e: self.mode.set("arrow"))
        for k in "vV": self.root.bind(k, lambda e: self.mode.set("line"))
        for k in "bB": self.root.bind(k, lambda e: self.mode.set("group"))

    def _hit(self, x, y):
        for n in reversed(self.nodes):
            if n.contains(x, y): return n
        for g in reversed(self.groups):
            if g.contains(x, y): return g
        return None

    def add_node(self, name, x=None, y=None, snap=True):
        if snap: self._snap()
        W = self.ca.winfo_width() or 900
        H = self.ca.winfo_height() or 600
        if x is None:
            a = len(self.nodes) * 2.39996 + random.uniform(-.08, .08)
            r = min(W, H) * .32 + random.uniform(-20, 20)
            x = W//2 + r*math.cos(a)
            y = H//2 + r*math.sin(a)
        n = Node(self.ca, x, y, name)
        self.nodes.append(n)
        return n

    def _dlg_add(self):
        n = simpledialog.askstring("New Node", "Name:", parent=self.root)
        if n: self.add_node(n.strip())

    def _dlg_import(self):
        top = tk.Toplevel(self.root)
        top.title("Import Nodes"); top.geometry("500x350"); top.configure(bg=BG)
        tk.Label(top, text="One per line:", bg=BG, fg=FG, font=("Helvetica",10)).pack(pady=8)
        t = tk.Text(top, bg=NODE_FILL, fg=FG, font=("Helvetica",10), insertbackground=FG, height=12)
        t.pack(fill=tk.BOTH, expand=True, padx=10, pady=5)
        def do():
            r = t.get("1.0", tk.END).strip()
            if not r: return
            self._snap()
            for ln in r.split("\n"):
                ln = ln.strip()
                if not ln: continue
                if " — " in ln: ln = ln.split(" — ", 1)[0]
                self.add_node(ln, snap=False)
            top.destroy(); self._msg("Imported")
        tk.Button(top, text="Import", command=do,
            bg=BTN_BG, fg=BTN_FG, relief=tk.FLAT, padx=16, pady=4).pack(pady=8)

    def _lmb(self, e):
        x,y = e.x, e.y; h = self._hit(x,y)
        if h:
            if h not in self.selected:
                for s in list(self.selected): s.select(False)
                self.selected.clear()
                h.select(True); self.selected.add(h)
            self.sel = h; self.drag = h; self.drag_xy = (x,y)
        else:
            for s in list(self.selected): s.select(False)
            self.selected.clear(); self.sel = None
            self.drag_xy = (x,y)
            self.rubber = self.ca.create_rectangle(x,y,x,y,outline=GROUP_C,width=1,dash=(4,2))

    def _rmb(self, e):
        h = self._hit(e.x, e.y)
        if not h or not self.sel or h is self.sel: return
        self._snap()
        self.conns.append(Connection(self.ca, self.sel, h, self.mode.get()))
        self.sel.select(False); self.sel = None; self._msg("Connected")

    def _drag(self, e):
        if self.rubber:
            x1,y1 = self.drag_xy; self.ca.coords(self.rubber, x1,y1, e.x,e.y)
            return
        if self.drag and self.drag_xy:
            dx = e.x - self.drag_xy[0]; dy = e.y - self.drag_xy[1]
            moved = list(self.selected) if len(self.selected) > 1 else [self.drag]
            for obj in moved:
                obj.move(dx, dy)
                for c in self.conns:
                    if c.touches(obj) or (getattr(obj,'is_group',False) and any(c.touches(n) for n in obj.nodes)):
                        c.redraw()
                for g in self.groups:
                    if obj is not g and (obj in g.nodes or obj is g): g.redraw()
            self.drag_xy = (e.x, e.y)

    def _up(self, e):
        if self.rubber:
            x1,y1 = self.drag_xy; x2,y2 = e.x, e.y
            inside = [n for n in self.nodes if n.in_rect(x1,y1,x2,y2)]
            self.ca.delete(self.rubber); self.rubber = None
            if inside:
                for s in list(self.selected): s.select(False)
                self.selected.clear(); self.sel = None
                for n in inside: n.select(True); self.selected.add(n)
                self._msg(f"Selected {len(inside)}")
                if self.mode.get() == "group":
                    self._snap()
                    nm = simpledialog.askstring("Group", "Name (or Cancel):", parent=self.root)
                    self.groups.append(GroupBox(self.ca, inside, nm.strip() if nm else None))
                    self._msg(f"Grouped {len(inside)} nodes")
            return
        self.drag = None; self.drag_xy = None

    def _dbl(self, e):
        h = self._hit(e.x, e.y)
        if h and not getattr(h, 'is_group', False):
            nm = simpledialog.askstring("Rename", "New name:", initialvalue=h.name, parent=self.root)
            if nm: self._snap(); h.rename(nm.strip())
            for c in self.conns:
                if c.touches(h): c.redraw()
            return
        if not h:
            for c in reversed(self.conns):
                if c.near(e.x, e.y):
                    init = c.label + ("!" if c.emph else "")
                    lb = simpledialog.askstring(
                        "Связь", "Метка связи ('!' в конце = жирная, пусто = убрать):",
                        initialvalue=init, parent=self.root)
                    if lb is None: return
                    self._snap()
                    lb = lb.strip()
                    c.emph = lb.endswith("!")
                    c.label = lb.rstrip("!").strip()
                    c.redraw()
                    return

    def _del(self, e):
        if not self.sel: return
        targets = list(self.selected) if len(self.selected) > 1 else [self.sel]
        self._snap()
        for n in targets:
            self.conns = [c for c in self.conns if not c.touches(n)]
            for g in self.groups:
                if n in g.nodes: g.nodes.remove(n)
                g.redraw()
            self.ca.delete(n.shape); self.ca.delete(n.label)
            if n in self.nodes: self.nodes.remove(n)
        self.selected.clear(); self.sel = None

    def _clear(self):
        if not self.nodes: return
        if not messagebox.askyesno("Clear", "Clear all?"): return
        self._snap()
        for c in self.conns: c.delete()
        for g in self.groups:
            if g.rect_id: self.ca.delete(g.rect_id)
            if g.label_id: self.ca.delete(g.label_id)
        for n in self.nodes: self.ca.delete(n.shape); self.ca.delete(n.label)
        self.nodes.clear(); self.conns.clear(); self.groups.clear(); self.sel = None; self.selected.clear()

    def export(self):
        if not self.nodes: return
        idx = {n:chr(65+i) if i<26 else f"N{i}" for i,n in enumerate(self.nodes)}
        lines = ["[MINDMAP EXPORT]", "=== NODES ==="]
        for n in self.nodes: lines.append(f"  {idx[n]}: {n.name}")
        if self.conns:
            lines += ["", "=== CONNECTIONS ==="]
            for c in self.conns:
                a = idx.get(c.a,"?") if not getattr(c.a,'is_group',False) else f"[{c.a.name}]"
                b = idx.get(c.b,"?") if not getattr(c.b,'is_group',False) else f"[{c.b.name}]"
                arrow = ("=>" if c.emph else "->") if c.typ=="arrow" else ("==" if c.emph else "--")
                tail = f" : {c.label}" if c.label else ""
                lines.append(f"  {a} {arrow} {b}{tail}")
        if self.groups:
            lines += ["", "=== GROUPS ==="]
            for g in self.groups:
                ms = [idx.get(n,"?") for n in g.nodes]
                lines.append(f"  [{g.name}]: {', '.join(ms)}")
        r = "\n".join(lines)
        self.root.clipboard_clear(); self.root.clipboard_append(r)
        with open("/tmp/mindmap-export.txt", "w") as f: f.write(r)
        self._msg("Exported!")

    def save(self):
        idx = {id(n):i for i,n in enumerate(self.nodes)}
        data = {
            "nodes": [{"name":n.name,"x":n.x,"y":n.y} for n in self.nodes],
            "conns": [{"f":idx[id(c.a)],"t":idx[id(c.b)],"y":c.typ,"l":c.label,"e":c.emph}
                      for c in self.conns if id(c.a) in idx and id(c.b) in idx],
            "groups": [{"name":g.name,"nodes":[idx[id(n)] for n in g.nodes if id(n) in idx]} for g in self.groups],
        }
        with open(SAVE_PATH, "w") as f: json.dump(data, f, indent=2, ensure_ascii=False)
        self._msg("Saved")

    def load(self, p=None):
        p = p or SAVE_PATH
        if not os.path.exists(p): return
        self._clear()
        with open(p) as f: data = json.load(f)
        for nd in data.get("nodes",[]): self.add_node(nd["name"], nd.get("x",100), nd.get("y",100), snap=False)
        for c in data.get("conns",[]):
            if c["f"] < len(self.nodes) and c["t"] < len(self.nodes):
                self.conns.append(Connection(self.ca, self.nodes[c["f"]], self.nodes[c["t"]],
                    c.get("y","arrow"), c.get("l",""), c.get("e",False)))
        self._msg("Loaded")

    def _msg(self, m): self.status.config(text=m)

    def _close(self):
        if self.nodes: self.export()
        self.root.destroy()
        try:
            import subprocess, time
            time.sleep(0.3)
            # длинная фраза — проходит shouldSkip ( > 20 символов)
            subprocess.run(
                ["xdotool", "type", "--delay", "20", "Мой вариант готов, прочитай"],
                timeout=3, capture_output=True
            )
            time.sleep(0.15)
            subprocess.run(["xdotool", "key", "Return"], timeout=3, capture_output=True)
        except:
            pass


def main():
    root = tk.Tk(); app = App(root)
    def delayed():
        if "--load" in sys.argv:
            idx = sys.argv.index("--load"); app.load(sys.argv[idx+1] if idx+1<len(sys.argv) else None)
        if "--title" in sys.argv:
            idx = sys.argv.index("--title")
            if idx+1 < len(sys.argv): root.title("Mindmap — " + sys.argv[idx+1])
        if "--nodes" in sys.argv:
            idx = sys.argv.index("--nodes")
            if idx+1 < len(sys.argv):
                import re as _re
                for n in _re.split(r"::|\||\n", sys.argv[idx+1]):
                    n = n.strip()
                    if n: app.add_node(n, snap=False)
                app._msg("Ready")
    root.after(100, delayed); root.mainloop()

if __name__ == "__main__":
    main()
