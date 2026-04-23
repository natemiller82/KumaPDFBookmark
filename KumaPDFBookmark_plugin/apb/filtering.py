"""
Depth filtering and deduplication logic extracted from auto-pdf-bookmarks/main.py.
No algorithmic changes — only the config import is adjusted for the apb sub-package.
"""
from __future__ import annotations

import re

from apb.config import CHAPTER_H1_RE, CREDENTIAL_RE, FRONT_MATTER_RE
from apb.extractor import Heading


def _is_front_matter(title: str) -> bool:
    return bool(FRONT_MATTER_RE.match(title.strip()))


def _has_chapter_number(title: str) -> bool:
    return bool(CHAPTER_H1_RE.search(title))


def _is_credential_name(title: str) -> bool:
    return bool(CREDENTIAL_RE.search(title))


# Strips leading chapter number + optional single-letter mnemonic code
# so deduplicated variants compare equal ("3 x: Title" == "3 Title").
_CHAPTER_NUM_PREFIX = re.compile(r"^\d+\s+(?:[a-zA-Z]:\s*)?")


def _dedup_key(title: str) -> str:
    return _CHAPTER_NUM_PREFIX.sub("", title).strip().lower()


def apply_depth_filter(headings: list[Heading], depth: int) -> list[Heading]:
    """
    Filter *headings* to the requested *depth* (1-3).

    Rules (identical to main.py):
    - Front-matter headings are always kept and promoted to H1.
    - H1 headings without a recognisable chapter/section number are dropped
      (suppresses cover-page OCR noise).
    - H2/H3 headings that start with a lowercase letter are dropped (OCR artefacts).
    - H2/H3 credential lines (e.g. "JOHN SMITH, MD") are suppressed at depth < 3.
    - Adjacent same-level headings with the same normalised title within 2 pages
      are deduplicated.
    """
    result: list[Heading] = []
    for h in headings:
        level = h.level

        if _is_front_matter(h.title):
            result.append(Heading(level=1, title=h.title, page=h.page))
            continue

        if level == 1 and not _has_chapter_number(h.title):
            continue

        if level > 1 and h.title and h.title[0].islower():
            continue

        if level > 1 and depth < 3 and _is_credential_name(h.title):
            continue

        if level <= depth:
            result.append(h)

    deduped: list[Heading] = []
    last_at_level: dict[int, Heading] = {}
    for h in result:
        prev = last_at_level.get(h.level)
        if (
            prev is not None
            and _dedup_key(prev.title) == _dedup_key(h.title)
            and h.page - prev.page <= 2
        ):
            continue
        deduped.append(h)
        last_at_level[h.level] = h

    return deduped
