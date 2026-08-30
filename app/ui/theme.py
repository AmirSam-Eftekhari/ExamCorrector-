"""
Theme stylesheets. Plain Qt Style Sheets (QSS) so there's no extra
dependency -- consistent spacing/typography tokens are centralized here so
every page picks them up automatically instead of hand-rolling styles.
"""
from __future__ import annotations

_BASE = """
* { font-family: "Segoe UI", "Vazirmatn", "Noto Sans Arabic", sans-serif; font-size: 14px; }
QMainWindow { background: {bg}; }
QWidget#Sidebar { background: {sidebar_bg}; border-{side}: 1px solid {border}; }
QListWidget#NavList { background: transparent; border: none; padding: 8px; outline: 0; }
QListWidget#NavList::item { padding: 10px 14px; border-radius: 8px; color: {text}; margin-bottom: 2px; }
QListWidget#NavList::item:selected { background: {accent}; color: white; }
QListWidget#NavList::item:hover:!selected { background: {hover}; }
QWidget#PageHeader { background: transparent; }
QLabel#PageTitle { font-size: 20px; font-weight: 600; color: {text}; }
QLabel#EmptyTitle { font-size: 16px; font-weight: 600; color: {text}; }
QLabel#EmptyBody { color: {subtext}; }
QPushButton#Primary {
    background: {accent}; color: white; border: none; border-radius: 8px;
    padding: 9px 18px; font-weight: 600;
}
QPushButton#Primary:hover { background: {accent_hover}; }
QFrame#Card { background: {card_bg}; border: 1px solid {border}; border-radius: 10px; }
QStatusBar { background: {sidebar_bg}; color: {subtext}; }
"""

_PALETTES = {
    "light": dict(bg="#F5F6F8", sidebar_bg="#FFFFFF", border="#E3E5E8", text="#1B1F24",
                  subtext="#6B7280", accent="#2F6FED", accent_hover="#2559C7",
                  hover="#EEF2FF", card_bg="#FFFFFF"),
    "dark": dict(bg="#15171B", sidebar_bg="#1B1E23", border="#2A2E35", text="#E8EAED",
                 subtext="#9AA1AC", accent="#4C82F7", accent_hover="#3E6BD8",
                 hover="#232733", card_bg="#1E2126"),
    "gray": dict(bg="#EBEDEF", sidebar_bg="#DDE0E3", border="#C7CBD1", text="#20242A",
                 subtext="#565C66", accent="#3A5A9B", accent_hover="#2F4A80",
                 hover="#CDD2D8", card_bg="#F2F3F5"),
}


def build_stylesheet(theme: str, rtl: bool = False) -> str:
    palette = _PALETTES.get(theme, _PALETTES["light"])
    side = "left" if not rtl else "right"
    css = _BASE.format(side=side, **palette)
    return css


def resolve_system_theme() -> str:
    """Best-effort OS theme detection. Falls back to 'light' if unknown --
    real detection (QStyleHints.colorScheme()) is filled in once this runs
    inside an actual Qt application, not here."""
    return "light"
