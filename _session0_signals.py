"""
Session-0 signal classifier — runs cheap detector probes against every
fixture and writes a per-fixture signal record.  Reuses the post-filter
logic from extractor.py for pollution estimates and the TOC-page
heuristic from validator.py for printed-TOC detection.

Output: C:\\Users\\MillerFam\\signal_classification.txt
"""
from __future__ import annotations
import os
import re
import sys
from collections import Counter

import fitz  # PyMuPDF

# Make the CLI engine importable so we reuse its filters / regexes.
HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(HERE, "auto-pdf-bookmarks"))

from extractor import _is_caption_or_folio  # type: ignore  # noqa: E402
from validator import _looks_like_toc_page  # type: ignore  # noqa: E402


FIXTURE_DIR = HERE
FIXTURES = [
    ("Davis_Otoplasty",      "Otoplasty_ Aesthetic and Recons - Jack Davis.pdf"),
    ("ATLS_11_Course",       "ATLS 11th Edition Course Manua - American College Of Surgeons. C.pdf"),
    ("ATLS_10_Faculty",      "ATLS 10th Edition Faculty ManualATLS 10th - American College Of Surgeons. Committee On.pdf"),
    ("ATLS_Legacy_2017",     "Advanced Trauma Life Support_ S - American College Of Surgeons. C.pdf"),
    ("Janfaza_HeadAnatomy",  "Surgical Anatomy of the Head an - Parviz Janfaza.pdf"),
    ("Dutton_Atlas",         "Atlas of Clinical and Surgical - Jonathan J. Dutton.pdf"),
    ("Cheney_FacialSurgery", "Facial Surgery_ Plastic and Reconstructive - Mack L. Cheney, M. D_.pdf"),
    ("Grabb_Flaps",          "Grabb's Encyclopedia of Flaps_ - Berish Strauch.pdf"),
    ("Gubisch_Rhinoplasty",  "Mastering Advanced Rhinoplasty - Wolfgang Gubisch.pdf"),
    ("Kaufman_FacialRecon",  "Practical Facial Reconstruction - Dr. Andrew Kaufman M. D_.pdf"),
    ("Dedivitis_Laryngeal",  "Laryngeal Cancer_ Clinical Case - Rogerio A. Dedivitis.pdf"),
]

# Cap detector budget on huge PDFs.
TOC_SCAN_PAGES   = 30
HEADER_SAMPLE_PAGES = 100      # sample N body pages for running-header detection
HEADER_TOP_REGION_PT = 90      # top 90pt of each page = header zone
CHAPTER_HEADER_RE = re.compile(r"^\s*CHAPTER\s+\d+\b", re.IGNORECASE)
TITLE_PAGE_MAX_CHARS = 200


def _sample_pages(doc: fitz.Document, k: int) -> list[int]:
    """Return up to k evenly-spaced page indices, plus the first page."""
    n = doc.page_count
    if n <= k:
        return list(range(n))
    step = max(1, n // k)
    return list(range(0, n, step))[:k]


def probe(name: str, fname: str) -> dict:
    path = os.path.join(FIXTURE_DIR, fname)
    rec: dict = {"name": name, "file": fname, "errors": []}
    if not os.path.isfile(path):
        rec["errors"].append("file not found")
        return rec
    rec["size_mb"] = round(os.path.getsize(path) / 1024 / 1024, 1)

    try:
        doc = fitz.open(path)
    except Exception as e:
        rec["errors"].append(f"open failed: {e}")
        return rec

    try:
        rec["pages"] = doc.page_count

        # --- Outline signals (1-4) ---
        try:
            toc = doc.get_toc(simple=False)
        except Exception as e:
            toc = []
            rec["errors"].append(f"get_toc: {e}")

        rec["has_outline"]            = len(toc) > 0
        rec["outline_entry_count"]    = len(toc)
        rec["outline_depth_hist"]     = dict(sorted(Counter(e[0] for e in toc).items()))
        rec["outline_is_flat"]        = len(toc) > 5 and set(rec["outline_depth_hist"].keys()) == {1}

        # Pollution estimate via shared post-filter logic
        if toc:
            polluted = sum(1 for e in toc if _is_caption_or_folio(e[1] or ""))
            rec["outline_pollution_pct"] = round(100 * polluted / len(toc), 1)
        else:
            rec["outline_pollution_pct"] = 0.0

        # Cheap "broken page targets" check — count entries pointing to page <= 1
        if toc:
            single_page_targets = sum(1 for e in toc if e[2] <= 1)
            rec["outline_broken_page_pct"] = round(100 * single_page_targets / len(toc), 1)
        else:
            rec["outline_broken_page_pct"] = 0.0

        # --- TOC-page signals (5-6) ---
        toc_pages_with_links: list[int] = []
        toc_pages_without_links: list[int] = []
        scan_n = min(TOC_SCAN_PAGES, doc.page_count)
        for pno in range(scan_n):
            try:
                p = doc.load_page(pno)
                links = p.get_links()
                inbound = sum(
                    1 for l in links
                    if l.get("kind") in (fitz.LINK_GOTO, 1) or "page" in l
                )
                text = p.get_text("text")
                looks_toc = _looks_like_toc_page(text)
                if inbound >= 5:
                    toc_pages_with_links.append(pno + 1)
                elif looks_toc:
                    toc_pages_without_links.append(pno + 1)
            except Exception:
                continue
        rec["toc_pages_with_links"] = toc_pages_with_links
        rec["toc_pages_without_links"] = toc_pages_without_links

        # --- Body structure signals (7-8) ---
        chapter_title_pages: list[int] = []
        chapter_header_pages: list[int] = []
        sampled = _sample_pages(doc, HEADER_SAMPLE_PAGES)
        for pno in sampled:
            try:
                p = doc.load_page(pno)
                text = p.get_text("text")
                # Source 7: chapter title page = sparse text
                if 0 < len(text.strip()) < TITLE_PAGE_MAX_CHARS:
                    chapter_title_pages.append(pno + 1)
                # Source 8: top-of-page header = "CHAPTER N"
                page_h = p.rect.height
                clip = fitz.Rect(0, 0, p.rect.width, min(HEADER_TOP_REGION_PT, page_h))
                top_text = p.get_textbox(clip).strip()
                if top_text and CHAPTER_HEADER_RE.match(top_text):
                    chapter_header_pages.append(pno + 1)
            except Exception:
                continue
        rec["chapter_title_pages_sample"]   = chapter_title_pages
        rec["chapter_header_pages_sample"]  = chapter_header_pages
        rec["sample_size"]                  = len(sampled)

        # --- Source 10: structure tree ---
        # PyMuPDF doesn't expose StructTreeRoot directly; the practical
        # detector is whether the catalog has a /StructTreeRoot key.
        try:
            cat = doc.pdf_catalog()
            cat_str = doc.xref_object(cat) if cat else ""
            rec["has_struct_tree"] = "/StructTreeRoot" in (cat_str or "")
        except Exception:
            rec["has_struct_tree"] = False

    finally:
        doc.close()

    return rec


def classify_dominant(rec: dict) -> tuple[int, str]:
    """Pick the single best-fit signal pattern from BOOKMARK_SOURCES.md."""
    if "errors" in rec and any("open failed" in e for e in rec["errors"]):
        return (12, "no structural signals (open failed)")

    # Signal 11: page-shifted outline (most entries at page <= 1)
    if rec.get("has_outline") and rec["outline_entry_count"] >= 5 \
            and rec.get("outline_broken_page_pct", 0) > 50:
        return (11, "outline present but page targets broken — repaginated")

    # Signal 2: polluted outline
    if rec.get("has_outline") and rec.get("outline_pollution_pct", 0) > 20:
        return (2, "embedded outline, polluted")

    # Signal 3: flat outline at L1 only with significant entry count
    if rec.get("outline_is_flat"):
        return (3, "embedded outline, flat (single depth)")

    # Signal 1: complete outline
    if rec.get("has_outline") and rec["outline_entry_count"] >= 5 \
            and len(rec["outline_depth_hist"]) >= 1:
        return (1, "embedded outline, complete")

    # Outline present but trivial (< 5 entries)
    if rec.get("has_outline") and rec["outline_entry_count"] < 5:
        # fall through to other signals
        pass

    # Signal 5/6: TOC page
    if rec.get("toc_pages_with_links"):
        return (5, "TOC page with hyperlinks")
    if rec.get("toc_pages_without_links"):
        return (6, "TOC page without hyperlinks")

    # Signal 8: running CHAPTER N headers
    if len(rec.get("chapter_header_pages_sample", [])) >= 3:
        return (8, "running CHAPTER N page headers")

    # Signal 7: chapter title pages (sparse)
    if len(rec.get("chapter_title_pages_sample", [])) >= 3:
        return (7, "distinctive chapter title pages")

    # Signal 9: font cluster fallback
    if rec.get("pages", 0) > 0:
        return (9, "inline numbered section headings (font cluster)")

    return (12, "no structural signals")


def fmt_rec(rec: dict) -> str:
    lines = [
        f"=== {rec['name']} ===",
        f"  file: {rec['file']}",
        f"  size_mb: {rec.get('size_mb', '?')}  pages: {rec.get('pages', '?')}",
    ]
    if rec.get("errors"):
        lines.append(f"  errors: {rec['errors']}")
    lines += [
        f"  has_outline:            {rec.get('has_outline')}",
        f"  outline_entry_count:    {rec.get('outline_entry_count')}",
        f"  outline_depth_hist:     {rec.get('outline_depth_hist')}",
        f"  outline_is_flat:        {rec.get('outline_is_flat')}",
        f"  outline_pollution_pct:  {rec.get('outline_pollution_pct')}%",
        f"  outline_broken_page_pct:{rec.get('outline_broken_page_pct')}% (entries at page <= 1)",
        f"  toc_pages_with_links:   {rec.get('toc_pages_with_links')}",
        f"  toc_pages_without_links:{rec.get('toc_pages_without_links')}",
        f"  chapter_title_pages:    {len(rec.get('chapter_title_pages_sample', []))} of {rec.get('sample_size')} sampled "
        f"(eg {rec.get('chapter_title_pages_sample', [])[:6]})",
        f"  chapter_header_pages:   {len(rec.get('chapter_header_pages_sample', []))} of {rec.get('sample_size')} sampled "
        f"(eg {rec.get('chapter_header_pages_sample', [])[:6]})",
        f"  has_struct_tree:        {rec.get('has_struct_tree')}",
    ]
    pat_n, pat_desc = classify_dominant(rec)
    lines.append(f"  --> dominant pattern: Source {pat_n} ({pat_desc})")
    return "\n".join(lines) + "\n"


def main() -> int:
    out_path = r"C:\Users\MillerFam\signal_classification.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"Signal classification — {len(FIXTURES)} fixtures\n")
        f.write("=" * 70 + "\n\n")
        for name, fname in FIXTURES:
            print(f"probing {name}...", flush=True)
            rec = probe(name, fname)
            f.write(fmt_rec(rec) + "\n")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
