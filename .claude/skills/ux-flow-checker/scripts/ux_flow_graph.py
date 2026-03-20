"""UX Flow Graph — static analysis of Telegram bot handler navigation.

Parses handler files using Python AST, builds a directed graph of
callback transitions, and detects UX issues (dead ends, orphans, deep paths).

Usage:
    python ux_flow_graph.py savebot/handlers/
    python ux_flow_graph.py savebot/handlers/browse.py  # single file
"""

from __future__ import annotations

import ast
import json
import os
import sys
from collections import defaultdict
from pathlib import Path

# Resolve project root (script is in .claude/skills/ux-flow-checker/scripts/)
SCRIPT_DIR = Path(__file__).resolve().parent
SKILL_DIR = SCRIPT_DIR.parent
DATA_DIR = SKILL_DIR / "data"

# Action prefixes that are terminal (no outgoing navigation expected)
ACTION_PREFIXES = {"va:pin:", "va:del:", "va:dyes:", "va:dno:", "va:mc:", "va:ac:", "va:nc:", "noop"}


def extract_string_prefix(node: ast.expr) -> str | None:
    """Extract string or f-string prefix from an AST node."""
    if isinstance(node, ast.Constant) and isinstance(node.value, str):
        return node.value
    if isinstance(node, ast.JoinedStr):
        # f-string: take everything before first FormattedValue
        parts = []
        for v in node.values:
            if isinstance(v, ast.Constant) and isinstance(v.value, str):
                parts.append(v.value)
            else:
                break  # stop at first {variable}
        return "".join(parts) if parts else None
    return None


def normalize_prefix(s: str) -> str:
    """Normalize a callback string to its prefix for graph matching.

    For exact strings like 'bm:cats', return as-is.
    For patterns like 'vi:c:5:42', return 'vi:'.
    """
    # If it ends with ':', it's already a prefix
    if s.endswith(":"):
        return s
    # Known exact-match callbacks
    exact = {"noop", "tags_back", "cat_back", "dcancel", "settings_back"}
    if s in exact:
        return s
    # If it starts with a known 2-3 char prefix + ':', return prefix
    if ":" in s:
        parts = s.split(":")
        prefix = parts[0]
        # bm:cats, bm:tags etc are exact
        if prefix == "bm" and len(parts) >= 2:
            # bm:cats is exact, bm:sources:d has params
            base = f"{parts[0]}:{parts[1]}"
            if len(parts) > 2:
                return base  # bm:sources → parameterized
            return base  # bm:cats → exact
        return prefix + ":"
    return s


class HandlerVisitor(ast.NodeVisitor):
    """Visit a handler file and extract callback registrations and button generations."""

    def __init__(self, filename: str):
        self.filename = filename
        self.handlers: list[dict] = []       # registered handlers
        self.buttons: list[dict] = []        # generated buttons (callback_data=)
        self._current_func: str | None = None
        self._current_func_line: int = 0
        self._current_decorators: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef | ast.AsyncFunctionDef):
        self._current_func = node.name
        self._current_func_line = node.lineno

        # Check decorators for callback/command registrations
        self._current_decorators = []
        for dec in node.decorator_list:
            reg = self._parse_decorator(dec)
            if reg:
                self._current_decorators.append(reg)
                self.handlers.append({
                    "id": reg,
                    "func": node.name,
                    "file": self.filename,
                    "line": node.lineno,
                    "type": self._classify_registration(reg),
                })

        # Visit body to find callback_data generation
        self.generic_visit(node)
        self._current_func = None

    visit_AsyncFunctionDef = visit_FunctionDef

    def _parse_decorator(self, node: ast.expr) -> str | None:
        """Extract registration pattern from a decorator."""
        if not isinstance(node, ast.Call):
            return None

        # router.callback_query(F.data.startswith("prefix:"))
        # router.callback_query(F.data == "exact")
        # router.message(Command("cmd"))
        for arg in node.args:
            result = self._parse_filter(arg)
            if result:
                return result
        return None

    def _parse_filter(self, node: ast.expr) -> str | None:
        """Parse F.data.startswith('x') or F.data == 'x' or Command('x')."""
        # F.data.startswith("prefix")
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "startswith":
                if node.args:
                    s = extract_string_prefix(node.args[0])
                    if s:
                        return s
            # Command("cmd")
            if isinstance(node.func, ast.Name) and node.func.id in ("Command", "CommandStart"):
                if node.args:
                    s = extract_string_prefix(node.args[0])
                    if s:
                        return f"/{s}"
                elif node.func.id == "CommandStart":
                    return "/start"

        # F.data == "exact"
        if isinstance(node, ast.Compare):
            if len(node.ops) == 1 and isinstance(node.ops[0], ast.Eq):
                if node.comparators:
                    s = extract_string_prefix(node.comparators[0])
                    if s:
                        return s

        # F.text.in_(BUTTON_TEXTS) — keyboard buttons
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute) and node.func.attr == "in_":
                return "__keyboard_buttons__"

        return None

    def _classify_registration(self, reg: str) -> str:
        if reg.startswith("/"):
            return "command"
        if reg == "__keyboard_buttons__":
            return "keyboard_button"
        return "callback"

    def visit_Call(self, node: ast.Call):
        """Find callback_data= keyword arguments in function calls."""
        if self._current_func is None:
            self.generic_visit(node)
            return

        for kw in node.keywords:
            if kw.arg == "callback_data":
                s = extract_string_prefix(kw.value)
                if s:
                    self.buttons.append({
                        "from_func": self._current_func,
                        "from_file": self.filename,
                        "from_line": self._current_func_line,
                        "callback_data": s,
                    })
        self.generic_visit(node)


def parse_file(filepath: Path) -> tuple[list[dict], list[dict]]:
    """Parse a single Python file and return (handlers, buttons)."""
    try:
        source = filepath.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(filepath))
    except (SyntaxError, UnicodeDecodeError) as e:
        print(f"  ⚠ Skip {filepath.name}: {e}")
        return [], []

    visitor = HandlerVisitor(filepath.name)
    visitor.visit(tree)
    return visitor.handlers, visitor.buttons


def build_graph(handlers: list[dict], buttons: list[dict]) -> dict:
    """Build directed graph from handlers and buttons."""
    nodes = {}
    edges = []

    # Add handler nodes
    for h in handlers:
        node_id = h["id"]
        nodes[node_id] = {
            "id": node_id,
            "handler": f"{h['file']}:{h['line']}",
            "func": h["func"],
            "type": h["type"],
        }

    # Build edges: for each button, find which handler it targets
    for btn in buttons:
        cb = btn["callback_data"]
        prefix = normalize_prefix(cb)

        # Find source handler (function that generates this button)
        source_handlers = [
            h["id"] for h in handlers
            if h["func"] == btn["from_func"] and h["file"] == btn["from_file"]
        ]

        # Find target handler (handler that catches this callback)
        target = None
        # Try exact match first
        if cb in nodes:
            target = cb
        elif prefix in nodes:
            target = prefix
        else:
            # Try prefix matching against startswith registrations
            for node_id in nodes:
                if node_id.endswith(":") and cb.startswith(node_id):
                    target = node_id
                    break

        for src in source_handlers:
            if target and src != target:
                edges.append({
                    "from": src,
                    "to": target,
                    "callback_data": cb,
                })

    # Deduplicate edges
    seen = set()
    unique_edges = []
    for e in edges:
        key = (e["from"], e["to"])
        if key not in seen:
            seen.add(key)
            unique_edges.append(e)

    return {"nodes": nodes, "edges": unique_edges}


def compute_depths(graph: dict) -> dict[str, int]:
    """BFS from root nodes to compute click depth for each node."""
    nodes = graph["nodes"]
    adj = defaultdict(set)
    for e in graph["edges"]:
        adj[e["from"]].add(e["to"])

    # Root nodes: commands and keyboard buttons
    roots = [
        nid for nid, n in nodes.items()
        if n["type"] in ("command", "keyboard_button")
    ]

    depths: dict[str, int] = {}
    queue = [(r, 0) for r in roots]
    visited = set(roots)

    for r in roots:
        depths[r] = 0

    while queue:
        current, depth = queue.pop(0)
        for neighbor in adj[current]:
            if neighbor not in visited:
                visited.add(neighbor)
                depths[neighbor] = depth + 1
                queue.append((neighbor, depth + 1))

    return depths


def find_warnings(graph: dict, depths: dict[str, int]) -> list[dict]:
    """Detect UX issues in the navigation graph."""
    nodes = graph["nodes"]
    warnings = []

    # Build adjacency sets
    outgoing = defaultdict(set)
    incoming = defaultdict(set)
    for e in graph["edges"]:
        outgoing[e["from"]].add(e["to"])
        incoming[e["to"]].add(e["from"])

    for nid, node in nodes.items():
        # Skip keyboard button handler (catch-all)
        if node["type"] == "keyboard_button":
            continue

        # Check for action prefixes (terminal by design)
        is_action = any(nid.startswith(ap) or nid == ap for ap in ACTION_PREFIXES)

        # Dead ends: no outgoing edges, not a command, not an action
        if not outgoing[nid] and node["type"] == "callback" and not is_action:
            warnings.append({
                "severity": "HIGH",
                "type": "dead_end",
                "node": nid,
                "handler": node["handler"],
                "description": f"Handler '{nid}' has no outgoing navigation (no buttons lead elsewhere)",
                "suggestion": "Add a back button or navigation link",
            })

        # Orphans: no incoming edges, not a root
        if not incoming[nid] and node["type"] == "callback":
            warnings.append({
                "severity": "LOW",
                "type": "orphan",
                "node": nid,
                "handler": node["handler"],
                "description": f"Handler '{nid}' has no incoming edges — unreachable from any button",
                "suggestion": "Add a button that leads here, or remove the handler",
            })

        # Deep paths: more than 4 clicks from root
        depth = depths.get(nid)
        if depth is not None and depth > 4:
            warnings.append({
                "severity": "MED",
                "type": "deep_path",
                "node": nid,
                "handler": node["handler"],
                "depth": depth,
                "description": f"Handler '{nid}' is {depth} clicks from nearest root",
                "suggestion": "Add a shortcut from a higher-level screen",
            })

    # Sort: HIGH first, then MED, then LOW
    severity_order = {"HIGH": 0, "MED": 1, "LOW": 2}
    warnings.sort(key=lambda w: severity_order.get(w["severity"], 3))

    return warnings


def main():
    # Parse arguments
    if len(sys.argv) < 2:
        print("Usage: python ux_flow_graph.py <handlers_dir_or_file>")
        sys.exit(1)

    target = Path(sys.argv[1])
    if not target.exists():
        # Try relative to project root
        project_root = SKILL_DIR.parent.parent.parent
        target = project_root / sys.argv[1]

    if not target.exists():
        print(f"Error: {sys.argv[1]} not found")
        sys.exit(1)

    # Collect files to parse
    if target.is_dir():
        files = sorted(target.glob("*.py"))
    else:
        files = [target]

    print(f"Analyzing {len(files)} file(s)...")

    # Parse all files
    all_handlers = []
    all_buttons = []
    for f in files:
        handlers, buttons = parse_file(f)
        all_handlers.extend(handlers)
        all_buttons.extend(buttons)
        print(f"  {f.name}: {len(handlers)} handlers, {len(buttons)} buttons")

    # Build graph
    graph = build_graph(all_handlers, all_buttons)
    depths = compute_depths(graph)
    warnings = find_warnings(graph, depths)

    # Ensure data directory exists
    DATA_DIR.mkdir(parents=True, exist_ok=True)

    # Save graph
    graph_output = {
        "nodes": list(graph["nodes"].values()),
        "edges": graph["edges"],
    }
    with open(DATA_DIR / "flow_graph.json", "w", encoding="utf-8") as f:
        json.dump(graph_output, f, indent=2, ensure_ascii=False)

    # Save warnings
    with open(DATA_DIR / "flow_warnings.json", "w", encoding="utf-8") as f:
        json.dump(warnings, f, indent=2, ensure_ascii=False)

    # Append to history
    from datetime import datetime
    history_entry = {
        "timestamp": datetime.now().isoformat(),
        "total_nodes": len(graph["nodes"]),
        "total_edges": len(graph["edges"]),
        "dead_ends": sum(1 for w in warnings if w["type"] == "dead_end"),
        "orphans": sum(1 for w in warnings if w["type"] == "orphan"),
        "deep_paths": sum(1 for w in warnings if w["type"] == "deep_path"),
        "max_depth": max(depths.values()) if depths else 0,
    }
    with open(DATA_DIR / "flow_history.jsonl", "a", encoding="utf-8") as f:
        f.write(json.dumps(history_entry, ensure_ascii=False) + "\n")

    # Print summary
    print(f"\n{'='*50}")
    print(f"  UX FLOW REPORT")
    print(f"{'='*50}")
    print(f"  Nodes: {len(graph['nodes'])}")
    print(f"  Edges: {len(graph['edges'])}")
    print(f"  Max depth: {max(depths.values()) if depths else 0}")
    print()

    # Depth distribution
    if depths:
        print("  Click depth distribution:")
        depth_counts = defaultdict(int)
        for d in depths.values():
            depth_counts[d] += 1
        for d in sorted(depth_counts):
            bar = "#" * depth_counts[d]
            print(f"    {d} clicks: {bar} ({depth_counts[d]})")
        print()

    # Warnings
    if warnings:
        high = [w for w in warnings if w["severity"] == "HIGH"]
        med = [w for w in warnings if w["severity"] == "MED"]
        low = [w for w in warnings if w["severity"] == "LOW"]

        if high:
            print("  [HIGH]:")
            for w in high:
                print(f"    {w['handler']} -- {w['description']}")
        if med:
            print("  [MED]:")
            for w in med:
                print(f"    {w['handler']} -- {w['description']}")
        if low:
            print("  [LOW]:")
            for w in low:
                print(f"    {w['handler']} -- {w['description']}")

        print(f"\n  TOTAL: HIGH={len(high)} MED={len(med)} LOW={len(low)}")
    else:
        print("  OK: No warnings found!")

    print(f"{'='*50}")
    print(f"  Output: {DATA_DIR / 'flow_graph.json'}")
    print(f"  Output: {DATA_DIR / 'flow_warnings.json'}")


if __name__ == "__main__":
    main()
