"""
Session-0 diagnostic: embedded-outline survey for the 11 source fixtures.
Read-only. No source-code edits, no PDF mutation.

Output:
    C:\\Users\\MillerFam\\embedded_outline_survey.txt
"""
from __future__ import annotations
import os
import sys
from collections import Counter

import fitz  # PyMuPDF


FIXTURE_DIR = r"C:\Users\MillerFam\KumaPDFBookmark"
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


def survey_one(name: str, fname: str) -> str:
    path = os.path.join(FIXTURE_DIR, fname)
    out_lines = [f"=== {name} ===", f"Source: {fname}"]
    if not os.path.isfile(path):
        out_lines.append(f"ERROR: file not found")
        return "\n".join(out_lines) + "\n"
    out_lines.append(f"File size: {os.path.getsize(path):,} bytes "
                     f"({os.path.getsize(path)/1024/1024:.1f} MB)")
    try:
        doc = fitz.open(path)
    except Exception as e:
        out_lines.append(f"ERROR opening: {e}")
        return "\n".join(out_lines) + "\n"

    try:
        out_lines.append(f"Pages: {doc.page_count}")
        try:
            toc = doc.get_toc(simple=False)
        except Exception as e:
            out_lines.append(f"ERROR get_toc: {e}")
            toc = []
        out_lines.append(f"Embedded TOC entries: {len(toc)}")
        if toc:
            depth_hist = Counter(e[0] for e in toc)
            out_lines.append(f"Depth histogram: {dict(sorted(depth_hist.items()))}")
            out_lines.append("First 20 entries:")
            for e in toc[:20]:
                lvl, title, page = e[0], e[1], e[2]
                title_safe = (title or "").encode("ascii", "replace").decode()
                out_lines.append(f"  L{lvl} p{page:>5}: {title_safe[:90]}")
        else:
            out_lines.append("Depth histogram: {}")
            out_lines.append("First 20 entries: (no embedded TOC)")
    finally:
        doc.close()

    return "\n".join(out_lines) + "\n"


def main() -> int:
    out_path = r"C:\Users\MillerFam\embedded_outline_survey.txt"
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(f"Embedded outline survey — {len(FIXTURES)} fixtures\n")
        f.write("=" * 60 + "\n\n")
        for name, fname in FIXTURES:
            block = survey_one(name, fname)
            f.write(block + "\n")
            print(f"surveyed {name}")
    print(f"\nwrote {out_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
