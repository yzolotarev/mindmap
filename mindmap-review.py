#!/usr/bin/env python3
"""mindmap-review — открывает канвас с реальным расположением юзера + мои
правки жёлтым пунктиром прямо в GUI (не текстом в чате).

Читает /tmp/mindmap-export.txt (NODES + POSITIONS + CONNECTIONS), строит json
для mindmap-canvas.py --load, добавляет correction-рёбра из --mark как typ=fix.

--mark "X-Y:add:причина,X-Y:wrong:причина" — третье поле = короткая надпись (2-4 слова)
прямо на жёлтой стрелке, ГОВОРЯЩАЯ ПОЧЕМУ (не вердикт "верно/неверно"):
  add   = стрелки не хватало  -> жёлтая пунктирная X->Y
  wrong = связь юзера неверна -> его связь не трогается, рядом жёлтая пунктирная
          правильная версия
Без причины подпись по умолчанию: add -> "не хватало", wrong -> "надо так".
"""
import re, json, argparse, subprocess, sys, os

HOME = os.path.expanduser("~")
CANVAS = HOME + "/bin/mindmap-canvas.py"
W, H = 1000, 642


def parse_export(path):
    nodes, pos, conns, groups = {}, {}, [], []
    section = None
    for raw in open(path, encoding="utf-8"):
        s = raw.strip()
        if s.startswith("=== NODES"): section = "nodes"; continue
        if s.startswith("=== POSITIONS"): section = "pos"; continue
        if s.startswith("=== CONNECTIONS"): section = "conns"; continue
        if s.startswith("=== GROUPS"): section = "groups"; continue
        if s.startswith("==="): section = None; continue
        if not s: continue
        if section == "groups":
            m = re.match(r"\[(.+)\]:\s*(.+)", s)
            if m: groups.append((m.group(1), [x.strip() for x in m.group(2).split(",")]))
            continue
        if s.startswith("["): continue
        if section == "nodes":
            m = re.match(r"(\w+):\s*(.+)", s)
            if m: nodes[m.group(1)] = m.group(2)
        elif section == "pos":
            m = re.match(r"(\w+):\s*x=(\d+)%\s*y=(\d+)%", s)
            if m: pos[m.group(1)] = (int(m.group(2)), int(m.group(3)))
        elif section == "conns":
            m = re.match(r"(\w+)\s*(->|--|=>|==)\s*(\w+)(?:\s*:\s*(.+))?", s)
            if m: conns.append((m.group(1), m.group(2), m.group(3), (m.group(4) or "").strip()))
    return nodes, pos, conns, groups


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default="/tmp/mindmap-export.txt")
    ap.add_argument("--mark", default="")
    ap.add_argument("--title", default="правки")
    args = ap.parse_args()

    nodes, pos, conns, groups = parse_export(args.export)
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
        parts = tok.split(":", 2)
        pair, tag = parts[0], parts[1]
        reason = parts[2].strip() if len(parts) > 2 else ""
        a, b = pair.split("-")
        marks[(a, b)] = (tag, reason)

    for (a, b), (tag, reason) in marks.items():
        if a not in idx or b not in idx: continue
        label = reason or ("не хватало" if tag == "add" else "надо так")
        json_conns.append({"f": idx[a], "t": idx[b], "y": "fix", "l": label, "e": False})

    json_groups = []
    for name, members in groups:
        ms = [idx[m] for m in members if m in idx]
        if ms: json_groups.append({"name": name, "nodes": ms})

    data = {"nodes": json_nodes, "conns": json_conns, "groups": json_groups}
    out_path = "/tmp/mindmap-review.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)

    subprocess.Popen(
        ["python3", CANVAS, "--load", out_path, "--title", args.title,
         "--no-signal", "--export-file", "/tmp/mindmap-review-export.txt"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
    )


if __name__ == "__main__":
    main()
