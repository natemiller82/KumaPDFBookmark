"""
PDF outline extraction using PyMuPDF (fitz).

Strategy (in order):
  1. doc.get_toc() — use embedded bookmarks if present.
  2. Font-size clustering — classify every span as H1/H2/H3 or body, then
     merge consecutive same-level heading spans with no substantial body text
     between them (fixes multi-line OCR titles).
  3. Pattern-match fallback — regex for numbered sections / Chapter/Section
     headers (fires when font analysis yields nothing).
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Callable

import fitz  # PyMuPDF

from calibre_plugins.kumapdfbookmark.config import (
    BODY_FLUSH_MIN_LEN,
    BODY_FLUSH_MIN_SIZE_RATIO,
    HEADING_MAX_CHARS,
    HEADING_MAX_FREQUENCY_RATIO,
    HEADING_MERGE_MAX_LINE_GAP,
    HEADING_MIN_CHARS,
    HEADING_PATTERNS,
    HEADING_SIZE_RATIO_H1,
    HEADING_SIZE_RATIO_H2,
    HEADING_SIZE_RATIO_H3,
)


@dataclass
class Heading:
    level: int   # 1, 2, or 3
    title: str
    page: int    # 0-indexed


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def extract_outline(
    pdf_path: str,
    use_llm: Callable[[list[str]], list[str]] | None = None,
    verbose: bool = False,
) -> list[Heading]:
    """
    Extract a structured outline from *pdf_path*.

    Args:
        pdf_path:  Path to the source PDF.
        use_llm:   Optional callable — accepts a list of candidate strings,
                   returns a list of labels ("H1"/"H2"/"H3"/"BODY").
                   Used to resolve spans in the H3 size-band that are not bold.
        verbose:   Emit progress messages to stdout.

    Returns:
        List of Heading objects in document order.
    """
    doc = fitz.open(pdf_path)
    try:
        # Step 1: embedded TOC
        toc = doc.get_toc(simple=False)
        if toc:
            if verbose:
                print(f"[extractor] Found embedded TOC with {len(toc)} entries.")
            return _toc_to_headings(toc)

        if verbose:
            print("[extractor] No embedded TOC — running font-size analysis.")

        # Step 2: font-size clustering with merge pass
        spans = _collect_spans(doc, verbose)
        headings = _cluster_by_font_size(spans, use_llm=use_llm, verbose=verbose)

        if headings:
            if verbose:
                print(f"[extractor] Font-size clustering found {len(headings)} headings.")
            return headings

        if verbose:
            print("[extractor] Font-size clustering inconclusive — using pattern matching.")

        # Step 3: pattern-match fallback
        headings = _pattern_match(doc, verbose)
        if verbose:
            print(f"[extractor] Pattern matching found {len(headings)} headings.")
        return headings
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Step 1
# ---------------------------------------------------------------------------

def _toc_to_headings(toc: list) -> list[Heading]:
    headings = []
    for entry in toc:
        level, title, page = entry[0], entry[1], entry[2]
        if level > 3:
            level = 3
        headings.append(Heading(level=level, title=title.strip(), page=max(0, page - 1)))
    return headings


# ---------------------------------------------------------------------------
# Step 2 — span collection
# ---------------------------------------------------------------------------

@dataclass
class _Span:
    text: str
    size: float
    flags: int   # PyMuPDF font flags (bold = bit 4)
    page: int
    y: float     # top of bounding box — used for same-page merge decisions


def _collect_spans(doc: fitz.Document, verbose: bool) -> list[_Span]:
    """Return every non-whitespace span from the document in reading order."""
    spans: list[_Span] = []
    for page_num, page in enumerate(doc):
        blocks = page.get_text("dict", flags=fitz.TEXT_PRESERVE_WHITESPACE)["blocks"]
        for block in blocks:
            if block.get("type") != 0:
                continue
            for line in block.get("lines", []):
                for span in line.get("spans", []):
                    text = span["text"].strip()
                    if not text:
                        continue
                    spans.append(_Span(
                        text=text,
                        size=round(span["size"], 1),
                        flags=span.get("flags", 0),
                        page=page_num,
                        y=round(span["bbox"][1], 1),
                    ))
    if verbose:
        print(f"[extractor] Collected {len(spans)} spans across {len(doc)} pages.")
    return spans


# ---------------------------------------------------------------------------
# Step 2 — classification + merge
# ---------------------------------------------------------------------------

_AMBIGUOUS = -1  # sentinel: needs LLM classification


def _cluster_by_font_size(
    spans: list[_Span],
    use_llm: Callable | None,
    verbose: bool,
) -> list[Heading]:
    if not spans:
        return []

    sizes = [s.size for s in spans]
    try:
        median_size = statistics.median(sizes)
    except statistics.StatisticsError:
        return []
    if median_size == 0:
        return []

    # Frequency is measured among heading-candidate spans only (ratio >= H3).
    # Counting against all spans would suppress single-digit chapter numbers
    # like "1" or "2" that appear thousands of times in body text at a
    # completely different font size.
    candidates_for_freq = [
        s for s in spans
        if s.size / median_size >= HEADING_SIZE_RATIO_H3
    ]
    total_for_freq = max(len(candidates_for_freq), 1)
    text_freq: dict[str, int] = {}
    for s in candidates_for_freq:
        text_freq[s.text] = text_freq.get(s.text, 0) + 1

    # --- Classify every span ---
    # level: 1/2/3 = heading, _AMBIGUOUS = needs LLM, None = body
    classified: list[tuple[_Span, int | None]] = []
    ambiguous_spans: list[_Span] = []

    for span in spans:
        ratio = span.size / median_size
        freq_ratio = text_freq.get(span.text, 0) / total_for_freq

        # Frequency filter → body
        if freq_ratio > HEADING_MAX_FREQUENCY_RATIO:
            classified.append((span, None))
            continue

        # Length filter — waived for H1-sized spans so single-digit chapter
        # numbers ("1", "2") are not silently dropped before classification.
        too_long = len(span.text) > HEADING_MAX_CHARS
        too_short = len(span.text) < HEADING_MIN_CHARS
        if too_long or (too_short and ratio < HEADING_SIZE_RATIO_H1):
            classified.append((span, None))
            continue

        if ratio >= HEADING_SIZE_RATIO_H1:
            classified.append((span, 1))
        elif ratio >= HEADING_SIZE_RATIO_H2:
            classified.append((span, 2))
        elif ratio >= HEADING_SIZE_RATIO_H3:
            is_bold = bool(span.flags & (1 << 4))
            if is_bold or use_llm is None:
                classified.append((span, 3))
            else:
                classified.append((span, _AMBIGUOUS))
                ambiguous_spans.append(span)
        else:
            classified.append((span, None))

    # --- Resolve LLM ambiguous spans ---
    if use_llm and ambiguous_spans:
        if verbose:
            print(f"[extractor] Sending {len(ambiguous_spans)} ambiguous spans to LLM.")
        labels = use_llm([s.text for s in ambiguous_spans])
        label_map = {s.text: l for s, l in zip(ambiguous_spans, labels)}
        resolved: list[tuple[_Span, int | None]] = []
        for span, level in classified:
            if level == _AMBIGUOUS:
                raw = label_map.get(span.text, "BODY")
                resolved.append((span, {"H1": 1, "H2": 2, "H3": 3}.get(raw)))
            else:
                resolved.append((span, level))
        classified = resolved
    elif ambiguous_spans:
        # No LLM — default ambiguous to H3
        classified = [(s, 3 if l == _AMBIGUOUS else l) for s, l in classified]

    # --- Merge consecutive same-level heading spans ---
    return _merge_consecutive_headings(classified, median_size, verbose)


def _merge_consecutive_headings(
    classified: list[tuple[_Span, int | None]],
    median_size: float,
    verbose: bool,
) -> list[Heading]:
    """
    Walk spans in document order and merge consecutive heading spans of the
    same level when they appear to be continuation lines of one title.

    Merge rules for same-level heading spans:
      • Different font sizes on the same page → always merge (e.g. section
        number "SECTION I" at 32pt followed by title text at 34pt).
      • Same font size, same page → merge only when the vertical gap between
        spans is <= HEADING_MERGE_MAX_LINE_GAP × span.size.  This separates
        adjacent distinct section headings (which have intentional whitespace
        before them) from wrapped title lines (which are spaced at normal
        line height).
      • Different pages → merge (body text on the intervening page would have
        already flushed the buffer if the headings were truly unrelated).

    Body-text flush rules:
      A body-level span flushes the accumulator ONLY when it is substantial
      (size >= BODY_FLUSH_MIN_SIZE_RATIO × median AND len >= BODY_FLUSH_MIN_LEN).
      Tiny spans — superscripts, "®", "|", page-number digits — are skipped
      so they cannot split a multi-line heading.
    """
    flush_min_size = BODY_FLUSH_MIN_SIZE_RATIO * median_size

    headings: list[Heading] = []
    buf_level: int | None = None
    buf_texts: list[str] = []
    buf_page: int | None = None
    buf_last_y: float | None = None
    buf_last_size: float | None = None

    def _flush() -> None:
        nonlocal buf_level, buf_texts, buf_page, buf_last_y, buf_last_size
        if buf_texts:
            headings.append(Heading(
                level=buf_level,
                title=" ".join(buf_texts),
                page=buf_page,
            ))
        buf_level = None
        buf_texts = []
        buf_page = None
        buf_last_y = None
        buf_last_size = None

    for span, level in classified:
        if level is None:
            is_substantial = (
                span.size >= flush_min_size
                and len(span.text) >= BODY_FLUSH_MIN_LEN
            )
            if is_substantial:
                _flush()
        else:
            if not buf_texts:
                buf_level = level
                buf_texts = [span.text]
                buf_page = span.page
                buf_last_y = span.y
                buf_last_size = span.size
            elif level != buf_level:
                _flush()
                buf_level = level
                buf_texts = [span.text]
                buf_page = span.page
                buf_last_y = span.y
                buf_last_size = span.size
            else:
                # Same level — decide merge vs. new heading
                if span.page != buf_page:
                    should_merge = True  # cross-page: body text would flush if separate
                elif abs(span.size - buf_last_size) > 0.5:
                    should_merge = True  # different sizes = section number + title
                else:
                    y_gap = span.y - buf_last_y
                    should_merge = y_gap <= HEADING_MERGE_MAX_LINE_GAP * span.size

                if should_merge:
                    buf_texts.append(span.text)
                    buf_last_y = span.y
                    buf_last_size = span.size
                else:
                    _flush()
                    buf_level = level
                    buf_texts = [span.text]
                    buf_page = span.page
                    buf_last_y = span.y
                    buf_last_size = span.size

    _flush()
    return headings


# ---------------------------------------------------------------------------
# Step 3 — pattern-match fallback
# ---------------------------------------------------------------------------

def _pattern_match(doc: fitz.Document, verbose: bool) -> list[Heading]:
    headings: list[Heading] = []
    seen: set[tuple[str, int]] = set()

    for page_num, page in enumerate(doc):
        text = page.get_text("text")
        for line in text.splitlines():
            line = line.strip()
            if not (HEADING_MIN_CHARS <= len(line) <= HEADING_MAX_CHARS):
                continue
            for level, pattern in HEADING_PATTERNS:
                if pattern.match(line):
                    key = (line, page_num)
                    if key not in seen:
                        seen.add(key)
                        headings.append(Heading(level=level, title=line, page=page_num))
                    break  # first matching pattern wins

    headings.sort(key=lambda h: h.page)
    return headings
