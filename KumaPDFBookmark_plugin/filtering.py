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


def _is_front_matter(title: str) -> bool:
    return bool(FRONT_MATTER_RE.match(title.strip()))


def _has_chapter_number(title: str) -> bool:
    return bool(CHAPTER_H1_RE.search(title))


def _is_credential_name(title: str) -> bool:
    """Return True for lines like 'JOHN SMITH, MD, FACS' — author attributions."""
    return bool(CREDENTIAL_RE.search(title))


def _has_descendants(headings: list[Heading], idx: int) -> bool:
    """
    Return True when headings[idx] is followed by one or more entries deeper
    than itself before any entry at the same level or shallower.

    Used by apply_depth_filter to keep an L1 entry whose title doesn't
    match CHAPTER_H1_RE (e.g. Dutton's descriptive chapter titles like
    "Cavernous Sinus") when that entry is the parent of L2/L3/L4 children.
    """
    cur_level = headings[idx].level
    for h in headings[idx + 1:]:
        if h.level > cur_level:
            return True
        if h.level <= cur_level:
            return False
    return False


_CHAPTER_NUM_PREFIX = re.compile(r"^\d+\s+(?:[a-zA-Z]:\s*)?")


def _dedup_key(title: str) -> str:
    return _CHAPTER_NUM_PREFIX.sub("", title).strip().lower()


def apply_depth_filter(headings: list[Heading], depth: int) -> list[Heading]:
    """
    Filter headings to the requested depth.

    Rules:
    - Front matter headings (Preface, Foreword, Dedication, etc.) are always
      kept and promoted to H1, regardless of depth.
    - H1 headings that are not front matter are kept only when they carry a
      recognisable chapter/section number; this suppresses cover-page noise.
    - H2/H3 headings whose title starts with a lowercase letter are dropped —
      these are almost always OCR artefacts (truncated first character).
    - H2 and H3 headings are kept when their level <= depth.
    """
    result: list[Heading] = []
    for i, h in enumerate(headings):
        level = h.level

        if _is_front_matter(h.title):
            result.append(Heading(level=1, title=h.title, page=h.page))
            continue

        # L1 entries without chapter numbers are usually cover-page noise,
        # but keep them when they head a subtree (Dutton's "Cavernous Sinus"
        # etc. each parents 5+ L2/L3 entries).
        if level == 1 and not _has_chapter_number(h.title) and not _has_descendants(headings, i):
            continue

        # OCR artefact: real headings start with an uppercase letter or digit
        if level > 1 and h.title and h.title[0].islower():
            continue

        # Author / credential attribution lines (e.g. "JOHN SMITH, MD, FACS")
        # are suppressed at depth < 3; they appear under Foreword/Preface sections.
        if level > 1 and depth < 3 and _is_credential_name(h.title):
            continue

        if level <= depth:
            result.append(h)

    # Deduplicate headings at the same level with identical titles on adjacent
    # pages.  Medical textbooks often repeat the chapter title on the facing
    # page; keeping both produces doubled bookmarks in the PDF panel.
    # Track the most-recent heading seen at each level (H2 entries between two
    # H1 entries must not prevent the H1 comparison).
    deduped: list[Heading] = []
    last_at_level: dict[int, Heading] = {}
    for h in result:
        prev = last_at_level.get(h.level)
        if (prev is not None
                and _dedup_key(prev.title) == _dedup_key(h.title)
                and h.page - prev.page <= 2):
            continue
        deduped.append(h)
        last_at_level[h.level] = h

    return deduped
