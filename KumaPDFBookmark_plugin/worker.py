"""
BookmarkWorker — runs extract_outline() → apply_depth_filter() → write_outline().

The linuxserver/calibre Docker image does not ship PyMuPDF.  _ensure_fitz()
pip-installs it on first use into a persistent directory under Calibre's
config_dir, then adds that directory to sys.path before extractor/writer
do `import fitz`.  pypdf is no longer needed (writer.py was migrated to
fitz upstream) so its bootstrap was removed along with the vendored copy.
"""
from __future__ import annotations

import os
import sys

_FITZ_READY = False   # module-level flag — pip runs only once per session


# ---------------------------------------------------------------------------
# Bootstrap helpers
# ---------------------------------------------------------------------------

def _ensure_fitz() -> None:
    """Guarantee fitz (PyMuPDF) is importable, installing it if necessary."""
    global _FITZ_READY
    if _FITZ_READY:
        return
    try:
        import fitz  # noqa: F401
        _FITZ_READY = True
        return
    except ImportError:
        pass

    import importlib
    from calibre.utils.config import config_dir

    deps_dir = os.path.join(config_dir, 'plugins', 'kumapdfbookmark_fitz')
    sentinel  = os.path.join(deps_dir, '.installed')

    if not os.path.exists(sentinel):
        os.makedirs(deps_dir, exist_ok=True)
        _pip_install('pymupdf', deps_dir)
        open(sentinel, 'w').close()

    if deps_dir not in sys.path:
        sys.path.insert(0, deps_dir)
    importlib.invalidate_caches()

    try:
        import fitz  # noqa: F401
    except ImportError:
        raise ImportError(
            "PyMuPDF (fitz) could not be loaded even after pip install. "
            "Run 'pip install pymupdf' inside the container and restart Calibre."
        )
    _FITZ_READY = True


def _pip_install(package: str, target: str) -> None:
    """Try several pip invocations; raise RuntimeError if all fail."""
    import shutil
    import subprocess

    candidates = [
        [sys.executable, '-m', 'pip'],
        [shutil.which('pip3') or ''],
        [shutil.which('pip')  or ''],
    ]
    last_exc: Exception | None = None
    for base in candidates:
        if not base[0]:
            continue
        cmd = base + ['install', package, '--target', target, '--no-deps', '-q']
        try:
            subprocess.check_call(cmd, timeout=300)
            return
        except Exception as exc:
            last_exc = exc

    raise RuntimeError(
        f"Could not install {package} via pip (last error: {last_exc}). "
        "Run 'pip install <package>' inside the container and restart Calibre."
    )


# ---------------------------------------------------------------------------
# Worker
# ---------------------------------------------------------------------------

class BookmarkWorker:
    def __init__(self, pdf_path: str, output_path: str, settings: dict) -> None:
        self.pdf_path    = pdf_path
        self.output_path = output_path
        self.settings    = settings
        self.error: str | None = None
        self.count: int = 0

    def run_sync(self) -> None:
        """Execute the pipeline; captures any exception into self.error."""
        try:
            self._run()
        except Exception as exc:
            self.error = str(exc)

    def _run(self) -> None:
        # Must run before importing extractor/writer, which both `import fitz`
        # at module load.
        _ensure_fitz()

        from calibre_plugins.kumapdfbookmark.extractor import extract_outline
        from calibre_plugins.kumapdfbookmark.filtering import apply_depth_filter
        from calibre_plugins.kumapdfbookmark.writer import write_outline

        use_llm = None
        if self.settings.get('enable_llm'):
            from calibre_plugins.kumapdfbookmark.llm_classifier import build_classifier
            use_llm = build_classifier(
                model=self.settings.get('model_name', 'mistral-nemo'),
                base_url=self.settings.get('ollama_url', 'http://localhost:11434'),
            )

        headings = extract_outline(
            self.pdf_path,
            use_llm=use_llm,
            ignore_existing_outline=self.settings.get('ignore_existing_outline', False),
        )
        filtered = apply_depth_filter(headings, self.settings.get('depth', 2))
        self.count = len(filtered)
        write_outline(self.pdf_path, self.output_path, filtered)
