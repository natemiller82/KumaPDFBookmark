"""
Thresholds, regex patterns, and Ollama defaults for auto-pdf-bookmarks.
"""
import re

# --- Font-size clustering thresholds ---
# Ratio of a span's font size to the document median body size.
HEADING_SIZE_RATIO_H1 = 1.35
HEADING_SIZE_RATIO_H2 = 1.15
HEADING_SIZE_RATIO_H3 = 1.05

# Span length limits for heading candidates.
HEADING_MIN_CHARS = 3
HEADING_MAX_CHARS = 200

# Spans whose text appears on more than this fraction of *heading-candidate*
# spans are treated as running headers/footers, not headings.
# Frequency is measured among candidates only (ratio >= H3 threshold) so that
# single-digit chapter numbers like "1" are not suppressed by their thousands
# of body-text occurrences at a different font size.
HEADING_MAX_FREQUENCY_RATIO = 0.15

# --- Heading buffer / merge thresholds ---
# A body-level span flushes the heading accumulator ONLY when it meets both
# of these criteria.  Tiny spans (superscripts, "®", "|", page numbers) are
# silently skipped so they don't split multi-line heading titles.
BODY_FLUSH_MIN_SIZE_RATIO = 0.70   # span.size / median must be >= this
BODY_FLUSH_MIN_LEN = 6             # span text must have >= this many chars

# Same-page, same-font-size heading spans are merged only when the vertical
# gap between them is <= this factor × span.size.  Values near 1.2 reflect
# normal line spacing; 1.7 adds enough headroom for modest leading without
# swallowing an adjacent section heading that has deliberate whitespace before it.
HEADING_MERGE_MAX_LINE_GAP = 1.7

# --- Pattern-match fallback ---
HEADING_PATTERNS = [
    # "Chapter 3", "Chapter 3:", "Chapter 3 –", etc.
    (1, re.compile(
        r"^(Chapter|CHAPTER)\s+(\d+|[IVXLCDM]+)[\s:.\-–—]",
        re.IGNORECASE,
    )),
    # "Section 3.2", "Section A"
    (2, re.compile(
        r"^(Section|SECTION)\s+[\dA-Z][\dA-Z.]*[\s:.\-–—]",
        re.IGNORECASE,
    )),
    # Numbered: "1.", "1.1", "1.1.1" at line start
    (1, re.compile(r"^\d+\.\s+\S")),
    (2, re.compile(r"^\d+\.\d+\s+\S")),
    (3, re.compile(r"^\d+\.\d+\.\d+\s+\S")),
    # All-caps short lines (common OCR chapter titles in medical textbooks)
    (1, re.compile(r"^[A-Z][A-Z\s\-:]{4,60}$")),
]

# --- Depth / hierarchy ---
# Front matter keywords: headings matching this are always promoted to H1
# and are never filtered out by --depth.
# The lookahead (?=\s|:|,|-|$) requires the keyword to be a complete word,
# preventing partial matches like "EDITORIAL NOTES" matching "Editors?".
# "Introduction" is intentionally excluded — it is too common as a per-chapter
# section heading and should not be promoted to H1 document-level front matter.
FRONT_MATTER_RE = re.compile(
    r"^(Preface|Forewords?|Editors?|Contents?|Index|"
    r"Acknowledgements?|Acknowledgments?|Contributors?|Dedication|"
    r"About|Abbreviations?|Glossary|Appendix)(?=\s|:|,|-|$)",
    re.IGNORECASE,
)

# H1 headings should carry a chapter/section number or be front matter.
# Used as a soft filter to suppress random large-font OCR artefacts.
CHAPTER_H1_RE = re.compile(
    r"(Chapter|Section|Part)\s+[\w]"   # Chapter/Section/Part N
    r"|^\d+[\s.\-]"                    # digit at line start (numbered chapters)
    r"|^[IVXLCDM]{2,6}[\s.\-]",       # roman numeral at start; 2+ chars so single
                                       # OCR diagram letters ("x","C","D") don't match
    re.IGNORECASE,
)

# Professional credential suffixes used to detect author-name lines.
# H2/H3 spans that match this pattern are dropped at depth < 3
# (they appear under Foreword/Preface sections, not as real content headings).
CREDENTIAL_RE = re.compile(
    r",\s*(MD|DO|PhD|PHD|MBBS|MBChB|MBBCh|FACS|FRCSC|FRCS|FRCA|"
    r"FCEM|FRCEM|FACEM|FACEP|FACP|FACC|FAHA|FACOG|FAAOS|FAANS|FCCM|FCCP|"
    r"RN|NP|PA|MBA|MPH|MSc|MHA|DrPH|DNP|FICS|FPMRS|FEBU|FEBVS)\b",
    re.IGNORECASE,
)

# --- LLM / Ollama defaults ---
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "mistral-nemo"
OLLAMA_TIMEOUT = 30  # seconds

LLM_SYSTEM_PROMPT = (
    "You are a medical textbook structure classifier. "
    "Given a short line of text extracted from an OCR'd medical PDF, "
    "respond with exactly one word: H1, H2, H3, or BODY. "
    "H1 = major chapter title, H2 = section heading, H3 = subsection heading, "
    "BODY = regular paragraph text or figure captions."
)
