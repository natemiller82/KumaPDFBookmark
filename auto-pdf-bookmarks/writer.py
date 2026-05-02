"""
Write a detected outline back to a PDF using PyMuPDF (fitz).

fitz is preferred over pypdf here because pypdf's catalog/root validation
rejects some legitimately-structured PDFs (e.g. Janfaza, which raises
LimitReachedError on the recovery path).  fitz reads and writes those
files without complaint, and we already depend on it for extraction.
"""
from __future__ import annotations

from pathlib import Path

import fitz  # PyMuPDF

from extractor import Heading


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
    doc = fitz.open(source_path)
    try:
        if headings:
            num_pages = doc.page_count
            toc = _build_toc(headings, num_pages, verbose)
            # collapse=False preserves the existing page-tree pointers; fitz
            # handles level-based hierarchy itself, so we don't need to track
            # parent references the way pypdf does.
            doc.set_toc(toc)
        elif verbose:
            print("[writer] No headings to write — saving unchanged PDF.")

        Path(dest_path).parent.mkdir(parents=True, exist_ok=True)
        # garbage=1 sweeps unreferenced objects (including the old outline
        # tree that set_toc just replaced) without the expensive stream
        # recompression that garbage>=3 / deflate=True would trigger.
        doc.save(dest_path, garbage=1)
        if verbose:
            print(f"[writer] Saved {len(headings)} bookmarks -> {dest_path}")
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _build_toc(
    headings: list[Heading],
    num_pages: int,
    verbose: bool,
) -> list[list]:
    """
    Convert Heading objects into the fitz set_toc format:
    [[level, title, page_1indexed], ...].

    fitz requires the first entry to be at level 1 and every subsequent
    entry's level to differ from its predecessor by at most +1 (no jumping
    from level 1 straight to level 3).  We fix up the latter by clamping
    each entry's level to prev_level + 1.
    """
    toc: list[list] = []
    prev_level = 0
    for h in headings:
        # Clamp page to valid range (PyMuPDF expects 1-indexed for set_toc)
        page_1idx = max(1, min(h.page + 1, num_pages))

        # Enforce monotonic level rules required by set_toc.
        level = h.level
        if not toc:
            level = 1  # first entry must be level 1
        elif level > prev_level + 1:
            level = prev_level + 1

        toc.append([level, h.title, page_1idx])
        prev_level = level

        if verbose:
            indent = "  " * (level - 1)
            print(f"[writer]   {indent}H{level} p{page_1idx}: {h.title[:60]}")

    return toc
