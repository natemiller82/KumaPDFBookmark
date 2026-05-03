"""
Depth filtering and deduplication — logic extracted from auto-pdf-bookmarks/main.py.
Flat import version: config.py and extractor.py live at the same ZIP root level.
"""
from __future__ import annotations

import re

from calibre_plugins.kumapdfbookmark.config import CHAPTER_H1_RE, CREDENTIAL_RE, FRONT_MATTER_RE
from calibre_plugins.kumapdfbookmark.extractor import Heading


def _is_front_matter(title: str) -> bool:
    return bool(FRONT_MATTER_RE.match(title.strip()))


def _has_chapter_number(title: str) -> bool:
    return bool(CHAPTER_H1_RE.search(title))


def _is_credential_name(title: str) -> bool:
    return bool(CREDENTIAL_RE.search(title))


_CHAPTER_NUM_PREFIX = re.compile(r"^\d+\s+(?:[a-zA-Z]:\s*)?")


def _dedup_key(title: str) -> str:
    return _CHAPTER_NUM_PREFIX.sub("", title).strip().lower()


def apply_depth_filter(headings: list[Heading], depth: int) -> list[Heading]:
    """
    Filter headings to the requested depth (1-3).
    See auto-pdf-bookmarks/main.py for full rule documentation.
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
