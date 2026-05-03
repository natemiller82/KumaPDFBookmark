"""
Sync auto-pdf-bookmarks/ engine code into KumaPDFBookmark_plugin/, then
package the plugin folder as KumaPDFBookmark.zip for calibre install.

The plugin runs an embedded copy of the CLI engine in calibre's Python
process (subprocess can't avoid the same fitz-bootstrap problem since
calibre's bundled Python doesn't ship PyMuPDF on the linuxserver/calibre
Docker image). This script keeps the embedded copy honest by re-syncing
on every build, so plugin users always see the same extractor/writer
behavior as CLI users.

Usage:
    python build_plugin.py

Outputs:
    KumaPDFBookmark_plugin/{extractor,writer,config,llm_classifier,filtering}.py
        (overwritten from auto-pdf-bookmarks/ at every run)
    KumaPDFBookmark.zip
        (rebuilt from KumaPDFBookmark_plugin/ contents)
"""
from __future__ import annotations

import ast
import os
import re
import sys
import zipfile
from pathlib import Path

# ---------------------------------------------------------------------------
# Layout
# ---------------------------------------------------------------------------

REPO_ROOT   = Path(__file__).resolve().parent
CLI_DIR     = REPO_ROOT / "auto-pdf-bookmarks"
PLUGIN_DIR  = REPO_ROOT / "KumaPDFBookmark_plugin"
ZIP_PATH    = REPO_ROOT / "KumaPDFBookmark.zip"

# Plain copies — overwrite the plugin file with the CLI file, then
# rewrite imports to the calibre_plugins.kumapdfbookmark namespace.
COPY_FILES = ["extractor.py", "writer.py", "config.py", "llm_classifier.py"]

# Module names that, when imported with bare `from X import ...`, refer to
# sibling files in the CLI tree but must be rewritten to the plugin
# namespace so calibre can resolve them.
PLUGIN_NAMESPACE = "calibre_plugins.kumapdfbookmark"
NAMESPACE_MODULES = ("extractor", "writer", "config", "llm_classifier", "filtering")
_BARE_IMPORT_RE = re.compile(
    rf"^from\s+({'|'.join(NAMESPACE_MODULES)})\s+import\s+",
    re.MULTILINE,
)

# Functions + module-level assignments to lift out of main.py for filtering.py.
FILTERING_FUNCS = (
    "_is_front_matter",
    "_has_chapter_number",
    "_is_credential_name",
    "_dedup_key",
    "apply_depth_filter",
)
FILTERING_ASSIGNS = ("_CHAPTER_NUM_PREFIX",)

FILTERING_HEADER = '''\
"""
Depth filtering and deduplication for the calibre plugin.

GENERATED FILE — do not edit by hand.  build_plugin.py extracts
apply_depth_filter() and its helpers from auto-pdf-bookmarks/main.py
and writes them here with plugin-namespaced imports.  The CLI keeps the
same logic inline in main.py because it shares scope with argparse
plumbing; the plugin needs it as a standalone module so worker.py can
import it without dragging in the CLI's argparse code.
"""
from __future__ import annotations

import re

from calibre_plugins.kumapdfbookmark.config import (
    CHAPTER_H1_RE,
    CREDENTIAL_RE,
    FRONT_MATTER_RE,
)
from calibre_plugins.kumapdfbookmark.extractor import Heading
'''

# ZIP exclusions
EXCLUDE_BASENAMES = {"__pycache__", ".DS_Store"}
EXCLUDE_SUFFIXES = (".pyc", ".pyo")


# ---------------------------------------------------------------------------
# Sync steps
# ---------------------------------------------------------------------------

def rewrite_imports(source: str) -> str:
    """Rewrite `from <sibling> import ...` to the plugin namespace."""
    return _BARE_IMPORT_RE.sub(
        rf"from {PLUGIN_NAMESPACE}.\1 import ",
        source,
    )


def sync_one(name: str) -> tuple[str, int, int]:
    """Copy one file from CLI to plugin, rewriting imports.  Returns
    (filename, lines, rewrites)."""
    src_path = CLI_DIR / name
    dst_path = PLUGIN_DIR / name
    raw = src_path.read_text(encoding="utf-8")
    rewritten = rewrite_imports(raw)
    rewrites = len(_BARE_IMPORT_RE.findall(raw))
    dst_path.write_text(rewritten, encoding="utf-8")
    return (name, rewritten.count("\n") + 1, rewrites)


def generate_filtering() -> tuple[str, int]:
    """Build filtering.py by lifting selected functions out of main.py."""
    main_src = (CLI_DIR / "main.py").read_text(encoding="utf-8")
    tree = ast.parse(main_src)

    pieces: list[tuple[int, str]] = []  # (lineno, source) — sort by lineno

    for node in tree.body:
        if isinstance(node, ast.FunctionDef) and node.name in FILTERING_FUNCS:
            seg = ast.get_source_segment(main_src, node)
            if seg:
                pieces.append((node.lineno, seg))
        elif isinstance(node, ast.Assign):
            names = {t.id for t in node.targets if isinstance(t, ast.Name)}
            if names & set(FILTERING_ASSIGNS):
                seg = ast.get_source_segment(main_src, node)
                if seg:
                    pieces.append((node.lineno, seg))

    found_funcs = sum(
        1 for node in tree.body
        if isinstance(node, ast.FunctionDef) and node.name in FILTERING_FUNCS
    )
    if found_funcs != len(FILTERING_FUNCS):
        missing = set(FILTERING_FUNCS) - {
            n.name for n in tree.body
            if isinstance(n, ast.FunctionDef)
        }
        raise RuntimeError(
            f"main.py is missing required functions for filtering.py: {missing}. "
            "Either main.py was refactored or FILTERING_FUNCS is stale."
        )

    pieces.sort(key=lambda p: p[0])
    body = "\n\n\n".join(seg for _, seg in pieces) + "\n"
    full = FILTERING_HEADER + "\n\n" + body

    dst = PLUGIN_DIR / "filtering.py"
    dst.write_text(full, encoding="utf-8")
    return ("filtering.py", full.count("\n") + 1)


# ---------------------------------------------------------------------------
# ZIP build
# ---------------------------------------------------------------------------

def _should_exclude(path: Path) -> bool:
    if path.name in EXCLUDE_BASENAMES:
        return True
    if path.suffix in EXCLUDE_SUFFIXES:
        return True
    if any(part in EXCLUDE_BASENAMES for part in path.parts):
        return True
    return False


def build_zip() -> tuple[int, int]:
    """Repackage PLUGIN_DIR contents as KumaPDFBookmark.zip.  Returns
    (entry_count, byte_size)."""
    if ZIP_PATH.exists():
        ZIP_PATH.unlink()

    entries: list[tuple[Path, str]] = []
    for path in PLUGIN_DIR.rglob("*"):
        if not path.is_file() or _should_exclude(path):
            continue
        # Calibre expects forward-slash arcnames at the ZIP root (no plugin-
        # folder prefix), so files land directly under e.g. extractor.py.
        arcname = path.relative_to(PLUGIN_DIR).as_posix()
        entries.append((path, arcname))

    entries.sort(key=lambda e: e[1])

    with zipfile.ZipFile(ZIP_PATH, "w", zipfile.ZIP_DEFLATED) as zf:
        for path, arcname in entries:
            zf.write(path, arcname)

    return (len(entries), ZIP_PATH.stat().st_size)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def main() -> int:
    print(f"Syncing CLI engine -> plugin")
    print(f"  CLI:    {CLI_DIR}")
    print(f"  Plugin: {PLUGIN_DIR}")

    if not CLI_DIR.is_dir() or not PLUGIN_DIR.is_dir():
        print(f"ERROR: missing CLI or plugin directory.", file=sys.stderr)
        return 1

    print(f"\n  copy + rewrite imports:")
    for name in COPY_FILES:
        fname, lines, rewrites = sync_one(name)
        print(f"    {fname:24s}  {lines:4d} lines  {rewrites} import rewrite(s)")

    print(f"\n  generate filtering.py from main.py AST:")
    fname, lines = generate_filtering()
    print(f"    {fname:24s}  {lines:4d} lines")

    print(f"\nBuilding ZIP -> {ZIP_PATH.name}")
    count, size = build_zip()
    size_mb = size / (1024 * 1024)
    print(f"  {count} entries, {size_mb:.2f} MB ({size:,} bytes)")

    return 0


if __name__ == "__main__":
    sys.exit(main())
