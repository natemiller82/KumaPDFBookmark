"""
PDF outline extraction using PyMuPDF (fitz).

Strategy (in order):
  1. doc.get_toc() — use embedded bookmarks if present.
  2. Font-size clustering — detect H1/H2/H3 by relative font size.
  3. Pattern-match fallback — regex for numbered sections / Chapter/Section headers.
"""
from __future__ import annotations

import statistics
from dataclasses import dataclass
from typing import Callable

import fitz  # PyMuPDF

from config import (
    HEADING_MAX_CHARS,
    HEADING_MAX_FREQUENCY_RATIO,
    HEADING_MIN_CHARS,
    HEADING_PATTERNS,
    HEADING_SIZE_RATIO_H1,
    HEADING_SIZE_RATIO_H2,
    HEADING_SIZE_RATIO_H3,
)


@dataclass
class Heading:
    level: int          # 1, 2, or 3
    title: str
    page: int           # 0-indexed


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
        use_llm:   Optional callable that accepts a list of candidate text
                   strings and returns a list of labels ("H1"/"H2"/"H3"/"BODY").
                   When provided it is used to resolve ambiguous font-size
                   candidates that fall in the H2/H3 gray zone.
        verbose:   Emit progress messages to stdout.

    Returns:
        List of Heading objects in document order.
    """
    doc = fitz.open(pdf_path)
    try:
        # --- Step 1: embedded TOC ---
        toc = doc.get_toc(simple=False)
        if toc:
            if verbose:
                print(f"[extractor] Found embedded TOC with {len(toc)} entries.")
            return _toc_to_headings(toc)

        if verbose:
            print("[extractor] No embedded TOC — running font-size analysis.")

        # --- Step 2: font-size clustering ---
        spans = _collect_spans(doc, verbose)
        headings = _cluster_by_font_size(spans, use_llm=use_llm, verbose=verbose)

        if headings:
            if verbose:
                print(f"[extractor] Font-size clustering found {len(headings)} headings.")
            return headings

        if verbose:
            print("[extractor] Font-size clustering inconclusive — using pattern matching.")

        # --- Step 3: pattern-match fallback ---
        headings = _pattern_match(doc, verbose)
        if verbose:
            print(f"[extractor] Pattern matching found {len(headings)} headings.")
        return headings
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Step 1 helpers
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
# Step 2 helpers
# ---------------------------------------------------------------------------

@dataclass
class _Span:
    text: str
    size: float
    flags: int   # PyMuPDF font flags (bold = bit 4, italic = bit 1)
    page: int


def _collect_spans(doc: fitz.Document, verbose: bool) -> list[_Span]:
    """Collect every non-whitespace span from the document."""
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
                    ))
    if verbose:
        print(f"[extractor] Collected {len(spans)} spans across {len(doc)} pages.")
    return spans


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

    # Count how often each (text, page) combo appears — filter running headers.
    total_spans = len(spans)
    text_freq: dict[str, int] = {}
    for s in spans:
        text_freq[s.text] = text_freq.get(s.text, 0) + 1

    candidates: list[tuple[_Span, int | None]] = []  # (span, tentative_level)
    ambiguous_texts: list[str] = []

    for span in spans:
        ratio = span.size / median_size
        freq_ratio = text_freq[span.text] / total_spans

        if freq_ratio > HEADING_MAX_FREQUENCY_RATIO:
            continue
        if not (HEADING_MIN_CHARS <= len(span.text) <= HEADING_MAX_CHARS):
            continue

        if ratio >= HEADING_SIZE_RATIO_H1:
            candidates.append((span, 1))
        elif ratio >= HEADING_SIZE_RATIO_H2:
            candidates.append((span, 2))
        elif ratio >= HEADING_SIZE_RATIO_H3:
            # Gray zone: bold → H3 immediately; otherwise try LLM.
            is_bold = bool(span.flags & (1 << 4))
            if is_bold or use_llm is None:
                candidates.append((span, 3))
            else:
                candidates.append((span, None))  # defer to LLM
                ambiguous_texts.append(span.text)

    # Resolve ambiguous candidates via LLM if available
    if use_llm and ambiguous_texts:
        if verbose:
            print(f"[extractor] Sending {len(ambiguous_texts)} ambiguous spans to LLM.")
        labels = use_llm(ambiguous_texts)
        label_map = dict(zip(ambiguous_texts, labels))
    else:
        label_map = {}

    headings: list[Heading] = []
    seen: set[tuple[str, int]] = set()
    for span, tentative_level in candidates:
        if tentative_level is None:
            raw_label = label_map.get(span.text, "BODY")
            level = {"H1": 1, "H2": 2, "H3": 3}.get(raw_label)
            if level is None:
                continue
        else:
            level = tentative_level

        key = (span.text, span.page)
        if key in seen:
            continue
        seen.add(key)
        headings.append(Heading(level=level, title=span.text, page=span.page))

    headings.sort(key=lambda h: h.page)
    return headings


# ---------------------------------------------------------------------------
# Step 3 helpers
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
