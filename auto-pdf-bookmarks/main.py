"""
auto-pdf-bookmarks CLI entry point.

Usage examples:
    python main.py input.pdf output.pdf
    python main.py input.pdf output.pdf --depth 2 --verbose
    python main.py input.pdf output.pdf --depth 1 --dry-run
    python main.py input.pdf output.pdf --llm --model mistral-nemo --verbose
"""
import argparse
import re
import sys

from config import (
    CHAPTER_H1_RE,
    CREDENTIAL_RE,
    FRONT_MATTER_RE,
    OLLAMA_BASE_URL,
    OLLAMA_DEFAULT_MODEL,
)
from extractor import Heading, extract_outline
from writer import write_outline


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="auto-pdf-bookmarks",
        description="Detect and embed bookmarks in a PDF, optimised for medical textbooks.",
    )
    parser.add_argument("input", help="Path to the source PDF file.")
    parser.add_argument(
        "output",
        nargs="?",
        default=None,
        help="Path for the output PDF with bookmarks (required unless --dry-run).",
    )
    parser.add_argument(
        "--depth",
        type=int,
        default=2,
        choices=[1, 2, 3],
        metavar="{1,2,3}",
        help=(
            "Maximum bookmark depth: "
            "1 = chapters only, "
            "2 = chapters + sections (default), "
            "3 = chapters + sections + subsections."
        ),
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print detected headings to stdout without writing a PDF.",
    )
    parser.add_argument(
        "--llm",
        action="store_true",
        default=False,
        help="Enable Ollama LLM to resolve ambiguous heading candidates.",
    )
    parser.add_argument(
        "--model",
        default=OLLAMA_DEFAULT_MODEL,
        metavar="NAME",
        help=f"Ollama model name (default: {OLLAMA_DEFAULT_MODEL}).",
    )
    parser.add_argument(
        "--ollama-url",
        default=OLLAMA_BASE_URL,
        metavar="URL",
        help=f"Ollama base URL (default: {OLLAMA_BASE_URL}).",
    )
    parser.add_argument(
        "--pages",
        default=None,
        metavar="START-END",
        help="For --dry-run: only display headings within this 1-indexed page range (e.g. --pages 20-100).",
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        default=False,
        help="Print progress information.",
    )
    return parser.parse_args(argv)


# ---------------------------------------------------------------------------
# Depth filter + front matter / chapter-number logic
# ---------------------------------------------------------------------------

def _is_front_matter(title: str) -> bool:
    return bool(FRONT_MATTER_RE.match(title.strip()))


def _has_chapter_number(title: str) -> bool:
    return bool(CHAPTER_H1_RE.search(title))


def _is_credential_name(title: str) -> bool:
    """Return True for lines like 'JOHN SMITH, MD, FACS' — author attributions."""
    return bool(CREDENTIAL_RE.search(title))


def _has_descendants(headings: list[Heading], idx: int) -> bool:
    """
    Return True when headings[idx] is followed by one or more entries deeper
    than itself before any entry at the same level or shallower.

    Used by apply_depth_filter to keep an L1 entry whose title doesn't
    match CHAPTER_H1_RE (e.g. Dutton's descriptive chapter titles like
    "Cavernous Sinus") when that entry is the parent of L2/L3/L4 children.
    """
    cur_level = headings[idx].level
    for h in headings[idx + 1:]:
        if h.level > cur_level:
            return True
        if h.level <= cur_level:
            return False
    return False


# Strips leading chapter number and optional single-letter mnemonic code
# ("3 x: Title" → "title") so that two variants of the same chapter heading
# compare equal during deduplication even when one carries the mnemonic label.
_CHAPTER_NUM_PREFIX = re.compile(r"^\d+\s+(?:[a-zA-Z]:\s*)?")


def _dedup_key(title: str) -> str:
    return _CHAPTER_NUM_PREFIX.sub("", title).strip().lower()


def apply_depth_filter(headings: list[Heading], depth: int) -> list[Heading]:
    """
    Filter headings to the requested depth.

    Rules:
    - Front matter headings (Preface, Foreword, Dedication, etc.) are always
      kept and promoted to H1, regardless of depth.
    - H1 headings that are not front matter are kept only when they carry a
      recognisable chapter/section number; this suppresses cover-page noise.
    - H2/H3 headings whose title starts with a lowercase letter are dropped —
      these are almost always OCR artefacts (truncated first character).
    - H2 and H3 headings are kept when their level <= depth.
    """
    result: list[Heading] = []
    for i, h in enumerate(headings):
        level = h.level

        if _is_front_matter(h.title):
            result.append(Heading(level=1, title=h.title, page=h.page))
            continue

        # L1 entries without chapter numbers are usually cover-page noise,
        # but keep them when they head a subtree (Dutton's "Cavernous Sinus"
        # etc. each parents 5+ L2/L3 entries).
        if level == 1 and not _has_chapter_number(h.title) and not _has_descendants(headings, i):
            continue

        # OCR artefact: real headings start with an uppercase letter or digit
        if level > 1 and h.title and h.title[0].islower():
            continue

        # Author / credential attribution lines (e.g. "JOHN SMITH, MD, FACS")
        # are suppressed at depth < 3; they appear under Foreword/Preface sections.
        if level > 1 and depth < 3 and _is_credential_name(h.title):
            continue

        if level <= depth:
            result.append(h)

    # Deduplicate headings at the same level with identical titles on adjacent
    # pages.  Medical textbooks often repeat the chapter title on the facing
    # page; keeping both produces doubled bookmarks in the PDF panel.
    # Track the most-recent heading seen at each level (H2 entries between two
    # H1 entries must not prevent the H1 comparison).
    deduped: list[Heading] = []
    last_at_level: dict[int, Heading] = {}
    for h in result:
        prev = last_at_level.get(h.level)
        if (prev is not None
                and _dedup_key(prev.title) == _dedup_key(h.title)
                and h.page - prev.page <= 2):
            continue
        deduped.append(h)
        last_at_level[h.level] = h

    return deduped


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def run(args: argparse.Namespace) -> int:
    if not args.dry_run and args.output is None:
        print("[main] ERROR: OUTPUT path is required unless --dry-run is specified.")
        return 1

    use_llm = None
    if args.llm:
        from llm_classifier import build_classifier
        use_llm = build_classifier(
            model=args.model,
            base_url=args.ollama_url,
            verbose=args.verbose,
        )
        if use_llm is None:
            print("[main] Continuing without LLM classification.")

    if args.verbose:
        print(f"[main] Extracting outline from: {args.input}")

    raw_headings = extract_outline(args.input, use_llm=use_llm, verbose=args.verbose)

    headings = apply_depth_filter(raw_headings, args.depth)

    if not headings:
        print("[main] WARNING: No headings detected after depth filtering.")
    else:
        print(f"[main] Detected {len(headings)} heading(s) at depth <= {args.depth} "
              f"(raw: {len(raw_headings)}).")

    if args.dry_run:
        page_start = page_end = None
        if args.pages:
            parts = args.pages.split("-")
            page_start = int(parts[0])
            page_end = int(parts[1]) if len(parts) > 1 else page_start

        label = f"depth={args.depth}"
        if page_start is not None:
            label += f", pages {page_start}-{page_end}"
        print(f"\n--- Headings ({label}) ---")
        for h in headings:
            pg = h.page + 1
            if page_start is not None and not (page_start <= pg <= page_end):
                continue
            indent = "  " * (h.level - 1)
            title = h.title[:90].encode("ascii", "replace").decode()
            print(f"{indent}H{h.level} p{pg}: {title}")
        return 0

    if args.verbose:
        for h in headings:
            indent = "  " * (h.level - 1)
            title = h.title[:70].encode("ascii", "replace").decode()
            print(f"  {indent}H{h.level} p{h.page + 1}: {title}")

    write_outline(args.input, args.output, headings, verbose=args.verbose)
    print(f"[main] Done -> {args.output}")
    return 0


def main() -> None:
    args = parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
