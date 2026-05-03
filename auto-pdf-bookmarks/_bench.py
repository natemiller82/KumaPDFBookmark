"""
Test harness for the bookmark over-detection fix.

Runs main.py + validator.py against the fixture PDFs and prints a
single-line summary per fixture: bookmarks, missing-in-toc (warnings),
missing-in-bookmarks (errors), TOC entries parsed, and elapsed seconds.

Usage:
    python _bench.py LABEL [--only fixture_substring] [--skip-regen] [--quick]

    --quick  Run only the 3 representative fixtures (Davis, Dutton, Cheney)
             — fast iteration during development.

Outputs:
    <fixture>.<LABEL>.bookmarked.pdf
    <fixture>.<LABEL>.bookmarked.validation.json
    _bench.<LABEL>.summary.json
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
import time
from pathlib import Path

FIXTURE_DIR = r"C:\Users\MillerFam\KumaPDFBookmark"
HERE = Path(__file__).parent

FIXTURES = [
    ("Davis_Otoplasty",      r"Otoplasty_ Aesthetic and Recons - Jack Davis.pdf"),
    ("ATLS_11_Course",       r"ATLS 11th Edition Course Manua - American College Of Surgeons. C.pdf"),
    ("ATLS_10_Faculty",      r"ATLS 10th Edition Faculty ManualATLS 10th - American College Of Surgeons. Committee On.pdf"),
    ("ATLS_Legacy_2017",     r"Advanced Trauma Life Support_ S - American College Of Surgeons. C.pdf"),
    ("Janfaza_HeadAnatomy",  r"Surgical Anatomy of the Head an - Parviz Janfaza.pdf"),
    ("Dutton_Atlas",         r"Atlas of Clinical and Surgical - Jonathan J. Dutton.pdf"),
    ("Cheney_FacialSurgery", r"Facial Surgery_ Plastic and Reconstructive - Mack L. Cheney, M. D_.pdf"),
    ("Grabb_Flaps",          r"Grabb's Encyclopedia of Flaps_ - Berish Strauch.pdf"),
    ("Gubisch_Rhinoplasty",  r"Mastering Advanced Rhinoplasty - Wolfgang Gubisch.pdf"),
    ("Kaufman_FacialRecon",  r"Practical Facial Reconstruction - Dr. Andrew Kaufman M. D_.pdf"),
    ("Dedivitis_Laryngeal",  r"Laryngeal Cancer_ Clinical Case - Rogerio A. Dedivitis.pdf"),
]

# --quick subset — three representative shapes:
#   Davis    = no embedded outline (font-cluster path)
#   Dutton   = clean hierarchical outline
#   Cheney   = polluted outline (post-filter pressure test)
QUICK_FIXTURES = {"Davis_Otoplasty", "Dutton_Atlas", "Cheney_FacialSurgery"}


def run(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    p = subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, encoding="utf-8", errors="replace")
    return p.returncode, p.stdout, p.stderr


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: python _bench.py LABEL [--only substring] [--skip-regen] [--quick]")
        return 2
    label = sys.argv[1]
    only = None
    skip_regen = False
    quick = False
    args_iter = iter(sys.argv[2:])
    for a in args_iter:
        if a == "--skip-regen":
            skip_regen = True
        elif a == "--quick":
            quick = True
        elif a == "--only":
            only = next(args_iter, None)
        else:
            print(f"Unknown argument: {a}", file=sys.stderr)
            return 2

    if quick and only:
        print("--quick and --only are mutually exclusive.", file=sys.stderr)
        return 2

    results = []
    print(f"=== bench label={label}{' (quick)' if quick else ''} ===")
    for name, fname in FIXTURES:
        if quick and name not in QUICK_FIXTURES:
            continue
        if only and only.lower() not in name.lower():
            continue
        src = os.path.join(FIXTURE_DIR, fname)
        out_pdf = os.path.join(FIXTURE_DIR, f"{name}.{label}.bookmarked.pdf")
        if not os.path.isfile(src):
            print(f"[skip] {name}: source missing -> {src}")
            continue

        t0 = time.time()
        if not skip_regen or not os.path.isfile(out_pdf):
            rc, so, se = run(
                ["python", "main.py", src, out_pdf, "--depth", "2"],
                cwd=str(HERE),
            )
            if rc != 0:
                print(f"[FAIL gen] {name} rc={rc}")
                print((so or "")[-400:])
                print((se or "")[-400:])
                continue
        gen_secs = time.time() - t0

        t1 = time.time()
        rc, so, se = run(
            ["python", "validator.py", out_pdf, "--validation-format", "json", "--quiet"],
            cwd=str(HERE),
        )
        val_secs = time.time() - t1
        if rc != 0:
            print(f"[FAIL val] {name} rc={rc}")
            print((so or "")[-400:])
            print((se or "")[-400:])
            continue

        # Validator writes <pdf>.validation.json next to the PDF
        report_path = os.path.splitext(out_pdf)[0] + ".validation.json"
        try:
            with open(report_path, "r", encoding="utf-8") as f:
                report = json.load(f)
        except Exception as e:
            print(f"[FAIL parse] {name}: {e}")
            continue

        s = report.get("summary", {})
        tc = report.get("toc_check", {})
        rec = {
            "fixture": name,
            "label": label,
            "bookmarks": s.get("total_bookmarks", 0),
            "errors_missing_in_bookmarks": s.get("errors", 0),
            "warnings_missing_in_toc": s.get("warnings", 0),
            "toc_entries_parsed": tc.get("toc_entries_parsed", 0),
            "matched_count": tc.get("matched_count", 0),
            "gen_secs": round(gen_secs, 1),
            "val_secs": round(val_secs, 1),
            "report_path": report_path,
        }
        results.append(rec)
        print(f"  {name:24s}  bm={rec['bookmarks']:5d}  miss_bm(err)={rec['errors_missing_in_bookmarks']:4d}  "
              f"miss_toc(warn)={rec['warnings_missing_in_toc']:5d}  "
              f"toc={rec['toc_entries_parsed']:3d}/match={rec['matched_count']:3d}  "
              f"gen={rec['gen_secs']:5.1f}s  val={rec['val_secs']:4.1f}s")

    summary_path = HERE / f"_bench.{label}.summary.json"
    with open(summary_path, "w", encoding="utf-8") as f:
        json.dump(results, f, indent=2)
    print(f"\nSummary written to {summary_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
