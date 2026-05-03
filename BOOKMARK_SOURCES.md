# KumaPDFBookmark — Bookmark Source Taxonomy & Strategy Router

**Status:** Design — ready for implementation in a focused Claude Code session
**Target files:** new `signals.py`, new `strategies.py`, refactored `extractor.py`, patched `main.py` (CLI surface)
**Scope:** v0.3 of KumaPDFBookmark. Builds on the post-filter (commits 1a66af6/aff9715) and validator framework (May 2026).

---

## 1. Why this exists

The current extractor is a hardcoded fallback chain:

```
embedded TOC -> font cluster -> regex pattern
```

This shape is too coarse for real-world PDFs because it treats sources as exclusive. Dutton's case proves the point: it has *both* an embedded outline (flat, missing chapter wrappers) *and* "CHAPTER N" running headers that could supply the missing structure. The current chain takes the outline and stops; the headers are ignored.

The fix is to model bookmark sources as a **taxonomy of signals** with a **router** that detects which signals are present and selects an extraction strategy that combines them. Detection is cheap, runs once, and feeds both auto-mode strategy selection and a `--inspect` mode that prints the survey for users.

## 2. Signal taxonomy

Twelve+ recognized signal patterns. The router cares about presence/absence and, for some, quality.

| # | Source | Detection | Quality signal |
|---|---|---|---|
| 1 | Embedded outline, complete | `doc.get_toc()` returns >5 entries with sane depth distribution | Trust unless polluted |
| 2 | Embedded outline, polluted | Outline present but >20% caption/folio/initial-pattern entries | Trust shape, scrub via post-filter |
| 3a | Embedded outline, flat — *defect* (sections-only, missing chapter wrappers) | Outline present, all entries at depth 1, page headers show "CHAPTER N", entries vary in topical scope | Augment with running-header chapters |
| 3b | Embedded outline, flat — *by design* (encyclopedia / case-series) | Outline present, all entries at depth 1, AND a per-entry uniqueness signal: alphabetical/numeric ordering, ~equal pages-per-entry distribution, no shared topical roots, OR each entry already names a self-contained unit (technique, case, term) | Trust as-is; flat IS the correct shape, no augmentation |
| 4 | Embedded outline, stale/wrong | Title fuzzy-match against landed page text below threshold for >30% of entries | Replace via secondary source |
| 5 | TOC page with hyperlinks | First N pages contain `page.get_links()` results pointing inward, count >5 | Highest-quality non-outline source |
| 6 | TOC page without hyperlinks | First N pages match TOC density heuristic (validator's `_looks_like_toc_page`), no inbound links | Use validator's TOC parser logic |
| 7 | Distinctive chapter title pages | Pages with low text density (<200 chars) and large font, count matches expected chapter count | Detect boundaries, harvest titles |
| 8 | Running "CHAPTER N" page headers | Top-of-page text region matches `^CHAPTER\s+\d+`, count >3 | Boundary signal, plus chapter title from next-line text |
| 9 | Inline numbered section headings | Font-ratio analysis finds candidates with `^\d+(\.\d+)*\s+[A-Z]` titles | Current font extractor's domain |
| 10 | Structure tree tags (PDF/UA, Adobe-tagged) | `doc.get_xml_metadata()` exposes StructTreeRoot with H1/H2 tags | Highest-quality if present |
| 11 | Repaginated/page-shifted outline | Outline page targets fail title-text verification with consistent ±N offset, OR all targets collapse to a single page (page 1 sentinel) | Auto-correct shift, or rebuild via title-text fuzzy match |
| 12 | No structural signals | All detectors return null/sparse | Honest "no structure detectable", optional LLM rescue |
| 13 | Title-quality issue | Outline structure is valid (correct counts, valid page targets) but >30% of titles match a slug regex (`^[a-z0-9]+([-_][a-z0-9]+)+$`, `^OEBPS[-_]\d+$`, etc.) OR have <2 unique words after dedup | Run `title_rewrite` augmenter using struct-tree text or page-text first-line scrape |

**Out of scope but worth recognizing:**

- Image-only PDFs with no text layer → upstream OCR responsibility
- Multi-volume sets → per-file extractor still works on each, no cross-file reasoning

## 3. Architecture

```
                       PDF
                        |
                        v
              +-------------------+
              |  detect_signals() |   --> SignalReport
              +-------------------+         (read-only survey, ~1-3 sec)
                        |
                        v
              +-------------------+
              |  select_strategy()|   --> Strategy(primary, augmenters)
              +-------------------+
                        |
                        v
              +-------------------+
              |   extract()       |   --> List[Heading]
              | (strategy.run)    |
              +-------------------+
                        |
                        v
              +-------------------+
              |  _post_filter()   |   --> List[Heading], scrubbed
              | (existing code)   |
              +-------------------+
                        |
                        v
              +-------------------+
              |   writer.set_toc()|
              | (fitz, current)   |
              +-------------------+
```

### 3.1 SignalReport

```python
@dataclass
class SignalReport:
    pdf_path: str
    page_count: int

    # Source 1-4: embedded outline
    has_outline: bool
    outline_entry_count: int
    outline_pollution_estimate: float   # 0.0-1.0, fraction of entries that look like noise
    outline_depth_histogram: dict[int, int]  # {1: 80, 2: 0, 3: 0} for Dutton; {1: 56, 2: 409, 3: 0} for Cheney
    outline_page_verification: float | None  # 0.0-1.0, fraction whose page text matches title; None if not run

    # Source 5-6: printed TOC pages
    toc_pages_with_links: list[int]
    toc_pages_without_links: list[int]
    toc_entry_count_estimated: int

    # Source 7: chapter title pages
    chapter_title_page_candidates: list[int]   # 1-indexed pages

    # Source 8: running headers
    chapter_header_pages: list[int]             # pages where "CHAPTER N" found in top region
    chapter_header_titles: dict[int, str]       # page -> harvested title from next line

    # Source 9: font-cluster candidates (cheap pre-pass count, not full extraction)
    font_cluster_candidate_count: int

    # Source 10: structure tree
    has_struct_tree: bool
    struct_tree_heading_count: int

    # Recommendation
    recommended_strategy: str
    rationale: list[str]                        # human-readable reasons for the recommendation
```

### 3.2 Strategy

```python
@dataclass
class Strategy:
    name: str                                   # "outline_only", "outline_plus_headers", "toc_links", etc.
    primary: str                                # which source supplies the bookmark list
    augmenters: list[str]                       # ordered list of augmenter names to apply
    options: dict[str, Any]                     # strategy-specific knobs

    def run(self, signals: SignalReport) -> list[Heading]:
        ...
```

### 3.3 Strategy catalog

Each is an independently testable module. Naming follows `<primary>[_plus_<augmenter>]` convention.

| Strategy name | Primary source | Augmenters | Use case |
|---|---|---|---|
| `outline_only` | Embedded outline | none | Sources 1, 2 (post-filter handles 2), 3b (flat is intentional) |
| `outline_plus_headers` | Embedded outline | `chapter_headers` (insert chapter parents) | Source 3a — flat-by-defect. **No current fixture motivates this.** Originally cited Dutton, but Dutton is actually Source 1 with a depth-filter bug; see §7.0. |
| `outline_repaginate` | Embedded outline | `verify_pages` (auto-shift detection) | Source 4 |
| `toc_links` | TOC page hyperlinks | none | Source 5 |
| `toc_text` | Printed TOC text parse | `verify_pages` | Source 6 |
| `struct_tree` | PDF structure tags | none | Source 10 |
| `font_cluster` | Font-ratio analysis | `caption_filter` (already in post-filter) | Source 9 (Davis) |
| `chapter_headers_only` | Running "CHAPTER N" headers | `font_cluster` (subsections) | Source 8 alone |
| `chapter_pages_only` | Title-page detection | `chapter_headers` | Source 7 alone |
| `regex_pattern` | Numbered heading regex | none | Last-resort fallback |
| `llm_rescue` | LLM proposal from full text | `verify_pages` | Source 12 (no signals), opt-in only |

### 3.4 Augmenter catalog

An augmenter takes a `(headings, signals)` and returns a modified `headings` list. Composition is associative — augmenters run left-to-right.

| Augmenter | Effect |
|---|---|
| `chapter_headers` | For each page in `signals.chapter_header_pages`, insert a depth-1 entry at that page if no entry exists; reparent existing same-page entries to it |
| `verify_pages` | For each heading, fitz the landed page; if title doesn't fuzzy-match page text, mark for offset detection |
| `dedupe_titles` | Collapse exact-duplicate consecutive entries (for cases where outline + augmenter both proposed the same heading) |
| `caption_filter` | Drop figure/table/plate/box/folio entries (already in `_post_filter`, listed for completeness) |
| `title_rewrite` | For entries whose title matches a slug regex (`^[a-z0-9]+([-_][a-z0-9]+)+$`) or an OEBPS artifact pattern, replace title with text harvested from struct-tree (if present) or the first non-empty heading-shaped line of the landing page. Source 13. |

## 4. Auto strategy selection logic

Decision tree, evaluated top-to-bottom:

```
1. has_struct_tree AND struct_tree_heading_count >= 5
   -> struct_tree

2. has_outline AND outline_entry_count >= 5:
   2a. outline_depth_histogram has only depth 1 (flat outline):
       2a.i. AND topical-uniqueness signal absent
             (entries vary in scope, no alphabetical/numeric ordering,
              uneven pages-per-entry distribution)
             AND len(chapter_header_pages) >= 3
             -> outline_plus_headers (Source 3a — flat-by-defect)
       2a.ii. OTHERWISE
             (encyclopedia ordering, equal pages-per-entry, slug-style numeric prefixes,
              or each entry already names a self-contained unit)
             -> outline_only (Source 3b — flat is intentional)
   2b. outline_page_verification < 0.5 (more than half titles don't match landing page)
       OR >50% of entries point to page <= 1
       -> outline_repaginate (Source 11)
   2c. >30% of titles match slug-regex OR have <2 unique words
       -> outline_only + title_rewrite augmenter (Source 13)
   2d. otherwise
       -> outline_only (Sources 1, 2 — post-filter scrubs Source 2)

3. len(toc_pages_with_links) >= 1 AND link count >= 5
   -> toc_links

4. len(toc_pages_without_links) >= 1 AND toc_entry_count_estimated >= 5
   -> toc_text

5. len(chapter_header_pages) >= 3 OR len(chapter_title_page_candidates) >= 3
   -> chapter_headers_only or chapter_pages_only (whichever has higher count)

6. font_cluster_candidate_count >= 10
   -> font_cluster

7. otherwise
   -> regex_pattern (last-ditch deterministic), or llm_rescue if --llm-rescue set
```

Rationale for each branch printed in `signals.rationale` so `--inspect` and `--verbose` show the user *why* a strategy was chosen.

## 5. CLI surface

Backward-compatible: existing invocations keep working.

```
# Default — auto-detect, run, write
python main.py input.pdf output.pdf [--depth 2]

# Inspect: detect signals, print report and recommended strategy, do not write
python main.py input.pdf --inspect

# Force a specific strategy
python main.py input.pdf output.pdf --strategy outline_plus_headers

# List available strategies and exit
python main.py --list-strategies

# Override individual augmenters when forcing a strategy
python main.py input.pdf output.pdf --strategy outline_only --add-augmenter chapter_headers

# LLM rescue when no signals detected
python main.py input.pdf output.pdf --llm-rescue --llm-backend ollama --llm-model mistral-nemo
```

`--inspect` output (text format, ~30 lines, scannable):

```
=== KumaPDFBookmark — Signal Report ===
PDF: /path/to/Atlas_Dutton.pdf  (253 pages)

Embedded outline       : 80 entries  (depth dist: {1: 80})
                         pollution estimate: 12%
                         page-text verification: 91%
TOC page (linked)      : not detected
TOC page (text)        : not detected
Chapter title pages    : 11 candidates  (pp 1, 24, 47, 71, 94, ...)
Running CHAPTER headers: 11 detected   (pp 1, 24, 47, 71, 94, ...)
Font-cluster candidates: 47
Struct tree            : not present

Recommendation         : outline_plus_headers
  - embedded outline has 80 entries but all at depth 1 (no chapter level)
  - 11 "CHAPTER N" page headers detected, can supply parent level
  - augmenter `chapter_headers` will insert chapter parents and reparent existing entries
```

`--list-strategies` output:

```
Strategies:
  outline_only          Use embedded outline as-is. (Sources: complete or polluted outline)
  outline_plus_headers  Use embedded outline, augment with detected chapter headers.
  outline_repaginate    Use embedded outline, auto-correct page-shift.
  toc_links             Build outline from TOC page hyperlinks.
  toc_text              Build outline from TOC page text parse.
  struct_tree           Use Adobe-tagged structure tree.
  font_cluster          Font-size analysis on body pages.
  chapter_headers_only  Use only "CHAPTER N" running headers + font cluster for sections.
  chapter_pages_only    Use only chapter title pages + font cluster for sections.
  regex_pattern         Numbered heading regex (last resort).
  llm_rescue            LLM proposal from full text. Requires --llm-backend.
```

## 6. CLI auto-mode example invocations and expected behavior

| Fixture | Auto-selected strategy | Why |
|---|---|---|
| Cheney atlas | `outline_only` | Outline present (post-filter handles pollution) |
| ATLS 11 | `outline_only` | Outline present, mostly clean |
| ATLS 10 / Janfaza / ATLS Legacy | `outline_only` | Outline present (writer migration unblocked them) |
| Dutton | `outline_only` | Outline already hierarchical (depths 1-4); previously appeared "flat" downstream because `apply_depth_filter` drops L1 chapter wrappers via `CHAPTER_H1_RE`. Pre-phase fix in §7.0 restores the chapters. |
| Davis monograph | `font_cluster` | No outline, no TOC, body pages with numbered headings |

## 7. Implementation plan

Phased so each step is testable in isolation against `_bench.py`. Phase
ordering and motivations were revised after the Session 0 fixture survey
(see `FIXTURE_REPORT.md`); §7.0 captures the pre-phase code fixes that
must land first because later phases assume their effects are in place.

### 7.0 Pre-phase fixes from the Session 0 survey

Three known bugs surfaced by `FIXTURE_REPORT.md` that should land **before**
any taxonomy phase work, since later phases assume their effects are gone.
None of these are new strategies — they're patches to existing code.

1. **`apply_depth_filter` drops L1 entries with descendants.**
   `auto-pdf-bookmarks/main.py` currently applies `CHAPTER_H1_RE` to every
   L1 entry and rejects those without a chapter-number prefix, even when
   the entry has L2+ children. Dutton's 11 chapter wrappers ("Cavernous
   Sinus", "Osteology of the Orbit", …) are all dropped this way, which is
   the source of the "Dutton looks flat" observation that originally
   motivated `outline_plus_headers`. **Fix:** keep L1 entries that have any
   L2/L3/L4 descendants in the heading list, regardless of `CHAPTER_H1_RE`
   match.

2. **`_post_filter` should add a `page_bounds_filter`.** Janfaza's source
   outline points all 25 entries to page 1; Dedivitis's "cover" entry
   points to page -1. Both produce visible-but-broken bookmarks today.
   **Fix:** in `auto-pdf-bookmarks/extractor.py:_post_filter`, reject any
   `Heading` with `page < 0` or `page >= doc.page_count`. (Note: this
   does not solve Janfaza's broken page targets — that's Phase D — but
   stops Dedivitis's cover entry from leaking through.)

3. **`_post_filter` should add an `epub_artifact_filter`.** Grabb's
   outline leads with `OEBPS-14` and `OEBPS-6362`, which are pure
   EPUB-conversion artifacts. **Fix:** in `_post_filter`, reject titles
   matching `^OEBPS[-_]\d+$`.

4. **`_post_filter` should add an `_is_ocr_garbage` quality guard.**
   Surfaced during the §7.0 #1 implementation: when fix #1 keeps L1
   entries with descendants, font-cluster fixtures (Davis) start
   surfacing OCR-noise spans that happen to be at L1 size and followed
   by L2 children (`4t`, `-h-`, `f \ /' -`, `". , ),/t::"`). **Fix:** in
   `extractor.py:_post_filter`, reject titles where `alpha_count < 4`
   OR `non_alpha_non_space > alpha_count`. Universal quality guard —
   does not catch real headings even with sparse content
   (`Embryology` → 9 alpha, `ATLS.9e_Ch01` → 8 alpha).

These four patches are isolated to `main.py` (#1) and
`extractor.py:_post_filter` (#2, #3, #4). They land before Phase A.
Verified across the full 11-fixture set via `_bench.py PREPHASE`:

| Fixture | Baseline | After §7.0 | Δ | What happened |
|---|---:|---:|---:|---|
| `Davis_Otoplasty`     |  17 |  17 |    0 | Composition swap: 7 OCR-fragment L1s/L2-dashes dropped, 7 real chapter titles recovered ("The Patient", "Aesthetic Otoplasty", "Moderate Microtia and Partial Atresia", "The Cartilage", "Severe Microtia and Radical Auriculoplasty", "Bilateral Microtia and Atresia", "Hemifacial Microsomia"). "Conclusion" / "Bihliography*" not recovered — no L2 children. True fix is Phase D `toc_text`. |
| `ATLS_11_Course`      | 695 | 693 |   −2 | OCR-fragment L2s dropped (`III` at p150 alpha=3, `B-C.` at p310 alpha=2). |
| `ATLS_10_Faculty`     | 914 |1391 | +477 | ~500 real ATLS section headings restored ("The Development and Structure of ATLS", "The ATLS Program", "Course Overview", "Before the Course", "during the Course", …) — they had no chapter numbers but had L2 sub-section children. 23 OCR-fragment L2s dropped (test-answer-row strings like `1-10. (a) (b) (c) (d) (e) 1-30. (a) (b) (c) (d) (e)`). |
| `ATLS_Legacy_2017`    |  24 |  25 |   +1 | "Student Manual WIP3" L1 root container restored; "ATLS.9e_FrontMatter" correctly re-nested L1→L2 under it. |
| `Janfaza_HeadAnatomy` |  83 |  72 |  −11 | 23 real all-caps chapter wrappers gained ("ANATOMY OF THE NECK", "TEMPORALIS AND INFRATEMPORAL FOSSAE", "PHARYNX", "ORAL CAVITY", …); 34 OCR fragments dropped (`-------,f----_`, `~--J~`, `1tri--`, `(Fig. 12.15}`, …). Page targets remain broken (all → page 1) — that's Phase D `outline_repaginate`, not §7.0. |
| `Dutton_Atlas`        |  80 |  90 |  +10 | 10 of 11 source L1 chapter wrappers restored ("Cavernous Sinus", "Osteology of the Orbit", …). The 11th — "Histologic Anatomy of the Orbit" at p173 — has no L2 children in source so `_has_descendants` correctly doesn't promote it. |
| `Cheney_FacialSurgery`| 465 | 445 |  −20 | 20 single-letter index navigation markers `I-1`…`I-20` on pp 1146-1165 dropped via `_is_ocr_garbage`. Alphabetical-index anchors, not chapter content. |
| `Grabb_Flaps`         | 229 | 229 |    0 | OEBPS entries already dropped by `_post_filter`'s front-matter region check (they land before Chapter 1's page). #3 makes the rejection explicit and robust to future fixtures where `FIRST_BODY_HEADING_RE` doesn't fire. |
| `Gubisch_Rhinoplasty` |  17 |  23 |   +6 | 6 PART-level wrappers restored ("Internal Nose: Septum", "External Nose", "Nasal Pyramid", "Malformations", "Complex Revision", "Software") — same mechanism as Dutton. |
| `Kaufman_FacialRecon` |  16 |  16 |    0 | Already-clean outline; no descendants-recovery needed. |
| `Dedivitis_Laryngeal` |  31 |  31 |    0 | "cover" entry at page -1 was already being dropped by `apply_depth_filter`'s `_has_chapter_number` check; #2 makes it explicit at `_post_filter`. Cleaner pipeline ordering, no count change. |

**Surprise from the bench: Fix #1's chapter-wrapper recovery is much
broader than the Session 0 survey predicted.** The survey identified
Dutton as the canonical case, but ATLS_10 (+477), ATLS_11_Course (−2),
ATLS_Legacy_2017 (+1), Janfaza (−11), and Gubisch (+6) all share the
same root cause: descriptive or all-caps chapter titles that don't
match `CHAPTER_H1_RE`. Five fixtures were silently degraded by the
same mechanism Dutton was. Phase A's signal taxonomy needs a "has
descriptive (non-numbered) chapter wrappers" detector to match this
generality — currently the report only labels Dutton/Gubisch/Kaufman
as the chapter-wrapper-bearing fixtures, but ATLS_10 is the most
dramatic case (+500 headings restored).

### Phase A — Signal detection *(no behavior change)*
1. Create `signals.py` with `detect_signals(pdf_path) -> SignalReport`
2. Implement detectors 1, 2, 3a/3b discriminator, 5, 6, 8, 9, 10, 11, 13
   (skip 4 and 7 for now — no current fixture motivates them; see
   `FIXTURE_REPORT.md` §"Patterns NOT yet observed")
3. Add `--inspect` to `main.py` that prints the report and exits
4. Verify against the 11 fixtures: every fixture produces a sensible report

**Acceptance criterion — Davis TOC detection.** Session 2 surfaced that
the Session 0 probe (`_session0_signals.py`, using `validator._looks_like_toc_page`)
missed Davis's printed TOC page, so Davis was misclassified as Source 9
(font-cluster only) when it's actually Source 6 (TOC page without
hyperlinks) with Source 9 as a fallback. Davis's TOC has decorative
typography — drop-cap chapter numerals plus chapter title in distinct
font with sparse spacing — that the current density heuristic doesn't
score above threshold. Phase A's Source 6 detector must pass on Davis
without human inspection. Either:
  - tune the detector threshold so the existing density heuristic catches
    Davis (preferred — test on the 9-page Davis front matter), or
  - add a complementary signal (e.g. detect runs of "<title> ......... <int>"
    even when the dot-leaders are absent or unusual), or
  - both, if a single fix can't cover Davis without false positives on
    other fixtures.

  Davis-specific test case: open the source PDF, scan pages 5-9, and
  confirm the detector flags at least one of those as a TOC-without-
  hyperlinks page. Numeric threshold: TOC entry density on Davis's
  contents page is ~10-15 entries on one page, well above the validator's
  current `min_entries=4` floor — so the issue is likely line-recognition
  format, not count.

### Phase B — Strategy router *(no behavior change yet, just plumbing)*
1. Create `strategies.py` with `Strategy` dataclass and a registry
2. Wrap current behavior as the `outline_only` and `font_cluster` strategies
3. Implement `select_strategy(signals) -> Strategy` per §4 routing rules
4. Refactor `extractor.py:extract_outline` to use the router
5. Run `_bench.py ROUTER` — all 11 fixtures should produce identical
   bookmarks to PRE_PHASE baseline

### Phase C — TOC link harvest *(was old Phase D; promoted)*
**Motivation:** `ATLS_10_Faculty` is unusable today (1 useless bookmark);
TOC pages with hyperlinks at pp 5-9, 27 are the only viable structural
signal.

1. Implement TOC-page link detection in `signals.py` (extends Phase A)
2. Implement `toc_links` strategy that walks the link annotations and
   builds a heading list from their destinations
3. Update `select_strategy` rule 3
4. Run `_bench.py TOC_LINKS` — `ATLS_10_Faculty` should jump from 1 to
   ~30+ bookmarks; other 10 fixtures unchanged

### Phase D — Page verification + repaginate *(was old Phase E; promoted)*
**Motivation:** `Janfaza_HeadAnatomy` ships 25 valid chapter titles all
pointing to page 1. Today this produces 25 visible-but-broken bookmarks.

1. Implement `verify_pages` augmenter (fitz the landing page, fuzzy-match
   title against page text)
2. Implement `outline_repaginate` strategy with single-page-collapse
   detection (Janfaza shape) and ±N offset detection (true Source 4 shape,
   currently no fixture)
3. Add a synthetic test fixture for the offset case (Phase D-only,
   skip if too expensive)
4. Run `_bench.py REPAGINATE` — `Janfaza_HeadAnatomy` chapter pages
   should map to plausible body pages; other 10 fixtures unchanged

### Phase E (deferred) — outline_plus_headers *(was old Phase C)*
**Currently no motivating fixture.** The original motivation was Dutton,
which the Session 0 survey identified as a depth-filter bug (§7.0 #1)
rather than a missing strategy. Re-prioritise when a real Source 3a
fixture appears.

If/when implemented:
1. Implement `chapter_headers` augmenter (top-of-page text scrape, regex
   match, insert/reparent)
2. Implement `outline_plus_headers` strategy
3. Update `select_strategy` rule 2a.i
4. Run `_bench.py PLUS_HEADERS` against the candidate fixture only

Phases A → B → §7.0 fixes are the critical path. Phases C and D are
independent and can ship in either order. Phase E is deferred indefinitely
pending a motivating fixture.

## 8. Testing rubric

For each strategy, the bench should report:

- bookmark count vs prior baseline
- bookmark count vs validator's `missing_in_bookmarks` (recall)
- post-filter drop count (precision pressure)
- end-to-end time (signal detect + extract + write)

Add a `_bench.py --strategy STRATEGY_NAME` flag that forces the strategy on every fixture and produces a per-strategy comparison table. This is how you'd verify "outline_plus_headers doesn't accidentally degrade Cheney" — run it against Cheney with the augmenter forced and compare to the auto-selected `outline_only` baseline.

## 9. Out of scope for v0.3

- Repaginated/stale outline detection (Phase E, deferred)
- Multi-volume cross-file reasoning
- Image-only PDF / OCR integration (handled upstream by `ocrmypdf --skip-text`)
- Calibre plugin UI surface for strategy override (CLI-only for now; plugin can shell out)
- LLM coherence pass for ambiguous strategy selection

## 10. Risks and mitigations

**Risk: detector cost on huge PDFs.** Cheney is 264MB and 1165 pages. Running every detector on every page would be slow.
*Mitigation:* most detectors only need first 30 pages (TOC) and a sampling of body pages (chapter headers, title pages). Cap detector page budget.

**Risk: augmenter explosion.** Adding augmenters per-fixture risks turning the codebase into a special-case zoo.
*Mitigation:* augmenters must be reusable across strategies. Reject any augmenter that's only useful for one PDF.

**Risk: silent strategy drift.** A future change to `select_strategy` could route a fixture to a different strategy and silently degrade quality.
*Mitigation:* `_bench.py` records the selected strategy per fixture; CI-style diff catches drift.

**Risk: user confusion when auto picks wrong.** A user with a weird PDF might not understand why bookmarks look bad.
*Mitigation:* `--verbose` always prints the SignalReport and selected strategy with rationale, so the diagnosis is one flag away.
