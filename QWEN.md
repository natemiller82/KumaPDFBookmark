# KumaPDFBookmark - Qwen working rules

This repository has 3 lanes:

1. `main`
   - Canonical standalone CLI for PDF bookmark generation.
   - Do not add Calibre plugin code here.
   - Do not add Stirling-PDF integration code here except documentation that references integration branches.

2. `calibre-plugin`
   - Holds Calibre integration work.
   - Build a Calibre GUI plugin wrapper around the standalone CLI/library.
   - Keep the existing standalone CLI intact.

3. `stirling-sidecar`
   - Holds Stirling-PDF related work for this repository.
   - Build a FastAPI sidecar service and integration docs for Stirling.
   - Do not pretend Stirling supports a standalone plugin ZIP.
   - Native Stirling frontend/backend patches belong in a Stirling-PDF fork, not here.

General rules:
- Read README.md and the source tree before editing.
- Show a file-by-file plan before making changes.
- Prefer minimal, testable changes.
- Update README.md whenever behavior, layout, or installation changes.
- Run tests or validation commands after coding.
- Commit only when the tree is coherent.
- Never rewrite unrelated parts of the project.
