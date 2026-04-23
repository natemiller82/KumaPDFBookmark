# KumaPDFBookmark

Automatically detects and embeds a navigable bookmark tree in PDF files. Built for OCR'd medical textbooks that ship without a table of contents, but works on any PDF.

## What it does

Opens a PDF, infers its structure (chapters, sections, subsections), and writes a new PDF with a proper bookmark panel — the kind you click in your PDF reader to jump directly to a section. The original file is never modified.

Detection runs in three stages, stopping as soon as one succeeds:

1. **Embedded TOC** — if the PDF already has bookmarks, they are preserved and re-written as-is.
2. **Font-size clustering** — every text span is collected and compared to the median body font size. Spans that are significantly larger are classified as H1, H2, or H3 headings. Spans that repeat on more than 15% of pages (running headers/footers) are ignored.
3. **Pattern-match fallback** — if font analysis yields nothing (e.g. a flat-font OCR scan), regex patterns fire on the raw text: `Chapter N`, `Section N.N`, decimal-numbered headings (`1.`, `1.1`, `1.1.1`), and ALL-CAPS short lines common in medical textbook chapter pages.

An optional Ollama integration can classify spans that fall in a size gray zone (slightly larger than body but not bold) by asking a local LLM to label each one `H1 / H2 / H3 / BODY`.

## Requirements

- Python 3.10+
- [PyMuPDF](https://pymupdf.readthedocs.io/) (`fitz`) >= 1.24
- [pypdf](https://pypdf.readthedocs.io/) >= 4.2
- [Ollama](https://ollama.com/) running locally — **optional**, only needed with `--llm`

## Installation

```bash
git clone https://github.com/natemiller82/KumaPDFBookmark.git
cd KumaPDFBookmark/auto-pdf-bookmarks
pip install -r requirements.txt
```

No virtual environment is required, but one is recommended:

```bash
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

pip install -r requirements.txt
```

## Basic usage

```bash
python main.py INPUT.pdf OUTPUT.pdf
```

`INPUT.pdf` is read-only. `OUTPUT.pdf` is the new file with bookmarks embedded.

## CLI reference

```
python main.py [options] INPUT OUTPUT
```

| Argument | Description |
|---|---|
| `INPUT` | Path to the source PDF (required) |
| `OUTPUT` | Path for the output PDF with bookmarks (required) |
| `--llm` | Enable Ollama to resolve ambiguous heading candidates |
| `--model NAME` | Ollama model to use (default: `mistral-nemo`) |
| `--ollama-url URL` | Ollama base URL (default: `http://localhost:11434`) |
| `--verbose` / `-v` | Print per-span and per-bookmark progress |

## How the detection pipeline works

### Stage 1 — Embedded TOC

PyMuPDF's `doc.get_toc()` is called first. If the document already carries bookmark data, the pipeline stops here and those entries are passed directly to the writer. Levels deeper than 3 are clamped to H3.

### Stage 2 — Font-size clustering

All text spans are extracted via PyMuPDF's `page.get_text("dict")`. For each span the **ratio** of its font size to the document's median font size is computed:

| Ratio threshold | Assigned level |
|---|---|
| >= 1.35 | H1 |
| >= 1.15 | H2 |
| >= 1.05 (bold) | H3 |
| >= 1.05 (not bold, LLM available) | sent to LLM for classification |
| >= 1.05 (not bold, no LLM) | H3 |

Two filters run before the ratio check:

- **Frequency filter** — a span whose text appears on more than 15% of all pages is treated as a running header or footer and skipped.
- **Length filter** — spans shorter than 3 or longer than 200 characters are ignored.

If the stage produces at least one heading, the pipeline stops.

### Stage 3 — Pattern-match fallback

Plain text is extracted from each page and matched line-by-line against a set of regex patterns (first match wins):

| Pattern | Level | Examples |
|---|---|---|
| `^(Chapter\|CHAPTER)\s+(\d+\|[IVXLCDM]+)[\s:.\-]` | H1 | `Chapter 3:`, `CHAPTER IV` |
| `^(Section\|SECTION)\s+[\dA-Z][\dA-Z.]*[\s:.\-]` | H2 | `Section 2.1 —` |
| `^\d+\.\s+\S` | H1 | `1. Introduction` |
| `^\d+\.\d+\s+\S` | H2 | `1.1 Overview` |
| `^\d+\.\d+\.\d+\s+\S` | H3 | `1.1.1 Background` |
| `^[A-Z][A-Z\s\-:]{4,60}$` | H1 | `CARDIOVASCULAR PHYSIOLOGY` |

### Optional LLM classification (Ollama)

When `--llm` is passed, the extractor collects spans in the H3 size band that are not bold (the most ambiguous cases) and sends them one-by-one to the configured Ollama model. The system prompt instructs the model to respond with exactly one token: `H1`, `H2`, `H3`, or `BODY`. Any response that does not match is treated as `BODY`. If Ollama is unreachable at startup, the flag is silently ignored and font-size rules apply instead.

### Writing bookmarks

`writer.py` uses pypdf to copy all pages and metadata from the source PDF into a new file, then inserts the bookmark tree using `PdfWriter.add_outline_item()`. Parent–child nesting (up to 3 levels) is tracked so the bookmark panel in your PDF reader shows the correct hierarchy.

## Examples

**Simplest case — run and check output:**
```bash
python main.py Gray_Anatomy.pdf Gray_Anatomy_bookmarked.pdf
```

**See exactly what was detected:**
```bash
python main.py Gray_Anatomy.pdf Gray_Anatomy_bookmarked.pdf --verbose
```

**Enable LLM for a flat-font OCR scan where heading sizes are ambiguous:**
```bash
python main.py Robbins_Pathology_OCR.pdf Robbins_Pathology_bookmarked.pdf --llm --verbose
```

**Use a different local model:**
```bash
python main.py Robbins_Pathology_OCR.pdf Robbins_Pathology_bookmarked.pdf --llm --model llama3.2
```

**Point at an Ollama instance running on another machine:**
```bash
python main.py input.pdf output.pdf --llm --ollama-url http://192.168.1.50:11434
```

**Generate the test fixture and run the pipeline against it:**
```bash
python make_test_pdf.py
python main.py test_medical.pdf test_medical_bookmarked.pdf --verbose
```

## Tuning

All thresholds and regex patterns live in `config.py`. Edit that file to adjust font-size ratios, the frequency filter cutoff, or the heading patterns without touching any logic code.

```python
# config.py
HEADING_SIZE_RATIO_H1 = 1.35   # raise if body text is being picked up as H1
HEADING_SIZE_RATIO_H2 = 1.15
HEADING_SIZE_RATIO_H3 = 1.05
HEADING_MAX_FREQUENCY_RATIO = 0.15  # lower to filter more running headers
```

## Project structure

```
auto-pdf-bookmarks/
├── main.py            # CLI entry point
├── extractor.py       # Three-stage outline detection (PyMuPDF)
├── writer.py          # Bookmark writer (pypdf)
├── llm_classifier.py  # Optional Ollama integration
├── config.py          # Thresholds, patterns, defaults
├── requirements.txt
└── make_test_pdf.py   # Test fixture generator
```
