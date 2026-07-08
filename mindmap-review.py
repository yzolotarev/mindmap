#!/usr/bin/env python3
"""mindmap-review — открывает канвас с реальным расположением юзера + мои
правки жёлтым пунктиром прямо в GUI (не текстом в чате).

Читает /tmp/mindmap-export.txt (NODES + POSITIONS + CONNECTIONS), строит json
для mindmap-canvas.py --load, добавляет correction-рёбра из --mark как typ=fix.

--mark "X-Y:add,X-Y:wrong" — как в mindmap-ascii.py:
  add   = стрелки не хватало  -> жёлтая пунктирная X->Y с меткой "+ добавлено"
  wrong = связь юзера неверна -> сама связь юзера не трогается, рядом рисуется
          жёлтая пунктирная "правильная" версия с меткой "✓ верно"
"""
import re, json, argparse, subprocess, sys, os

HOME = os.path.expanduser("~")
CANVAS = HOME + "/bin/mindmap-canvas.py"
W, H = 1000, 642


def parse_export(path):
    nodes, pos, conns = {}, {}, []
    section = None
    for raw in open(path, encoding="utf-8"):
        s = raw.strip()
        if s.startswith("=== NODES"): section = "nodes"; continue
        if s.startswith("=== POSITIONS"): section = "pos"; continue
        if s.startswith("=== CONNECTIONS"): section = "conns"; continue
        if s.startswith("==="): section = None; continue
        if not s or s.startswith("["): continue
        if section == "nodes":
            m = re.match(r"(\w+):\s*(.+)", s)
            if m: nodes[m.group(1)] = m.group(2)
        elif section == "pos":
            m = re.match(r"(\w+):\s*x=(\d+)%\s*y=(\d+)%", s)
            if m: pos[m.group(1)] = (int(m.group(2)), int(m.group(3)))
        elif section == "conns":
            m = re.match(r"(\w+)\s*(->|--|=>|==)\s*(\w+)(?:\s*:\s*(.+))?", s)
            if m: conns.append((m.group(1), m.group(2), m.group(3), (m.group(4) or "").strip()))
    return nodes, pos, conns


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default="/tmp/mindmap-export.txt")
    ap.add_argument("--mark", default="")
    ap.add_argument("--title", default="правки")
    args = ap.parse_args()

    nodes, pos, conns = parse_export(args.export)
    letters = list(nodes.keys())
    idx = {l: i for i, l in enumerate(letters)}

    json_nodes = []
    for l in letters:
        xp, yp = pos.get(l, (50, 50))
        json_nodes.append({"name": nodes[l], "x": xp / 100 * W, "y": yp / 100 * H})

    json_conns = []
    for a, arrow, b, label in conns:
        if a not in idx or b not in idx: continue
        typ = "arrow" if arrow in ("->", "=>") else "line"
        emph = arrow in ("=>", "==")
        json_conns.append({"f": idx[a], "t": idx[b], "y": typ, "l": label, "e": emph})

    marks = {}
    for tok in args.mark.split(","):
        tok = tok.strip()
        if not tok: continue
        pair, tag = tok.split(":")
        a, b = pair.split("-")
        marks[(a, b)] = tag

    for (a, b), tag in marks.items():
        if a not in idx or b not in idx: continue
        label = "+ добавлено" if tag == "add" else "✓ верно"
        json_conns.append({"f": idx[a], "t": idx[b], "y": "fix", "l": label, "e": False})

    data = {"nodes": json_nodes, "conns": json_conns, "groups": []}
    out_path = "/tmp/mindmap-review.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    subprocess.Popen(
        ["python3", CANVAS, "--load", out_path, "--title", args.title],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    main()
