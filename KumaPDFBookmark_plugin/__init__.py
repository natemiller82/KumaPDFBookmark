# Calibre plugin entry point — declares the plugin to Calibre's loader.
from calibre.customize import InterfaceActionBase


class KumaPDFBookmarkPlugin(InterfaceActionBase):
    name                    = 'KumaPDFBookmark'
    description             = "Add PDF bookmarks to OCR'd medical textbooks"
    supported_platforms     = ['windows', 'osx', 'linux']
    author                  = 'KumaPDFBookmark'
    version                 = (1, 0, 0)
    minimum_calibre_version = (5, 0, 0)

    # Calibre lazy-loads the actual InterfaceAction from this string.
    actual_plugin = 'calibre_plugins.kumapdfbookmark.plugin:KumaPDFBookmarkAction'

    def is_customizable(self):
        return True

    def config_widget(self):
        from calibre_plugins.kumapdfbookmark.config import ConfigWidget
        return ConfigWidget()

    def save_settings(self, config_widget):
        config_widget.commit()
