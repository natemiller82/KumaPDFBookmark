"""
auto-pdf-bookmarks CLI entry point.

Usage examples:
    python main.py input.pdf output.pdf
    python main.py input.pdf output.pdf --depth 2 --verbose
    python main.py input.pdf output.pdf --depth 1 --dry-run
    python main.py input.pdf output.pdf --llm --model mistral-nemo --verbose
"""
import argparse
import sys

from config import (
    CHAPTER_H1_RE,
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
    for h in headings:
        level = h.level

        if _is_front_matter(h.title):
            result.append(Heading(level=1, title=h.title, page=h.page))
            continue

        if level == 1 and not _has_chapter_number(h.title):
            continue

        # OCR artefact: real headings start with an uppercase letter or digit
        if level > 1 and h.title and h.title[0].islower():
            continue

        if level <= depth:
            result.append(h)

    return result


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
        print(f"\n--- Headings (depth={args.depth}) ---")
        for h in headings:
            indent = "  " * (h.level - 1)
            title = h.title[:90].encode("ascii", "replace").decode()
            print(f"{indent}H{h.level} p{h.page + 1}: {title}")
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
