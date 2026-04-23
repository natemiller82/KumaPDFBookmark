"""
Write a detected outline back to a PDF using pypdf.
"""
from __future__ import annotations

from pathlib import Path

from pypdf import PdfReader, PdfWriter
from pypdf.generic import Fit

from calibre_plugins.kumapdfbookmark.extractor import Heading


def write_outline(
    source_path: str,
    dest_path: str,
    headings: list[Heading],
    verbose: bool = False,
) -> None:
    """
    Copy *source_path* to *dest_path* and embed *headings* as PDF bookmarks.

    Args:
        source_path: Original PDF (read-only).
        dest_path:   Output PDF with bookmarks written.
        headings:    Ordered list of Heading objects from extractor.
        verbose:     Emit progress messages.
    """
    reader = PdfReader(source_path)
    writer = PdfWriter()

    # Clone all pages.
    for page in reader.pages:
        writer.add_page(page)

    # Clone existing metadata.
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


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _add_bookmarks(
    writer: PdfWriter,
    headings: list[Heading],
    num_pages: int,
    verbose: bool,
) -> None:
    """
    Insert bookmarks into *writer*, preserving hierarchy up to 3 levels.

    pypdf's add_outline_item API expects a parent reference for nesting.
    We track the last seen bookmark at each level.
    """
    parent: dict[int, object] = {}  # level → bookmark reference

    for h in headings:
        page_idx = min(h.page, num_pages - 1)
        level = h.level

        # Determine parent reference
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
        # Invalidate deeper levels when we move back to a shallower heading
        for deeper in list(parent.keys()):
            if deeper > level:
                del parent[deeper]

        if verbose:
            indent = "  " * (level - 1)
            print(f"[writer]   {indent}H{level} p{page_idx + 1}: {h.title[:60]}")


def _save(writer: PdfWriter, dest_path: str) -> None:
    Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
    with open(dest_path, "wb") as f:
        writer.write(f)
