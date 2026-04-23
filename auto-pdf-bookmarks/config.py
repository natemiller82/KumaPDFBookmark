"""
Thresholds, regex patterns, and Ollama defaults for auto-pdf-bookmarks.
"""
import re

# --- Font-size clustering thresholds ---
# Minimum ratio of a line's font size to the median body font size to be
# considered a heading candidate.
HEADING_SIZE_RATIO_H1 = 1.35
HEADING_SIZE_RATIO_H2 = 1.15
HEADING_SIZE_RATIO_H3 = 1.05

# Minimum number of characters for a heading candidate (filters noise).
HEADING_MIN_CHARS = 3
HEADING_MAX_CHARS = 200

# A heading line must appear at least this many times fewer than body lines
# (prevents repeated running headers from being treated as structure).
HEADING_MAX_FREQUENCY_RATIO = 0.15

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

# --- LLM / Ollama defaults ---
OLLAMA_BASE_URL = "http://localhost:11434"
OLLAMA_DEFAULT_MODEL = "mistral-nemo"
OLLAMA_TIMEOUT = 30  # seconds

# System prompt sent to the LLM classifier
LLM_SYSTEM_PROMPT = (
    "You are a medical textbook structure classifier. "
    "Given a short line of text extracted from an OCR'd medical PDF, "
    "respond with exactly one word: H1, H2, H3, or BODY. "
    "H1 = major chapter title, H2 = section heading, H3 = subsection heading, "
    "BODY = regular paragraph text or figure captions."
)
