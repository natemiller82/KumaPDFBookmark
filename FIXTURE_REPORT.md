# Fixture Report — Bookmark Source Patterns

**Generated:** 2026-05-03
**Source PDFs:** 11
**Reference taxonomy:** `BOOKMARK_SOURCES.md`
**Detection method:** `_session0_signals.py` (read-only probes, no extraction)

This document classifies every source PDF in the project against the 12 signal
patterns from `BOOKMARK_SOURCES.md` §2, identifies the dominant pattern per
fixture, and flags edge cases worth surfacing before Phase A implementation.

---

## Summary table

| # | Fixture | Pages | Embedded TOC | Dominant pattern | Recommended strategy |
|---|---------|------:|--------------|------------------|----------------------|
| 1  | `Davis_Otoplasty`      |  149 | 0 entries                          | **Source 6** (printed TOC without hyperlinks) + **Source 9** (font-cluster fallback) | `toc_text` (Phase D) — interim: `font_cluster` + OCR garbage guard |
| 2  | `ATLS_11_Course`       |  377 | 727 entries, depth 1-2, 0.8% noise | **Source 1** (complete outline)          | `outline_only` |
| 3  | `ATLS_10_Faculty`      |  781 | 1 entry ("Contents")               | **Source 5** (TOC pages with hyperlinks) | `toc_links` |
| 4  | `ATLS_Legacy_2017`     |  421 | 31 entries, identifier-style       | **Source 1** (complete outline)          | `outline_only` |
| 5  | `Janfaza_HeadAnatomy`  |  932 | 25 entries, **all → page 1**       | **Source 11** (page targets broken)      | `outline_repaginate` |
| 6  | `Dutton_Atlas`         |  253 | 168 entries, depth 1-4 (clean)     | **Source 1** (complete outline)          | `outline_only` * |
| 7  | `Cheney_FacialSurgery` | 1165 | 2615 entries, **78.5% noise**      | **Source 2** (polluted outline)          | `outline_only` + post-filter |
| 8  | `Grabb_Flaps`          | 1215 | 232 entries, **all at L1**         | **Source 3b** (flat-by-design — encyclopedia) | `outline_only` (flat is intentional, see notes) |
| 9  | `Gubisch_Rhinoplasty`  |  946 | 316 entries, depth 1-5 (deep)      | **Source 1** (complete outline)          | `outline_only` |
| 10 | `Kaufman_FacialRecon`  |  521 | 93 entries, depth 1-3              | **Source 1** (complete outline)          | `outline_only` |
| 11 | `Dedivitis_Laryngeal`  |  189 | 33 entries, **slug-style titles**  | **Source 3b** (flat-by-design — case-series) + **Source 13** (slug titles) | `outline_only` + `title_rewrite` (see notes) |

\* See per-fixture notes for `Dutton_Atlas` — the source outline is hierarchical
but our current `apply_depth_filter` drops the chapter-level L1 entries because
their titles ("Cavernous Sinus", "Osteology of the Orbit") lack chapter numbers.
The downstream "flat" appearance is filter-induced, not a source defect. Phase B
should consider relaxing the `CHAPTER_H1_RE` requirement for L1 entries that
sit above L2/L3 children.

### Distribution

- **Source 1** (complete outline): 6 fixtures (ATLS_11, ATLS_Legacy, Dutton, Gubisch, Kaufman) + Cheney technically before pollution
- **Source 2** (polluted outline): 1 fixture (Cheney)
- **Source 3b** (flat-by-design): 2 fixtures (Grabb — encyclopedia, Dedivitis — case-series)
- **Source 13** (title-quality issue): 1 fixture (Dedivitis — slug titles, secondary signal alongside 3b)
- **Source 5** (TOC with hyperlinks): 1 fixture (ATLS_10)
- **Source 9** (font cluster as interim fallback): 1 fixture (Davis — true
  primary is Source 6, awaiting Phase D `toc_text`)
- **Source 11** (broken page targets): 1 fixture (Janfaza)

Source 3a (flat-by-defect) and patterns 4, 6, 7, 8, 10, 12 not dominant for
any fixture, though some appear as secondary signals — see §"Patterns
observed" below.

---

## Per-fixture details

### 1. Davis_Otoplasty

- **File:** `Otoplasty_ Aesthetic and Recons - Jack Davis.pdf`
- **Size:** 9.3 MB · **Pages:** 149
- **Embedded outline:** none
- **Other signals detected:**
  - 9 sparse-text pages (sample of 100): pp 1, 2, 3, 25, 60, 76, … — mix of
    cover/copyright pages and illustration plates rather than true chapter
    title pages. Source 7 detection is noisy on this fixture.
  - 0 `CHAPTER N` running headers detected
  - No struct tree
  - **Printed TOC page (no hyperlinks) on the early pages** — every chapter
    title and printed page number is in parseable text but our signals probe
    didn't score this above threshold. Re-classify Davis as Source 6 +
    fallback Source 9.
- **Dominant pattern:** **Source 6** (printed TOC without hyperlinks) with
  **Source 9** (font-cluster) as the current fallback because Phase D's
  `toc_text` strategy isn't built yet.
- **Recommended strategy (long-term):** `toc_text` (Phase D) — parse the
  printed TOC page once that strategy exists. **Recommended strategy
  (interim):** continue `font_cluster`, mitigated by the OCR-garbage filter
  added in §7.0 #4 of `BOOKMARK_SOURCES.md`.
- **Notes:** Single-author monograph, OCR'd. Decorative drop-cap chapter
  numerals plus chapter title in distinct font causes typographic split
  into multiple text spans, which is why the font-cluster path produces
  both real chapter titles AND OCR garbage simultaneously. The OCR-garbage
  filter (`_is_ocr_garbage`) catches the typographic noise; real chapter
  titles like "Aesthetic Otoplasty", "Moderate Microtia and Partial Atresia",
  "Hemifacial Microsomia" survive. Some titles remain mangled by OCR
  ("Bihliography*", "5 m. fttns") — OCR quality issue, not pipeline.

### 2. ATLS_11_Course

- **File:** `ATLS 11th Edition Course Manua - American College Of Surgeons. C.pdf`
- **Size:** 75.9 MB · **Pages:** 377
- **Embedded outline:** 727 entries, depth distribution `{1: 33, 2: 694}`,
  pollution 0.8% (6 caption/folio entries — `0 - 6`, `7 - 10`, `11 +` score
  ranges and similar)
- **Other signals:** none meaningful (0 TOC pages, 0 chapter-header sample hits)
- **Dominant pattern:** **Source 1** — complete outline, near-zero pollution
- **Recommended strategy:** `outline_only` (current behavior is correct)
- **Notes:** Best-shaped fixture in the set. Validates the post-filter's
  conservative approach — only the genuinely-bad 6 entries get scrubbed.

### 3. ATLS_10_Faculty

- **File:** `ATLS 10th Edition Faculty ManualATLS 10th - American College Of Surgeons. Committee On.pdf`
- **Size:** 13.2 MB · **Pages:** 781
- **Embedded outline:** 1 entry (`Contents` → p 6) — useless
- **Other signals detected:**
  - **TOC pages with hyperlinks: pp 5, 6, 7, 8, 9, 27** — strong signal
  - 17 `CHAPTER N` running headers detected in 100-page sample (every chapter
    has a "CHAPTER N" header at the top)
  - 2 sparse pages
- **Dominant pattern:** **Source 5** — TOC with inbound hyperlinks
- **Recommended strategy:** `toc_links` (Phase D). Until that strategy exists,
  current behavior produces just 1 useless bookmark.
- **Notes:** Best motivating fixture for Phase D. Also a good fallback test for
  `chapter_headers_only` since 17/100 sampled pages had matching headers — full
  scan would likely find 30+.

### 4. ATLS_Legacy_2017

- **File:** `Advanced Trauma Life Support_ S - American College Of Surgeons. C.pdf`
- **Size:** 33.4 MB · **Pages:** 421
- **Embedded outline:** 31 entries, depth `{1: 7, 2: 24}`, **identifier-style
  titles** (`ATLS.9e_Ch01`, `ATLS.9e_Ch01_Skills_I`, …)
- **Other signals detected:**
  - 1 TOC page with hyperlinks (p 5)
  - **Has structure tree: True** — only fixture besides Dedivitis with
    PDF/UA-style tagging
  - 6.5% of outline entries point to page ≤ 1 (one entry "ATLS.9e_FrontMatter"
    at page -1, others fine)
- **Dominant pattern:** **Source 1** — complete outline (identifier titles are
  ugly but page targets are valid for 93.5% of entries)
- **Recommended strategy:** `outline_only` (works today). **Future improvement:**
  `struct_tree` strategy (Source 10) could surface human-readable chapter
  titles in place of `ATLS.9e_Ch01`.
- **Notes:** This is the fixture that proves Source 10 is worth implementing
  eventually — the human-readable structure exists in the PDF tags, just not
  in the outline.

### 5. Janfaza_HeadAnatomy

- **File:** `Surgical Anatomy of the Head an - Parviz Janfaza.pdf`
- **Size:** 108.9 MB · **Pages:** 932
- **Embedded outline:** 25 entries, depth `{1: 25}`, **100% point to page 1**
- **Other signals:**
  - 0 TOC pages detected
  - 2 chapter-title-page candidates (pp 64, 73)
  - No struct tree
- **Dominant pattern:** **Source 11** — outline titles are clean ("1.
  Superficial Structures of the Face, Head, and Parotid Region — …") but every
  page target is broken (all 1)
- **Recommended strategy:** `outline_repaginate` (Phase E). Titles are
  recoverable; page targets need to be re-derived by fuzzy-matching titles
  against page text.
- **Notes:** This is the canonical Source 11 fixture. Until Phase E exists,
  `outline_only` produces 25 bookmarks all pointing to page 1 (visible but
  navigationally useless). Worth verifying whether the broken pages stem from
  PyMuPDF reading the source's `/Dest` entries incorrectly vs. the source PDF
  genuinely encoding them as 1.

### 6. Dutton_Atlas

- **File:** `Atlas of Clinical and Surgical - Jonathan J. Dutton.pdf`
- **Size:** 160.4 MB · **Pages:** 253
- **Embedded outline:** 168 entries, depth `{1: 11, 2: 80, 3: 69, 4: 8}` —
  hierarchical and clean (0% pollution)
- **Other signals detected:**
  - **12 TOC pages with hyperlinks** (pp 1, 3, 6, 7, 15, 16, 17, 18, 19, 20,
    28, 29) — many more than expected; could be inbound links inside chapter
    body pages, not a printed TOC
  - 0 chapter title pages, 0 chapter headers
  - No struct tree
- **Dominant pattern:** **Source 1** — complete hierarchical outline
- **Recommended strategy:** `outline_only` — but with a caveat
- **Notes:** **Important contradiction with `BOOKMARK_SOURCES.md` §3.3**, which
  cites Dutton as the canonical Source 3 (flat) example needing
  `outline_plus_headers`. Actual data shows Dutton's source outline is
  hierarchical with 11 L1 chapter wrappers. The "flat" appearance the doc
  references is **downstream-induced**: `apply_depth_filter` drops L1 entries
  that don't match `CHAPTER_H1_RE` (Chapter/Section/Part + N or numeric
  prefix), and Dutton's chapter titles are descriptive ("Cavernous Sinus",
  "Osteology of the Orbit") so they're all dropped. The 80 surviving L2
  entries are what produces the 80-bookmark current bench result.
  **Phase B should reconsider whether L1 entries above L2 children should be
  kept regardless of `CHAPTER_H1_RE`.**

### 7. Cheney_FacialSurgery

- **File:** `Facial Surgery_ Plastic and Reconstructive - Mack L. Cheney, M. D_.pdf`
- **Size:** 252.2 MB · **Pages:** 1165
- **Embedded outline:** 2615 entries, depth `{1: 62, 2: 1414, 3: 1139}`,
  **78.5% pollution** (figure captions, page folios, contributor initials)
- **Other signals detected:**
  - **8 TOC pages without hyperlinks** (pp 19-26) — printed TOC present but
    not linked, redundant with embedded outline
  - 14 `CHAPTER N` running headers in 100-page sample (would scale to ~150+
    full-doc) — confirms running-header source exists
  - 1 sparse page (p 1, cover)
  - No struct tree
- **Dominant pattern:** **Source 2** — heavily polluted outline
- **Recommended strategy:** `outline_only` + existing `_post_filter`
  (current bench: 1474 → 465 entries after filtering, all 51 numbered
  chapters preserved)
- **Notes:** The post-filter already handles this case. No Phase A/B/C work
  needed. The 14 running-header signal is interesting as redundant validation
  — could cross-check chapter detection against running headers in a future
  Phase E to catch the cases where the outline drops a chapter.

### 8. Grabb_Flaps

- **File:** `Grabb's Encyclopedia of Flaps_ - Berish Strauch.pdf`
- **Size:** 69.6 MB · **Pages:** 1215
- **Embedded outline:** 232 entries, **all at L1** (`{1: 232}`)
- **Outline content:** First 2 entries are EPUB conversion artifacts
  (`OEBPS-14`, `OEBPS-6362`); remaining 230 are `Chapter N <description>`
- **Other signals detected:**
  - 23 `CHAPTER N` running headers in 100-page sample (would scale to ~280
    full-doc, matches the 230 chapter outline entries)
  - 2 sparse pages (pp 169, 541)
  - No struct tree
- **Dominant pattern:** **Source 3** — flat outline at L1 only
- **Recommended strategy:** `outline_only`. **Encyclopedia shape:** each chapter
  IS a flap technique; the source structure is intentionally flat. Adding
  parent hierarchy (e.g., grouping by anatomic region) would be a feature
  decision, not a bug fix. **Recommend treating Grabb as out-of-scope for
  `outline_plus_headers`** unless explicit topical grouping becomes a goal.
- **Notes:** Two leading `OEBPS-*` entries are pure EPUB-conversion noise and
  point to title-block pages — should be dropped by an extension to the
  post-filter (e.g., regex for `^OEBPS-\d+$`).

### 9. Gubisch_Rhinoplasty

- **File:** `Mastering Advanced Rhinoplasty - Wolfgang Gubisch.pdf`
- **Size:** 162.0 MB · **Pages:** 946
- **Embedded outline:** 316 entries, depth `{1: 10, 2: 15, 3: 60, 4: 214, 5: 17}`
  — deep five-level hierarchy
- **Other signals detected:**
  - 2 TOC pages with hyperlinks (pp 23-24)
  - 7 TOC pages without hyperlinks (pp 8-14)
  - 54 sparse "chapter title" pages in 100-page sample (many illustration plates)
  - No struct tree
- **Dominant pattern:** **Source 1** — complete outline at significant depth
- **Recommended strategy:** `outline_only`. At depth 2, would produce ~25
  bookmarks (10 L1 chapters + 15 L2 sub-chapters); at depth 3, ~85.
- **Notes:** Cleanest of the new fixtures. Heavy use of case studies
  (`1.2.1 Case 1: …`) at L4. Default `--depth 2` will hide most clinical
  content; this fixture argues for `--depth 3` or `--depth 4` to be useful.
  May warrant a per-fixture default-depth heuristic in a future session.

### 10. Kaufman_FacialRecon

- **File:** `Practical Facial Reconstruction - Dr. Andrew Kaufman M. D_.pdf`
- **Size:** 60.1 MB · **Pages:** 521
- **Embedded outline:** 93 entries, depth `{1: 12, 2: 8, 3: 73}`
- **Outline shape:** Front matter (Half Title, Title, Copyright, Dedication,
  Foreword, Preface, Acknowledgments, …) at L1, then `Part I/II/III` at L1,
  `Chapter N` at L2, `1.1`/`1.2`/… at L3
- **Other signals detected:**
  - 3 TOC pages with hyperlinks (pp 14-16)
  - 27 sparse pages in 100-page sample
  - No struct tree
- **Dominant pattern:** **Source 1** — complete outline
- **Recommended strategy:** `outline_only`. Existing post-filter will drop
  the front-matter L1 entries before "Part I" by the front-matter-region
  filter; surviving L1 entries (`Part I`, `Part II`, `Part III`) plus L2
  `Chapter N` give a clean default tree.
- **Notes:** First fixture with `Part I/II/III` → `Chapter N` two-tier
  structure (matches Cheney's PART/CHAPTER pattern). Confirms
  `FIRST_BODY_HEADING_RE` correctly recognises both `Part \w+` and
  `Chapter \d+`.

### 11. Dedivitis_Laryngeal

- **File:** `Laryngeal Cancer_ Clinical Case - Rogerio A. Dedivitis.pdf`
- **Size:** 34.2 MB · **Pages:** 189
- **Embedded outline:** 33 entries, depth `{1: 33}`, slug-style titles
  (`2-radiotherapy-for-t1a-glottic-cancer-2019`,
  `3-robotic-surgery-for-earlystage-laryngeal-cancer-2019`, …)
- **Other signals detected:**
  - 3 TOC pages with hyperlinks (pp 8, 26, 28)
  - 4 TOC pages without hyperlinks (pp 9-12)
  - **Has structure tree: True**
  - First entry "cover" at page **-1** (invalid)
- **Dominant pattern:** **Source 3** — flat outline at L1 only
- **Recommended strategy:** `outline_only`. **Case-series shape:** each entry
  is one clinical case, structurally analogous to Grabb's flap-per-chapter.
  Flat-at-L1 is the correct shape.
- **Notes:** Two improvements possible:
  - **Title rewrite:** the slugs (`2-radiotherapy-for-…-2019`) are derived
    from filename conventions, not human-readable titles. A `struct_tree`
    strategy or page-text harvest would yield "Radiotherapy for T1a Glottic
    Cancer" in proper case.
  - **Cover entry:** the `cover` entry at page -1 is invalid; should be
    dropped by an out-of-range check in `_post_filter`.

---

## Patterns observed

For each of the 12 signal patterns from `BOOKMARK_SOURCES.md` §2, fixtures
that exhibit the signal (whether dominant or secondary):

1. **Embedded outline, complete** — ATLS_11_Course, ATLS_Legacy_2017,
   Dutton_Atlas, Gubisch_Rhinoplasty, Kaufman_FacialRecon
2. **Embedded outline, polluted** — Cheney_FacialSurgery
3a. **Embedded outline, flat-by-defect** — None observed (Dutton was the
    expected example but is actually Source 1; see edge case 3 below).
3b. **Embedded outline, flat-by-design** (encyclopedia / case-series) —
    Grabb_Flaps, Dedivitis_Laryngeal
4. **Embedded outline, stale/wrong** — Not directly observed. Closest is
   Dedivitis (slug titles don't match human-readable chapter content), but
   page targets are correct so this is more a "title-quality" issue than
   "wrong outline".
5. **TOC page with hyperlinks** — ATLS_10_Faculty (dominant), ATLS_Legacy_2017,
   Dutton_Atlas, Gubisch_Rhinoplasty, Kaufman_FacialRecon, Dedivitis_Laryngeal
   (all secondary — outline already supplies primary structure)
6. **TOC page without hyperlinks** — Davis_Otoplasty (re-classified after
   Session-2 OCR-garbage analysis: TOC page exists but signals probe
   missed it; primary parseable source for Davis when Phase D ships),
   Cheney_FacialSurgery, Gubisch_Rhinoplasty, Dedivitis_Laryngeal
   (Cheney/Gubisch/Dedivitis all secondary, outline supplies primary
   structure)
7. **Distinctive chapter title pages** — Davis (low confidence — likely cover
   pages mistaken for title pages), Gubisch (54/100 sampled — many are
   illustration plates), Kaufman (27/100). Detector is noisy.
8. **Running CHAPTER N page headers** — ATLS_10 (17/100), Cheney (14/100),
   Grabb (23/100). Strong signal where present.
9. **Inline numbered section headings** — Davis (the only fixture where this
   is the only signal). Implicit in font-cluster fallback for any outline-less
   PDF.
10. **Structure tree tags** — ATLS_Legacy_2017, Dedivitis_Laryngeal (only 2
    fixtures)
11. **Repaginated/page-shifted outline** — Janfaza_HeadAnatomy (100% broken)
12. **No structural signals** — None. Every fixture has at least one usable
    signal.
13. **Title-quality issue** — Dedivitis_Laryngeal (slug titles like
    `2-radiotherapy-for-t1a-glottic-cancer-2019`); ATLS_Legacy_2017 borderline
    (identifier-style `ATLS.9e_Ch01` titles, but readable enough that
    `title_rewrite` is optional rather than necessary)

---

## Patterns NOT yet observed

- **Source 3a** (flat-by-defect — sections-only outline that *should* have
  chapter wrappers): no fixture exhibits this. Dutton was the expected
  example in BOOKMARK_SOURCES.md, but the survey shows Dutton's outline is
  hierarchical at the source; the flat downstream appearance is a
  depth-filter bug. **`outline_plus_headers` strategy implementation
  (originally Phase C) is therefore deferred** — no current fixture
  motivates it. See edge case 3 and BOOKMARK_SOURCES.md §7 Phase E.
- **Source 4** (stale/wrong outline — title-vs-page-text mismatch >30%):
  no fixture exhibits this. The closest is Janfaza (Source 11 — pages broken
  but titles fine) and Dedivitis (titles are slugs but page targets are
  correct). Defer the offset-correction half of `verify_pages` until a true
  Source-4 fixture appears.
- **Source 12** (no structural signals at all): no fixture exhibits this.
  Every fixture has at least an outline, a TOC page, or font-cluster-amenable
  body text. Defer `llm_rescue` until a true Source-12 fixture appears.

---

## Edge cases worth flagging

1. **Encyclopedia shape (Grabb_Flaps).** A flat L1 outline with one entry per
   technique is the correct structure for a reference work; `outline_plus_headers`
   would inappropriately invent topical grouping. The `chapter_headers_only`
   strategy might fit if we ever need to detect anatomic-region groupings,
   but that's a feature, not a bug.

2. **Case-series shape (Dedivitis_Laryngeal).** Same logic as Grabb —
   each clinical case is one structural unit. Flat-at-L1 fits the shape.
   The slug titles are the only real defect; consider a separate
   `title_rewrite` augmenter that pulls human titles from struct_tree or
   first-page text.

3. **Dutton outline-vs-filter mismatch.** Dutton's source outline is fully
   hierarchical, but `apply_depth_filter`'s `CHAPTER_H1_RE` requirement drops
   the descriptive L1 chapter wrappers. The fix is in the depth filter, not
   in a new strategy. Phase B should consider: "L1 entries that have L2
   children should be kept regardless of `CHAPTER_H1_RE`."

4. **Davis chapter-title-page noise.** The Source 7 detector (sparse-text
   pages) returned 9 candidates for Davis, but inspection suggests these are
   cover/copyright pages and illustration plates rather than chapter title
   pages. A robust Source 7 detector needs additional signals: large
   centered text + short title-shaped string + position in the document
   (not the first 5 or last 5 pages).

5. **EPUB-conversion artifacts (Grabb).** Two leading entries
   (`OEBPS-14`, `OEBPS-6362`) are pure conversion noise. Suggests extending
   `_post_filter`'s caption/folio rejection with an `EPUB_ARTIFACT_RE`
   pattern. Low priority — only 2 entries out of 232.

6. **Invalid page targets (Janfaza, Dedivitis).** Janfaza has 100%
   broken (all → page 1); Dedivitis has the cover entry at page -1.
   `_post_filter` should reject any entry with `page < 0` or `page >
   doc.page_count` as a sanity guard, independently of Source 11
   repaginate logic.

7. **Struct tree availability is rarer than expected.** Only 2/11 fixtures
   (`ATLS_Legacy_2017`, `Dedivitis_Laryngeal`) expose `/StructTreeRoot`.
   Source 10 strategy implementation has limited near-term ROI; defer until
   we encounter a fixture where it would clearly improve title quality
   (ATLS_Legacy is a candidate but its outline already works).

8. **Default depth=2 mismatches deep hierarchies.** Gubisch has 5 levels of
   structure; depth=2 hides almost all clinical content. The current CLI
   forces a single depth across all fixtures. Future session might consider
   per-fixture depth heuristics or auto-depth selection based on the source's
   distribution.

---

## Implications for next sessions

### Phase A (`signals.py` — detection only)

Detectors that **must** be implemented to handle the 11 observed fixtures:

- Outline source: presence, entry count, depth histogram, pollution estimate
- Outline page-target validity (catches Source 11 — Janfaza)
- TOC pages with hyperlinks (catches Source 5 — ATLS_10)
- TOC pages without hyperlinks (validator's `_looks_like_toc_page`, useful
  for several secondary signals)
- Running `CHAPTER N` headers (sample-based; needed for Phase C)
- Struct tree presence (cheap to check, Source 10 hook for future)

Detectors **deferred** until a fixture motivates them:

- Source 4 page-text verification (no Source-4 fixture in the set)
- Source 7 chapter-title-page detection beyond the current low-text-density
  heuristic — needs refinement before being useful (Davis false-positive
  problem)
- Source 12 (no fixture exhibits it)

### Phase B (router + outline_only/font_cluster wrappers)

Refactor needed:
- `outline_only` strategy must include the existing `_post_filter`
- `font_cluster` strategy is the existing extractor.py step 2
- **Filter-pipeline fix:** L1 entries with descendants should not be dropped
  by `CHAPTER_H1_RE` (Dutton fix; not a new strategy, an existing-code patch)
- **Sanity guard:** `_post_filter` should reject `page < 0` or `page >=
  page_count` entries (Dedivitis cover, Janfaza paranoia)

### Phase C (`outline_plus_headers`)

Worth implementing for: nothing observed in this set requires it. Reconsider
whether the doc's premise was right. The Dutton case (cited in BOOKMARK_SOURCES.md
as the motivating example) is actually a depth-filter bug, not a missing
strategy.

**Recommendation:** Defer Phase C until a fixture genuinely exhibits
"flat outline + running CHAPTER N headers + need for parent hierarchy".
Grabb has the running headers but is intentionally flat (encyclopedia).

### Phase D (`toc_links`)

**Highest-priority new strategy.** ATLS_10_Faculty is unusable without it —
currently produces 1 useless bookmark. Three other fixtures have toc-link
secondary signals as redundant verification candidates.

### Phase E (`outline_repaginate` + `verify_pages`)

Janfaza is the canonical motivating fixture. 25 chapter titles, all pages
broken to 1. Phase E here is high-value.

### New strategies suggested by these fixtures

- **`title_rewrite` augmenter** — for Dedivitis-style slug titles, pull
  human-readable titles from struct_tree or page-text first-line. Niche but
  cheap.
- **`epub_artifact_filter` (extension to `_post_filter`)** — drop
  `^OEBPS-\d+$` entries. Trivial.
- **`page_bounds_filter` (extension to `_post_filter`)** — drop entries
  with `page < 0` or `page >= page_count`. Trivial sanity guard.

---

## Appendix: how this report was generated

- `_session0_survey.py` — fitz `get_toc()` survey (Task 2 output:
  `embedded_outline_survey.txt`)
- `_session0_signals.py` — per-fixture signal probes using shared
  `_is_caption_or_folio` from `auto-pdf-bookmarks/extractor.py` and
  `_looks_like_toc_page` from `auto-pdf-bookmarks/validator.py`
  (Task 3 output: `signal_classification.txt`)
- Both scripts capped detector budget at first 30 pages (TOC scan) and 100
  evenly-spaced pages (header sample) to keep runtime under 60 s on the
  full 11-fixture set.
- No PDFs were modified. No bookmark generation was performed.
