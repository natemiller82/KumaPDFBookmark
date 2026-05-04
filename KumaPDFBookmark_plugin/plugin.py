"""
InterfaceAction subclass — wires the "Add PDF Bookmarks" button/menu entry
into the Calibre GUI and drives the per-book processing loop.
"""
import os
import tempfile

from calibre.gui2.actions import InterfaceAction
from calibre.gui2 import error_dialog, info_dialog

try:
    from qt.core import QProgressDialog, QApplication
except ImportError:
    from PyQt5.Qt import QProgressDialog, QApplication


class KumaPDFBookmarkAction(InterfaceAction):
    name = 'KumaPDFBookmark'
    action_spec = (
        'Add PDF Bookmarks',
        None,
        "Detect and embed PDF bookmarks using auto-pdf-bookmarks",
        None,
    )
    popup_type = 1
    action_type = 'current'

    def genesis(self):
        # get_icons() is injected into plugin module scope by calibre's
        # plugin loader — it loads from the plugin ZIP via the resources
        # tuple in __init__.py.  Two-arg form (with plugin name) is
        # required by calibre 6+ for icon-theme support and is back-
        # compatible with calibre 5.
        icon = get_icons('images/icon.png', 'KumaPDFBookmark')
        self.qaction.setIcon(icon)
        self.qaction.triggered.connect(self.add_pdf_bookmarks)

    def initialization_complete(self):
        # Best-effort injection into the book-list right-click context menu.
        # Users can also add it manually via Preferences › Toolbars & menus.
        try:
            self.gui.library_view.context_menu.addAction(self.qaction)
        except Exception:
            pass

    def add_pdf_bookmarks(self):
        rows = self.gui.current_view().selectionModel().selectedRows()
        if not rows:
            return error_dialog(
                self.gui, 'No books selected',
                'Select at least one book first.', show=True,
            )

        model = self.gui.current_view().model()
        book_ids = [model.id(row) for row in rows]
        db = self.gui.current_db

        pdf_ids = [
            bid for bid in book_ids
            if 'PDF' in (db.formats(bid, index_is_id=True) or '')
        ]
        if not pdf_ids:
            return error_dialog(
                self.gui, 'No PDFs found',
                'None of the selected books have a PDF format attached.', show=True,
            )

        self._process(pdf_ids, db)

    def _process(self, book_ids, db):
        from calibre.gui2 import question_dialog
        from calibre_plugins.kumapdfbookmark.prefs import prefs
        from calibre_plugins.kumapdfbookmark.worker import BookmarkWorker, _ensure_fitz

        overwrite = prefs['overwrite']
        settings = {
            'depth':      prefs['depth'],
            'enable_llm': prefs['enable_llm'],
            'ollama_url': prefs['ollama_url'],
            'model_name': prefs['model_name'],
            # By the time worker runs, the user has either selected "always
            # overwrite" or accepted a prompt to replace existing bookmarks
            # (the 'never' branch in this method skips worker entirely).
            # Either way they expect fresh content, so tell the extractor to
            # bypass the existing outline rather than re-read it.
            'ignore_existing_outline': True,
        }

        # Ensure fitz is importable now so the per-book TOC check is instant.
        if overwrite != 'always':
            try:
                _ensure_fitz()
            except Exception:
                overwrite = 'always'  # can't check; proceed without restriction

        progress = QProgressDialog(
            'Adding bookmarks…', 'Cancel', 0, len(book_ids), self.gui,
        )
        progress.setWindowTitle('KumaPDFBookmark')
        progress.setMinimumDuration(0)
        progress.show()
        QApplication.processEvents()

        errors = []

        for i, bid in enumerate(book_ids):
            if progress.wasCanceled():
                break

            title = db.title(bid, index_is_id=True) or f'book {bid}'
            progress.setLabelText(f'Processing: {title}')
            progress.setValue(i)
            QApplication.processEvents()

            pdf_path = db.format_abspath(bid, 'PDF', index_is_id=True)
            if not pdf_path or not os.path.exists(pdf_path):
                errors.append(f'{title}: PDF not found on disk')
                continue

            # Overwrite check — skip or prompt when existing bookmarks are found.
            if overwrite != 'always':
                try:
                    import fitz
                    doc_check = fitz.open(pdf_path)
                    has_toc = bool(doc_check.get_toc())
                    doc_check.close()
                except Exception:
                    has_toc = False

                if has_toc:
                    if overwrite == 'never':
                        errors.append(f'{title}: already has bookmarks — skipped')
                        continue
                    elif not question_dialog(
                        self.gui,
                        'Existing bookmarks',
                        f'<b>{title}</b> already has bookmarks. Replace them?',
                    ):
                        continue

            fd, tmp = tempfile.mkstemp(suffix='.pdf')
            os.close(fd)

            worker = BookmarkWorker(pdf_path, tmp, settings)
            worker.run_sync()

            if worker.error:
                errors.append(f'{title}: {worker.error}')
                _unlink(tmp)
            else:
                if worker.count == 0:
                    errors.append(f'{title}: no headings detected — PDF unchanged')
                    _unlink(tmp)
                else:
                    db.add_format_with_hooks(bid, 'PDF', tmp, index_is_id=True)
                    _unlink(tmp)

        progress.setValue(len(book_ids))
        progress.close()

        if errors:
            error_dialog(
                self.gui, 'Completed with warnings',
                'The following issues occurred:\n\n' + '\n'.join(errors),
                show=True,
            )
        else:
            n = len(book_ids)
            info_dialog(
                self.gui, 'Done',
                f'Bookmarks added to {n} book{"s" if n != 1 else ""}.',
                show=True,
            )

        self.gui.current_view().model().refresh()


def _unlink(path):
    try:
        os.unlink(path)
    except OSError:
        pass
