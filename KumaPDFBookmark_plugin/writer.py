"""
Write a detected outline back to a PDF using pypdf.

pypdf imports are intentionally deferred into the function body so that
module-level import of this file cannot fail before _ensure_pypdf() runs.
"""
from __future__ import annotations

from pathlib import Path

from calibre_plugins.kumapdfbookmark.extractor import Heading


def write_outline(
    source_path: str,
    dest_path: str,
    headings: list[Heading],
    verbose: bool = False,
) -> None:
    from pypdf import PdfReader, PdfWriter  # deferred — pypdf guaranteed by _ensure_pypdf()

    reader = PdfReader(source_path)
    writer = PdfWriter()

    for page in reader.pages:
        writer.add_page(page)

    if reader.metadata:
        writer.add_metadata(dict(reader.metadata))

    if not headings:
        if verbose:
            print("[writer] No headings to write — saving unchanged PDF.")
        _save(writer, dest_path)
        return

    num_pages = len(reader.pages)
    _add_bookmarks(writer, headings, num_pages, verbose)

    _save(writer, dest_path)
    if verbose:
        print(f"[writer] Saved {len(headings)} bookmarks -> {dest_path}")


def _add_bookmarks(writer, headings, num_pages, verbose):
    from pypdf.generic import Fit  # deferred

    parent: dict[int, object] = {}

    for h in headings:
        page_idx = min(h.page, num_pages - 1)
        level = h.level

        par_ref = None
        for lvl in range(level - 1, 0, -1):
            if lvl in parent:
                par_ref = parent[lvl]
                break

        ref = writer.add_outline_item(
            title=h.title,
            page_number=page_idx,
            parent=par_ref,
            fit=Fit.fit(),
        )
        parent[level] = ref
        for deeper in list(parent.keys()):
            if deeper > level:
                del parent[deeper]

        if verbose:
            indent = "  " * (level - 1)
            print(f"[writer]   {indent}H{level} p{page_idx + 1}: {h.title[:60]}")


def _save(writer, dest_path: str) -> None:
    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        writer.write(f)
