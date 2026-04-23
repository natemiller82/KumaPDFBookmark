"""
Plugin preferences (persisted via Calibre's JSONConfig) and the ConfigWidget
shown in Preferences › Plugins › KumaPDFBookmark › Customize.
"""
from calibre.utils.config import JSONConfig

try:
    from qt.core import (
        QWidget, QVBoxLayout, QFormLayout,
        QComboBox, QCheckBox, QLineEdit,
    )
except ImportError:
    from PyQt5.Qt import (
        QWidget, QVBoxLayout, QFormLayout,
        QComboBox, QCheckBox, QLineEdit,
    )

# ---------------------------------------------------------------------------
# Persistent prefs — shared by plugin.py and worker.py at runtime.
# ---------------------------------------------------------------------------

prefs = JSONConfig('plugins/kumapdfbookmark')
prefs.defaults['depth']      = 2
prefs.defaults['enable_llm'] = False
prefs.defaults['ollama_url'] = 'http://localhost:11434'
prefs.defaults['model_name'] = 'mistral-nemo'


# ---------------------------------------------------------------------------
# Config dialog widget
# ---------------------------------------------------------------------------

class ConfigWidget(QWidget):

    def __init__(self):
        QWidget.__init__(self)
        layout = QVBoxLayout(self)
        self.setLayout(layout)

        form = QFormLayout()
        layout.addLayout(form)

        # --- Depth selector ---
        self.depth_combo = QComboBox()
        self.depth_combo.addItem('1 — chapters only', 1)
        self.depth_combo.addItem('2 — chapters + sections (default)', 2)
        self.depth_combo.addItem('3 — chapters + sections + subsections', 3)
        idx = self.depth_combo.findData(prefs['depth'])
        if idx >= 0:
            self.depth_combo.setCurrentIndex(idx)
        form.addRow('Bookmark depth:', self.depth_combo)

        # --- LLM toggle ---
        self.llm_check = QCheckBox('Enable Ollama LLM for ambiguous headings')
        self.llm_check.setChecked(prefs['enable_llm'])
        form.addRow('LLM:', self.llm_check)

        # --- Ollama URL ---
        self.url_edit = QLineEdit(prefs['ollama_url'])
        self.url_edit.setPlaceholderText('http://localhost:11434')
        form.addRow('Ollama URL:', self.url_edit)

        # --- Model name ---
        self.model_edit = QLineEdit(prefs['model_name'])
        self.model_edit.setPlaceholderText('mistral-nemo')
        form.addRow('Model name:', self.model_edit)

        # Grey out LLM fields when toggle is off.
        self.llm_check.toggled.connect(self._on_llm_toggled)
        self._on_llm_toggled(prefs['enable_llm'])

    def _on_llm_toggled(self, checked):
        self.url_edit.setEnabled(checked)
        self.model_edit.setEnabled(checked)

    def commit(self):
        prefs['depth']      = self.depth_combo.currentData()
        prefs['enable_llm'] = self.llm_check.isChecked()
        prefs['ollama_url'] = self.url_edit.text().strip() or 'http://localhost:11434'
        prefs['model_name'] = self.model_edit.text().strip() or 'mistral-nemo'
