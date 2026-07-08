#!/usr/bin/env python3
"""mindmap-ascii — рендер схемы из mindmap-canvas export координатными линиями.

Читает /tmp/mindmap-export.txt (NODES + POSITIONS + CONNECTIONS), рисует
ASCII-сцену НАСТОЯЩИМИ линиями по сохранённым координатам (zone), не текстовым
списком стрелок и не абзацами.

--mark "X-Y:wrong,X-Y:add" — правки поверх связей юзера (буквы узлов из EXPORT):
  wrong = его связь неверна (x на конце линии)
  add   = его связи не хватает (пунктир + '+' на конце)
Без --mark — просто рисует схему юзера как есть.
"""
import re, argparse

COLS, ROWS = 74, 22


def parse_export(path):
    nodes, pos, conns = {}, {}, []
    section = None
    for raw in open(path, encoding="utf-8"):
        s = raw.strip()
        if s.startswith("=== NODES"):
            section = "nodes"; continue
        if s.startswith("=== POSITIONS"):
            section = "pos"; continue
        if s.startswith("=== CONNECTIONS"):
            section = "conns"; continue
        if s.startswith("==="):
            section = None; continue
        if not s or s.startswith("["):
            continue
        if section == "nodes":
            m = re.match(r"(\w+):\s*(.+)", s)
            if m: nodes[m.group(1)] = m.group(2)
        elif section == "pos":
            m = re.match(r"(\w+):\s*x=(\d+)%\s*y=(\d+)%", s)
            if m: pos[m.group(1)] = (int(m.group(2)), int(m.group(3)))
        elif section == "conns":
            m = re.match(r"(\w+)\s*(->|--|=>|==)\s*(\w+)", s)
            if m: conns.append((m.group(1), m.group(3)))
    return nodes, pos, conns


def to_grid(xpct, ypct):
    gx = min(COLS - 1, max(0, round(xpct / 100 * (COLS - 1))))
    gy = min(ROWS - 1, max(0, round(ypct / 100 * (ROWS - 1))))
    return gx, gy


def place_label(grid, occ, gx, gy, text):
    label = f"[{text}]"
    start = min(max(gx - len(label) // 2, 0), COLS - len(label))
    for i, ch in enumerate(label):
        grid[gy][start + i] = ch
        occ[gy][start + i] = True
    return start + len(label) // 2, gy


def bres(x0, y0, x1, y1):
    pts = []
    dx = abs(x1 - x0); dy = -abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx + dy
    x, y = x0, y0
    while True:
        pts.append((x, y))
        if x == x1 and y == y1: break
        e2 = 2 * err
        if e2 >= dy: err += dy; x += sx
        if e2 <= dx: err += dx; y += sy
    return pts


def line_char(dx, dy):
    if dx == 0: return "|"
    if dy == 0: return "-"
    return "\\" if (dx > 0) == (dy > 0) else "/"


def draw_edge(grid, occ, a, b, style):
    (x0, y0), (x1, y1) = a, b
    pts = bres(x0, y0, x1, y1)
    if len(pts) < 3: return
    pts = pts[1:-1]
    dashed = style == "add"
    for i, (x, y) in enumerate(pts):
        if occ[y][x]: continue
        if dashed and i % 2 == 1: continue
        grid[y][x] = line_char(x1 - x0, y1 - y0)
    free = [p for p in reversed(pts) if not occ[p[1]][p[0]]]
    if not free: return
    ax, ay = free[0]
    if style == "wrong": grid[ay][ax] = "x"
    elif style == "add": grid[ay][ax] = "+"
    else:
        ddx, ddy = x1 - x0, y1 - y0
        if abs(ddx) > abs(ddy) * 1.5: grid[ay][ax] = ">" if ddx > 0 else "<"
        elif abs(ddy) > abs(ddx) * 1.5: grid[ay][ax] = "v" if ddy > 0 else "^"
        else: grid[ay][ax] = "\\" if (ddx > 0) == (ddy > 0) else "/"
    occ[ay][ax] = True


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--export", default="/tmp/mindmap-export.txt")
    ap.add_argument("--mark", default="")
    args = ap.parse_args()

    nodes, pos, conns = parse_export(args.export)
    marks = {}
    for tok in args.mark.split(","):
        tok = tok.strip()
        if not tok: continue
        pair, tag = tok.split(":")
        a, b = pair.split("-")
        marks[(a, b)] = tag

    grid = [[" "] * COLS for _ in range(ROWS)]
    occ = [[False] * COLS for _ in range(ROWS)]
    anchors = {}
    for letter in nodes:
        xp, yp = pos.get(letter, (50, 50))
        gx, gy = to_grid(xp, yp)
        anchors[letter] = place_label(grid, occ, gx, gy, letter)

    edges = list(conns)
    for (a, b), tag in marks.items():
        if tag == "add" and (a, b) not in conns and (b, a) not in conns:
            edges.append((a, b))

    order = {"ok": 0, "wrong": 1, "add": 2}
    edges.sort(key=lambda e: order.get(marks.get(e, marks.get((e[1], e[0]), "ok")), 0))
    for a, b in edges:
        if a not in anchors or b not in anchors: continue
        tag = marks.get((a, b), marks.get((b, a), "ok"))
        draw_edge(grid, occ, anchors[a], anchors[b], tag)

    print("\n".join("".join(row).rstrip() for row in grid))
    print()
    print(" · ".join(f"{k}={v}" for k, v in nodes.items()))
    if marks:
        print("x на конце = твоя связь неверна · пунктир+'+' = не хватало")


if __name__ == "__main__":
    main()
