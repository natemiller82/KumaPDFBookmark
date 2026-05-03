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

import re
import statistics
from dataclasses import dataclass
from typing import Callable

import fitz  # PyMuPDF

from calibre_plugins.kumapdfbookmark.config import (
    BODY_FLUSH_MIN_LEN,
    BODY_FLUSH_MIN_SIZE_RATIO,
    CAPTION_RE,
    EPUB_ARTIFACT_RE,
    FIRST_BODY_HEADING_RE,
    FRONT_MATTER_RE,
    HEADING_MAX_CHARS,
    HEADING_MAX_FREQUENCY_RATIO,
    HEADING_MERGE_MAX_LINE_GAP,
    HEADING_MIN_CHARS,
    HEADING_PATTERNS,
    HEADING_SIZE_RATIO_H1,
    HEADING_SIZE_RATIO_H2,
    HEADING_SIZE_RATIO_H3,
)


# Reused by _is_caption_or_folio: strip a leading number (with optional dot,
# dash, colon, or whitespace separator) so we can decide whether the
# remainder of the string is real heading text.
_LEADING_NUMBER_RE = re.compile(r"^\d+[\s.\-:]*")


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
        page_count = doc.page_count

        # Step 1: embedded TOC
        toc = doc.get_toc(simple=False)
        if toc and _toc_is_valid(toc, len(doc)):
            if verbose:
                print(f"[extractor] Found embedded TOC with {len(toc)} entries.")
            return _post_filter(_toc_to_headings(toc), verbose, page_count)

        if toc and verbose:
            print(f"[extractor] Embedded TOC rejected ({len(toc)} entries) — "
                  "too many entries point to front matter or a single page.")
        elif verbose:
            print("[extractor] No embedded TOC — running font-size analysis.")

        # Step 2: font-size clustering with merge pass
        spans = _collect_spans(doc, verbose)
        headings = _cluster_by_font_size(spans, use_llm=use_llm, verbose=verbose)

        if headings:
            if verbose:
                print(f"[extractor] Font-size clustering found {len(headings)} headings.")
            return _post_filter(headings, verbose, page_count)

        if verbose:
            print("[extractor] Font-size clustering inconclusive — using pattern matching.")

        # Step 3: pattern-match fallback
        headings = _pattern_match(doc, verbose)
        if verbose:
            print(f"[extractor] Pattern matching found {len(headings)} headings.")
        return _post_filter(headings, verbose, page_count)
    finally:
        doc.close()


# ---------------------------------------------------------------------------
# Post-filter — caption/folio rejection + front-matter region anchor filter
# ---------------------------------------------------------------------------

def _is_caption_or_folio(title: str) -> bool:
    """
    Return True for headings that should never be bookmarks regardless of
    where they came from:

      - Figure / table / plate / box captions ("Fig. 1-2", "Table 9-1",
        "346 Fig. 17-12" with leading folio).
      - EPUB conversion artifacts ("OEBPS-14", "OEBPS_6362").
      - Standalone page folios ("100", "101 102").
      - Headings whose text after stripping a leading number contains no
        alphabetic character ("3 -", "12 ...").
      - OCR garbage with no alphanumerics at all ("....", "----").
    """
    s = title.strip()
    if not s:
        return True
    if CAPTION_RE.match(s):
        return True
    if EPUB_ARTIFACT_RE.match(s):
        return True
    if s.isdigit():
        return True
    rest = _LEADING_NUMBER_RE.sub("", s).strip()
    if rest and not re.search(r"[A-Za-z]", rest):
        return True
    if not re.search(r"[A-Za-z0-9]", s):
        return True
    return False


def _is_ocr_garbage(title: str) -> bool:
    """
    Reject titles that are typographically OCR fragments rather than real
    headings.  Catches single-glyph artifacts ("4t", "-h-"), high-punctuation
    noise ("f \\ /' -"), and sub-threshold-content entries (". , ),/t::").

    Does *not* catch real headings even with sparse content (e.g.
    "Embryology", "ATLS.9e_Ch01") because those have >=4 alphabetic chars
    and predominantly-alphabetic composition.

    Universal quality guard — runs alongside _is_caption_or_folio in
    _post_filter regardless of whether the heading came from an embedded
    outline, font-cluster pass, or a future toc_text/repaginate strategy.
    """
    stripped = title.strip()
    if not stripped:
        return True
    alpha_count = sum(1 for c in stripped if c.isalpha())
    if alpha_count < 4:
        return True
    non_alpha_non_space = sum(
        1 for c in stripped if not c.isalpha() and not c.isspace()
    )
    if non_alpha_non_space > alpha_count:
        return True
    return False


def _find_front_matter_end(headings: list["Heading"]) -> int | None:
    """
    Return the 0-indexed page where body content begins.

    The first heading whose title looks like a numbered chapter/section/part
    marker establishes the boundary.  Returns None when no such heading
    exists (descriptive-titled atlases like Dutton), in which case the
    front-matter filter is skipped.
    """
    for h in headings:
        if FIRST_BODY_HEADING_RE.match(h.title.strip()):
            return h.page
    return None


def _post_filter(headings: list["Heading"], verbose: bool, page_count: int) -> list["Heading"]:
    """
    Apply quality / sanity rejections and the front-matter region filter.

    Runs on whatever list extract_outline produced, so embedded-TOC PDFs
    whose publisher-supplied outlines are themselves polluted (caption
    bookmarks, page-folio bookmarks, contributor-list bookmarks, OCR
    fragments, out-of-range page targets) are cleaned up the same way as
    font-derived outlines.

    Args:
        headings:    Raw headings from any extraction path.
        verbose:     Emit progress messages.
        page_count:  Total pages in the source PDF — used by the
                     page-bounds guard to reject entries with invalid page
                     targets (e.g. Dedivitis's "cover" entry at page -1).
    """
    raw_count = len(headings)

    cleaned = [
        h for h in headings
        if 0 <= h.page < page_count
        and not _is_caption_or_folio(h.title)
        and not _is_ocr_garbage(h.title)
    ]
    after_caption_folio = len(cleaned)

    fm_end = _find_front_matter_end(cleaned)
    if fm_end is not None:
        cleaned = [
            h for h in cleaned
            if h.page >= fm_end or FRONT_MATTER_RE.match(h.title.strip())
        ]

    if verbose:
        dropped_cf = raw_count - after_caption_folio
        dropped_fm = after_caption_folio - len(cleaned)
        fm_label = f"page {fm_end + 1}" if fm_end is not None else "not detected"
        print(
            f"[extractor] Post-filter: {raw_count} -> {len(cleaned)} headings "
            f"(captions/folios: -{dropped_cf}, front-matter@{fm_label}: -{dropped_fm})."
        )
    return cleaned


# ---------------------------------------------------------------------------
# Step 1
# ---------------------------------------------------------------------------

def _toc_is_valid(toc: list, total_pages: int) -> bool:
    """Return False when the embedded TOC looks like a scanned TOC-page index.

    Two heuristics — either one failing means the TOC is rejected and we fall
    through to font-size clustering:
      • >30 % of entries share the same destination page (scan artifact).
      • >30 % of entries land on pages 1-20 (front-matter pages, not chapters).
    """
    n = len(toc)
    if n == 0:
        return False

    page_counts: dict[int, int] = {}
    front_count = 0
    for entry in toc:
        p = entry[2]  # 1-indexed page number from doc.get_toc()
        page_counts[p] = page_counts.get(p, 0) + 1
        if p <= 20:
            front_count += 1

    if max(page_counts.values()) / n > 0.30:
        return False
    if front_count / n > 0.30:
        return False
    return True


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
