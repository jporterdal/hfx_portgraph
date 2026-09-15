#!/usr/bin/env python3
"""Render a diagram of the LangGraph workflow built by
`hfx_portgraph.agent.build_graph()`.

Introspects the compiled graph's actual nodes/edges (via LangGraph's
`get_graph()`) rather than hand-drawing a fixed shape, so the picture stays
accurate if nodes or edges change. Tries LangGraph's own mermaid.ink-backed
PNG renderer first; that requires outbound internet access, which this
sandbox does not have, so it falls back to a small local Pillow renderer
that lays the same node/edge list out in layers.

Usage: .venv/bin/python scripts/visualize_agent_graph.py [output.png]
"""

from __future__ import annotations

import sys
from collections import defaultdict
from pathlib import Path

from hfx_portgraph.agent import build_graph
from hfx_portgraph.paths import ROOT

DEFAULT_OUTPUT = ROOT / "scripts" / "scratch" / "agent_graph.png"

# Descriptive labels for the two conditional edges out of `critic`, per
# `critic_route()` in hfx_portgraph/agent.py -- the compiled graph itself
# carries no label since the path map's keys equal the target node names.
CONDITIONAL_EDGE_LABELS = {
    ("critic", "retriever"): "gaps remain & iteration < max_iterations",
    ("critic", "synthesizer"): "no gaps, or max_iterations reached",
}


def try_mermaid_png(graph, output_path: Path) -> bool:
    try:
        png_bytes = graph.get_graph().draw_mermaid_png()
    except Exception as exc:  # network unavailable, missing renderer, etc.
        print(f"draw_mermaid_png() unavailable ({exc.__class__.__name__}: {exc}); falling back to local renderer.")
        return False
    output_path.write_bytes(png_bytes)
    return True


def compute_layers(nodes: list[str], edges: list[tuple[str, str, bool]]) -> tuple[dict[str, int], set[tuple[str, str]]]:
    """Layer nodes left-to-right by longest forward path from __start__,
    first identifying back edges (DFS cycle detection) so a loop like
    critic->retriever doesn't get treated as a forward dependency."""
    adj: dict[str, list[str]] = defaultdict(list)
    for src, tgt, _cond in edges:
        adj[src].append(tgt)

    visited: set[str] = set()
    on_stack: set[str] = set()
    back_edges: set[tuple[str, str]] = set()

    def dfs(u: str) -> None:
        visited.add(u)
        on_stack.add(u)
        for v in adj[u]:
            if v in on_stack:
                back_edges.add((u, v))
            elif v not in visited:
                dfs(v)
        on_stack.discard(u)

    start = "__start__" if "__start__" in nodes else nodes[0]
    dfs(start)
    for n in nodes:
        if n not in visited:
            dfs(n)

    reverse_forward: dict[str, list[str]] = defaultdict(list)
    for src, tgt, _cond in edges:
        if (src, tgt) not in back_edges:
            reverse_forward[tgt].append(src)

    layer: dict[str, int] = {}

    def get_layer(n: str) -> int:
        if n in layer:
            return layer[n]
        preds = reverse_forward.get(n, [])
        layer[n] = 0 if not preds else 1 + max(get_layer(p) for p in preds)
        return layer[n]

    for n in nodes:
        get_layer(n)
    return layer, back_edges


def render_with_pillow(graph, output_path: Path) -> None:
    from PIL import Image, ImageDraw, ImageFont

    g = graph.get_graph()
    node_ids = list(g.nodes.keys())
    edges = [(e.source, e.target, e.conditional) for e in g.edges]

    layer, back_edges = compute_layers(node_ids, edges)

    by_layer: dict[int, list[str]] = defaultdict(list)
    for n in node_ids:
        by_layer[layer[n]].append(n)
    num_layers = max(layer.values()) + 1
    max_rows = max(len(v) for v in by_layer.values())

    box_w, box_h = 190, 60
    col_gap, row_gap = 110, 90
    margin = 60
    loop_lane_h = 70  # extra vertical room below the grid for back-edge arcs

    width = margin * 2 + num_layers * box_w + (num_layers - 1) * col_gap
    height = margin * 2 + max_rows * box_h + (max_rows - 1) * row_gap + loop_lane_h

    img = Image.new("RGB", (width, height), "white")
    draw = ImageDraw.Draw(img)

    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 15)
        font_small = ImageFont.truetype("DejaVuSans.ttf", 12)
        font_title = ImageFont.truetype("DejaVuSans-Bold.ttf", 20)
    except OSError:
        font = font_small = font_title = ImageFont.load_default()

    draw.text((margin, 18), "hfx_portgraph agent graph (plan -> retrieve -> critique -> answer)", fill="black", font=font_title)

    centers: dict[str, tuple[int, int]] = {}
    for l in range(num_layers):
        col_nodes = sorted(by_layer[l])
        col_x = margin + l * (box_w + col_gap)
        col_height = len(col_nodes) * box_h + (len(col_nodes) - 1) * row_gap
        top = margin + 40 + (max_rows * box_h + (max_rows - 1) * row_gap - col_height) // 2
        for i, n in enumerate(col_nodes):
            y = top + i * (box_h + row_gap)
            centers[n] = (col_x + box_w // 2, y + box_h // 2)

    def node_style(n: str) -> tuple[str, str]:
        if n in ("__start__", "__end__"):
            return "#eeeeee", "#555555"
        return "#dbe9ff", "#2a5db0"

    def draw_arrowhead(x: int, y: int, angle: float, color: str, size: int = 9) -> None:
        import math

        p1 = (x, y)
        p2 = (x - size * math.cos(angle - math.pi / 7), y - size * math.sin(angle - math.pi / 7))
        p3 = (x - size * math.cos(angle + math.pi / 7), y - size * math.sin(angle + math.pi / 7))
        draw.polygon([p1, p2, p3], fill=color)

    def box_edge_point(center: tuple[int, int], toward: tuple[int, int]) -> tuple[int, int]:
        import math

        cx, cy = center
        tx, ty = toward
        angle = math.atan2(ty - cy, tx - cx)
        hw, hh = box_w / 2, box_h / 2
        if abs(math.cos(angle)) < 1e-6:
            return cx, cy + (hh if math.sin(angle) > 0 else -hh)
        t_x = hw / abs(math.cos(angle))
        t_y = hh / abs(math.sin(angle)) if math.sin(angle) != 0 else float("inf")
        t = min(t_x, t_y)
        return int(cx + t * math.cos(angle)), int(cy + t * math.sin(angle))

    # Forward / same-layer edges: straight arrow between box edges.
    for src, tgt, cond in edges:
        if (src, tgt) in back_edges:
            continue
        import math

        c_src, c_tgt = centers[src], centers[tgt]
        p_src = box_edge_point(c_src, c_tgt)
        p_tgt = box_edge_point(c_tgt, c_src)
        color = "#b0862a" if cond else "#555555"
        draw.line([p_src, p_tgt], fill=color, width=2)
        angle = math.atan2(p_tgt[1] - p_src[1], p_tgt[0] - p_src[0])
        draw_arrowhead(p_tgt[0], p_tgt[1], angle, color)
        label = CONDITIONAL_EDGE_LABELS.get((src, tgt))
        if label:
            mx, my = (p_src[0] + p_tgt[0]) // 2, (p_src[1] + p_tgt[1]) // 2
            draw.text((mx - 40, my - 34), label, fill=color, font=font_small)

    # Back edges (loops): arc below the grid.
    for src, tgt in back_edges:
        c_src, c_tgt = centers[src], centers[tgt]
        arc_y = margin + 40 + (max_rows * box_h + (max_rows - 1) * row_gap) + loop_lane_h - 15
        start_pt = (c_src[0], c_src[1] + box_h // 2)
        end_pt = (c_tgt[0], c_tgt[1] + box_h // 2)
        bbox = [min(start_pt[0], end_pt[0]) - 20, min(start_pt[1], end_pt[1]), max(start_pt[0], end_pt[0]) + 20, arc_y]
        draw.line([start_pt, (start_pt[0], arc_y)], fill="#b0862a", width=2)
        draw.line([(start_pt[0], arc_y), (end_pt[0], arc_y)], fill="#b0862a", width=2)
        draw.line([(end_pt[0], arc_y), end_pt], fill="#b0862a", width=2)
        draw_arrowhead(end_pt[0], end_pt[1], -1.5708, "#b0862a")
        label = CONDITIONAL_EDGE_LABELS.get((src, tgt), "loop")
        draw.text(((start_pt[0] + end_pt[0]) // 2 - 90, arc_y + 6), label, fill="#b0862a", font=font_small)

    # Nodes on top of edges.
    for n, (cx, cy) in centers.items():
        fill, outline = node_style(n)
        x0, y0 = cx - box_w // 2, cy - box_h // 2
        x1, y1 = cx + box_w // 2, cy + box_h // 2
        draw.rounded_rectangle([x0, y0, x1, y1], radius=10, fill=fill, outline=outline, width=2)
        label = n.strip("_") if n in ("__start__", "__end__") else n
        bbox = draw.textbbox((0, 0), label, font=font)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        draw.text((cx - tw / 2, cy - th / 2 - bbox[1]), label, fill="black", font=font)

    img.save(output_path)


def main() -> None:
    output_path = Path(sys.argv[1]) if len(sys.argv) > 1 else DEFAULT_OUTPUT
    output_path.parent.mkdir(parents=True, exist_ok=True)

    graph = build_graph()

    if try_mermaid_png(graph, output_path):
        print(f"Wrote {output_path} via LangGraph's draw_mermaid_png().")
        return

    render_with_pillow(graph, output_path)
    print(f"Wrote {output_path} via local Pillow fallback renderer.")


if __name__ == "__main__":
    main()
