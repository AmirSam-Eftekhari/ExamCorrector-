from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QPushButton, QVBoxLayout, QWidget


class EmptyState(QWidget):
    def __init__(self, title: str, body: str, action_label: str | None = None, on_action=None, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(10)

        title_label = QLabel(title)
        title_label.setObjectName("EmptyTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        body_label = QLabel(body)
        body_label.setObjectName("EmptyBody")
        body_label.setAlignment(Qt.AlignmentFlag.AlignCenter)

        layout.addWidget(title_label)
        layout.addWidget(body_label)

        if action_label:
            button = QPushButton(action_label)
            button.setObjectName("Primary")
            button.setCursor(Qt.CursorShape.PointingHandCursor)
            if on_action:
                button.clicked.connect(on_action)
            layout.addSpacing(6)
            layout.addWidget(button, alignment=Qt.AlignmentFlag.AlignCenter)
