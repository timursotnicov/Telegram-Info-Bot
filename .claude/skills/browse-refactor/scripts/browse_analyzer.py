"""Analyze browse.py structure for refactoring.

Parses the file using Python's ast module, maps every function,
groups them by purpose, and builds a dependency graph.

Usage:
    python browse_analyzer.py [path_to_browse.py]

Default path: savebot/handlers/browse.py (relative to project root)
"""

from __future__ import annotations

import ast
import json
import os
import sys
from pathlib import Path


# ── Section classification rules ──────────────────────────

# Command handlers: decorated with @router.message(Command(...))
# Callback handlers: decorated with @router.callback_query(...)
# Helpers: everything else (no router decorator)

# Grouping by callback prefix or function name
SECTION_RULES = {
    "commands": {
        "name_patterns": ["cmd_"],
        "decorator_patterns": ["Command("],
    },
    "nav": {
        "callback_prefixes": ["vi:", "vn:"],
        "name_patterns": ["_navigate", "_adjacent", "_related", "_show_item"],
    },
    "list": {
        "callback_prefixes": ["vl:", "browse_cat:", "tag_items:", "bc:", "bm:", "vd:", "vy:", "vx:"],
        "name_patterns": ["_render_list", "_build_list", "_paginate", "_sort_button"],
    },
    "item": {
        "callback_prefixes": ["va:"],
        "name_patterns": ["_action", "_pin", "_delete", "_move", "_tag", "_note", "_edit"],
    },
}


def parse_file(filepath: str) -> ast.Module:
    """Parse a Python file and return the AST."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    return ast.parse(source, filename=filepath)


def get_decorator_info(node: ast.FunctionDef | ast.AsyncFunctionDef) -> list[str]:
    """Extract decorator strings for a function."""
    decorators = []
    for dec in node.decorator_list:
        decorators.append(ast.dump(dec))
    return decorators


def get_decorator_text(node: ast.FunctionDef | ast.AsyncFunctionDef, source_lines: list[str]) -> list[str]:
    """Get the actual source text of decorators."""
    texts = []
    for dec in node.decorator_list:
        start = dec.lineno - 1
        end = getattr(dec, "end_lineno", dec.lineno) - 1
        text = " ".join(source_lines[start:end + 1]).strip()
        if text.startswith("@"):
            text = text[1:]
        texts.append(text)
    return texts


def classify_function_type(decorators_text: list[str]) -> str:
    """Classify function as command_handler, callback_handler, or helper."""
    for dec in decorators_text:
        if "Command(" in dec:
            return "command_handler"
        if "callback_query" in dec:
            return "callback_handler"
        if "message" in dec:
            return "message_handler"
    return "helper"


def extract_callback_prefix(decorators_text: list[str]) -> str | None:
    """Try to extract the callback_data prefix from decorator."""
    for dec in decorators_text:
        if "startswith" in dec:
            # Find the string argument to startswith
            for quote in ['"', "'"]:
                idx = dec.find(f"startswith({quote}")
                if idx >= 0:
                    start = idx + len(f"startswith({quote}")
                    end = dec.find(quote, start)
                    if end >= 0:
                        return dec[start:end]
        if "==" in dec:
            # F.data == "something"
            for quote in ['"', "'"]:
                idx = dec.find(f"== {quote}")
                if idx >= 0:
                    start = idx + len(f"== {quote}")
                    end = dec.find(quote, start)
                    if end >= 0:
                        return dec[start:end]
    return None


def find_internal_calls(node: ast.FunctionDef | ast.AsyncFunctionDef, all_names: set[str]) -> list[str]:
    """Find names of other module-level functions called within this function."""
    calls = []
    for child in ast.walk(node):
        if isinstance(child, ast.Call):
            if isinstance(child.func, ast.Name) and child.func.id in all_names:
                calls.append(child.func.id)
            elif isinstance(child.func, ast.Attribute) and isinstance(child.func.value, ast.Name):
                # Skip method calls like queries.xxx, callback.xxx
                pass
    return sorted(set(calls))


def classify_section(name: str, func_type: str, callback_prefix: str | None) -> str:
    """Assign a function to a section based on rules."""
    # Command handlers go to commands section
    if func_type == "command_handler":
        return "commands"

    # Check callback prefix
    if callback_prefix:
        for section, rules in SECTION_RULES.items():
            for prefix in rules.get("callback_prefixes", []):
                if callback_prefix.startswith(prefix):
                    return section

    # Check name patterns
    for section, rules in SECTION_RULES.items():
        for pattern in rules.get("name_patterns", []):
            if pattern in name:
                return section

    # Default: helpers that are not decoracted go to core
    if func_type == "helper":
        return "core"

    # Unclassified handlers
    return "list"


def analyze(filepath: str) -> dict:
    """Full analysis of a Python handler file."""
    with open(filepath, "r", encoding="utf-8") as f:
        source = f.read()
    source_lines = source.splitlines()
    tree = parse_file(filepath)

    # Collect all top-level function/async function names
    functions = []
    all_names = set()

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            all_names.add(node.name)

    # Analyze each function
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            dec_text = get_decorator_text(node, source_lines)
            func_type = classify_function_type(dec_text)
            cb_prefix = extract_callback_prefix(dec_text)
            internal_calls = find_internal_calls(node, all_names)
            end_line = getattr(node, "end_lineno", node.lineno)
            section = classify_section(node.name, func_type, cb_prefix)

            functions.append({
                "name": node.name,
                "line_start": node.lineno,
                "line_end": end_line,
                "lines": end_line - node.lineno + 1,
                "type": func_type,
                "is_async": isinstance(node, ast.AsyncFunctionDef),
                "callback_prefix": cb_prefix,
                "decorators": dec_text,
                "internal_calls": internal_calls,
                "section": section,
            })

    # Also collect top-level assignments (constants)
    constants = []
    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    end_line = getattr(node, "end_lineno", node.lineno)
                    constants.append({
                        "name": target.id,
                        "line_start": node.lineno,
                        "line_end": end_line,
                    })

    # Group functions by section
    sections = {}
    for func in functions:
        sec = func["section"]
        if sec not in sections:
            sections[sec] = []
        sections[sec].append(func["name"])

    # Build dependency graph
    deps = {}
    for func in functions:
        if func["internal_calls"]:
            deps[func["name"]] = func["internal_calls"]

    # Find shared helpers (called from multiple sections)
    caller_sections = {}  # helper_name -> set of sections that call it
    for func in functions:
        for call_name in func["internal_calls"]:
            if call_name not in caller_sections:
                caller_sections[call_name] = set()
            caller_sections[call_name].add(func["section"])

    shared_helpers = {
        name: sorted(secs) for name, secs in caller_sections.items()
        if len(secs) > 1
    }

    return {
        "filepath": filepath,
        "total_lines": len(source_lines),
        "total_functions": len(functions),
        "total_constants": len(constants),
        "functions": functions,
        "constants": constants,
        "sections": sections,
        "deps": deps,
        "shared_helpers": shared_helpers,
    }


def print_summary(analysis: dict) -> None:
    """Print a console summary table."""
    print("=" * 80)
    print(f"File: {analysis['filepath']}")
    print(f"Total: {analysis['total_lines']} lines, "
          f"{analysis['total_functions']} functions, "
          f"{analysis['total_constants']} constants")
    print("=" * 80)

    # Functions table
    print(f"\n{'Name':<40} {'Lines':<12} {'Type':<18} {'Section':<10}")
    print("-" * 80)
    for func in analysis["functions"]:
        name = func["name"][:39]
        lines = f"{func['line_start']}-{func['line_end']}"
        ftype = func["type"]
        section = func["section"]
        print(f"{name:<40} {lines:<12} {ftype:<18} {section:<10}")

    # Section summary
    print(f"\n{'Section':<12} {'Functions':<10}")
    print("-" * 22)
    for section, funcs in sorted(analysis["sections"].items()):
        print(f"{section:<12} {len(funcs):<10}")

    # Shared helpers
    if analysis["shared_helpers"]:
        print("\nShared helpers (used across sections):")
        for name, secs in sorted(analysis["shared_helpers"].items()):
            secs_str = ", ".join(secs)
            print(f"  {name} -> [{secs_str}]")

    # Dependencies
    if analysis["deps"]:
        dep_count = sum(len(v) for v in analysis["deps"].values())
        print(f"\nDependency edges: {dep_count}")


def save_outputs(analysis: dict) -> None:
    """Save analysis results to JSON files."""
    # Create data/ directory next to the script
    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    # Sections file
    sections_path = data_dir / "browse_sections.json"
    sections_data = {
        "filepath": analysis["filepath"],
        "total_lines": analysis["total_lines"],
        "sections": {},
    }
    for section, func_names in analysis["sections"].items():
        section_funcs = [f for f in analysis["functions"] if f["section"] == section]
        sections_data["sections"][section] = {
            "function_count": len(func_names),
            "functions": [
                {
                    "name": f["name"],
                    "line_start": f["line_start"],
                    "line_end": f["line_end"],
                    "type": f["type"],
                    "callback_prefix": f["callback_prefix"],
                }
                for f in section_funcs
            ],
        }

    with open(sections_path, "w", encoding="utf-8") as f:
        json.dump(sections_data, f, indent=2, ensure_ascii=False)
    print(f"\nSections saved to: {sections_path}")

    # Dependencies file
    deps_path = data_dir / "browse_deps.json"
    deps_data = {
        "filepath": analysis["filepath"],
        "dependencies": analysis["deps"],
        "shared_helpers": analysis["shared_helpers"],
    }
    with open(deps_path, "w", encoding="utf-8") as f:
        json.dump(deps_data, f, indent=2, ensure_ascii=False)
    print(f"Dependencies saved to: {deps_path}")


def main() -> None:
    # Default path relative to project root
    if len(sys.argv) > 1:
        filepath = sys.argv[1]
    else:
        filepath = "savebot/handlers/browse.py"

    # Resolve relative to current directory
    full_path = Path(filepath)
    if not full_path.is_absolute():
        full_path = Path.cwd() / filepath

    if not full_path.exists():
        print(f"[ERR] File not found: {full_path}")
        sys.exit(1)

    analysis = analyze(str(full_path))
    print_summary(analysis)
    save_outputs(analysis)


if __name__ == "__main__":
    main()
