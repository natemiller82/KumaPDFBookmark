"""
auto-pdf-bookmarks CLI entry point.

Usage examples:
    python main.py input.pdf output.pdf
    python main.py input.pdf output.pdf --llm --model mistral-nemo --verbose
"""
import argparse
import sys

from config import OLLAMA_BASE_URL, OLLAMA_DEFAULT_MODEL
from extractor import extract_outline
from writer import write_outline


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="auto-pdf-bookmarks",
        description="Detect and embed bookmarks in a PDF, optimised for medical textbooks.",
    )
    parser.add_argument("input", help="Path to the source PDF file.")
    parser.add_argument("output", help="Path for the output PDF with bookmarks.")
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


def run(args: argparse.Namespace) -> int:
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

    headings = extract_outline(args.input, use_llm=use_llm, verbose=args.verbose)

    if not headings:
        print("[main] WARNING: No headings detected. Output PDF will have no bookmarks.")
    else:
        print(f"[main] Detected {len(headings)} heading(s).")

    if args.verbose:
        for h in headings:
            indent = "  " * (h.level - 1)
            print(f"  {indent}H{h.level} p{h.page + 1}: {h.title[:70]}")

    write_outline(args.input, args.output, headings, verbose=args.verbose)
    print(f"[main] Done -> {args.output}")
    return 0


def main() -> None:
    args = parse_args()
    sys.exit(run(args))


if __name__ == "__main__":
    main()
