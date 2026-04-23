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
        from calibre_plugins.kumapdfbookmark.prefs import prefs
        from calibre_plugins.kumapdfbookmark.worker import BookmarkWorker

        settings = {
            'depth':      prefs['depth'],
            'enable_llm': prefs['enable_llm'],
            'ollama_url': prefs['ollama_url'],
            'model_name': prefs['model_name'],
        }

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
