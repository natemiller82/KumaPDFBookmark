"""
BookmarkWorker — runs extract_outline() → apply_depth_filter() → write_outline()
against a single PDF.  All sibling modules are imported by flat name since they
live at the root of the plugin ZIP alongside this file.
"""
from __future__ import annotations


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
        from extractor import extract_outline
        from filtering import apply_depth_filter
        from writer import write_outline

        use_llm = None
        if self.settings.get('enable_llm'):
            from llm_classifier import build_classifier
            use_llm = build_classifier(
                model=self.settings.get('model_name', 'mistral-nemo'),
                base_url=self.settings.get('ollama_url', 'http://localhost:11434'),
            )

        headings = extract_outline(self.pdf_path, use_llm=use_llm)
        filtered = apply_depth_filter(headings, self.settings.get('depth', 2))
        self.count = len(filtered)
        write_outline(self.pdf_path, self.output_path, filtered)
