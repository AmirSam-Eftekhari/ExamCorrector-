"""
Phase 1 shell: sidebar navigation + theme + localization, wired to empty
pages. This intentionally does NOT yet wire up exam creation, the template
editor, or the review center's crop viewer -- those are real, non-trivial
features (spec sections 8, 11, 26) that belong in later phases, and per
this project's own anti-pattern list a placeholder button that pretends to
do something it doesn't is worse than an honest empty state.

NOTE: this module requires PySide6, which could not be installed in the
sandbox this project was first built in (no network access there). It has
not been run. Install requirements and run `python main.py` locally to
exercise it, and treat this as a reviewed-but-unverified starting point.
"""
from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QApplication, QLabel, QListWidget, QListWidgetItem, QMainWindow,
    QStackedWidget, QStatusBar, QVBoxLayout, QWidget,
)

from app.core.config import AppConfig, DEFAULT_CONFIG
from app.localization.strings import tr, is_rtl
from app.ui.theme import build_stylesheet, resolve_system_theme
from app.ui.pages.empty_state import EmptyState

NAV_ITEMS = [
    ("dashboard", "nav.dashboard"),
    ("exams", "nav.exams"),
    ("students", "nav.students"),
    ("answer_keys", "nav.answer_keys"),
    ("templates", "nav.templates"),
    ("results", "nav.results"),
    ("reports", "nav.reports"),
    ("review_queue", "nav.review_queue"),
    ("settings", "nav.settings"),
]


class MainWindow(QMainWindow):
    def __init__(self, cfg: AppConfig = DEFAULT_CONFIG):
        super().__init__()
        self.cfg = cfg
        self.lang = cfg.language
        self.setWindowTitle(tr("app_title", self.lang))
        self.resize(1180, 760)

        rtl = is_rtl(self.lang)
        self.setLayoutDirection(Qt.LayoutDirection.RightToLeft if rtl else Qt.LayoutDirection.LeftToRight)

        central = QWidget()
        self.setCentralWidget(central)
        root_layout = QVBoxLayout(central)
        root_layout.setContentsMargins(0, 0, 0, 0)

        body = QWidget()
        body_layout = _row_layout(body, rtl)
        root_layout.addWidget(body)

        self.sidebar = self._build_sidebar()
        self.stack = QStackedWidget()
        self._page_index: dict[str, int] = {}
        self._build_pages()

        body_layout.addWidget(self.sidebar)
        body_layout.addWidget(self.stack, stretch=1)

        self.setStatusBar(QStatusBar())
        self._apply_theme(cfg.theme)

        self.sidebar_list.currentRowChanged.connect(self.stack.setCurrentIndex)
        self.sidebar_list.setCurrentRow(0)

    # -- construction -----------------------------------------------------
    def _build_sidebar(self) -> QWidget:
        sidebar = QWidget()
        sidebar.setObjectName("Sidebar")
        sidebar.setFixedWidth(220)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 12, 0, 12)

        self.sidebar_list = QListWidget()
        self.sidebar_list.setObjectName("NavList")
        for key, label_key in NAV_ITEMS:
            item = QListWidgetItem(tr(label_key, self.lang))
            item.setData(Qt.ItemDataRole.UserRole, key)
            self.sidebar_list.addItem(item)
        layout.addWidget(self.sidebar_list)
        return sidebar

    def _build_pages(self) -> None:
        pages = {
            "dashboard": EmptyState(
                tr("empty.exams.title", self.lang), tr("empty.exams.body", self.lang),
                action_label=tr("action.new_exam", self.lang),
            ),
            "exams": EmptyState(
                tr("empty.exams.title", self.lang), tr("empty.exams.body", self.lang),
                action_label=tr("action.new_exam", self.lang),
            ),
            "templates": EmptyState(
                tr("empty.templates.title", self.lang), tr("empty.templates.body", self.lang),
                action_label=tr("action.new_template", self.lang),
            ),
            "review_queue": EmptyState(
                tr("empty.review_queue.title", self.lang), "",
            ),
        }
        for key, _ in NAV_ITEMS:
            widget = pages.get(key) or self._placeholder_page(key)
            self._page_index[key] = self.stack.addWidget(widget)

    def _placeholder_page(self, key: str) -> QWidget:
        # Honest "not built yet" page rather than a button that does nothing.
        label = QLabel(f"{tr('nav.' + key, self.lang) if 'nav.' + key in _KNOWN else key}\n\n"
                        f"Not implemented in this phase.")
        label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        return label

    def _apply_theme(self, theme: str) -> None:
        resolved = resolve_system_theme() if theme == "system" else theme
        self.setStyleSheet(build_stylesheet(resolved, rtl=is_rtl(self.lang)))


_KNOWN = {k for _, k in NAV_ITEMS}


def _row_layout(widget: QWidget, rtl: bool):
    from PySide6.QtWidgets import QHBoxLayout
    layout = QHBoxLayout(widget)
    layout.setContentsMargins(0, 0, 0, 0)
    layout.setSpacing(0)
    if rtl:
        layout.setDirection(QHBoxLayout.Direction.RightToLeft)
    return layout


def run() -> int:
    app = QApplication([])
    window = MainWindow()
    window.show()
    return app.exec()
