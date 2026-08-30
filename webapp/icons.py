"""
A small, consistent SVG icon set (outline style: 24x24 viewBox, currentColor
stroke, rounded caps/joins -- in the spirit of Feather/Lucide icons) used
everywhere in the UI instead of ad-hoc Unicode glyphs (▦ ▤ ▥ ⚠ etc.), which
render inconsistently across fonts/platforms and were an explicitly flagged
gap. Registered as a Jinja global via `icon(name, size=18, cls="")` so every
template draws from the same set.
"""
from __future__ import annotations

from markupsafe import Markup

_PATHS: dict[str, str] = {
    "grid": '<rect x="3" y="3" width="7" height="7" rx="1.5"></rect>'
            '<rect x="14" y="3" width="7" height="7" rx="1.5"></rect>'
            '<rect x="14" y="14" width="7" height="7" rx="1.5"></rect>'
            '<rect x="3" y="14" width="7" height="7" rx="1.5"></rect>',
    "layers": '<polygon points="12 2 2 7 12 12 22 7 12 2"></polygon>'
              '<polyline points="2 17 12 22 22 17"></polyline>'
              '<polyline points="2 12 12 17 22 12"></polyline>',
    "clipboard": '<path d="M9 2h6a1 1 0 0 1 1 1v2H8V3a1 1 0 0 1 1-1z"></path>'
                 '<rect x="5" y="4" width="14" height="18" rx="2"></rect>'
                 '<line x1="9" y1="11" x2="15" y2="11"></line>'
                 '<line x1="9" y1="15" x2="15" y2="15"></line>',
    "users": '<path d="M17 21v-2a4 4 0 0 0-4-4H5a4 4 0 0 0-4 4v2"></path>'
             '<circle cx="9" cy="7" r="4"></circle>'
             '<path d="M23 21v-2a4 4 0 0 0-3-3.87"></path>'
             '<path d="M16 3.13a4 4 0 0 1 0 7.75"></path>',
    "upload": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
              '<polyline points="17 8 12 3 7 8"></polyline>'
              '<line x1="12" y1="3" x2="12" y2="15"></line>',
    "sliders": '<line x1="4" y1="21" x2="4" y2="14"></line><line x1="4" y1="10" x2="4" y2="3"></line>'
               '<line x1="12" y1="21" x2="12" y2="12"></line><line x1="12" y1="8" x2="12" y2="3"></line>'
               '<line x1="20" y1="21" x2="20" y2="16"></line><line x1="20" y1="12" x2="20" y2="3"></line>'
               '<line x1="1" y1="14" x2="7" y2="14"></line><line x1="9" y1="8" x2="15" y2="8"></line>'
               '<line x1="17" y1="16" x2="23" y2="16"></line>',
    "edit": '<path d="M12 20h9"></path><path d="M16.5 3.5a2.12 2.12 0 0 1 3 3L7 19l-4 1 1-4Z"></path>',
    "trash": '<polyline points="3 6 5 6 21 6"></polyline>'
             '<path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2"></path>'
             '<line x1="10" y1="11" x2="10" y2="17"></line><line x1="14" y1="11" x2="14" y2="17"></line>',
    "download": '<path d="M21 15v4a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2v-4"></path>'
                '<polyline points="7 10 12 15 17 10"></polyline>'
                '<line x1="12" y1="15" x2="12" y2="3"></line>',
    "check-circle": '<path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>'
                     '<polyline points="22 4 12 14.01 9 11.01"></polyline>',
    "alert-triangle": '<path d="M10.29 3.86 1.82 18a2 2 0 0 0 1.71 3h16.94a2 2 0 0 0 1.71-3L13.71 3.86a2 2 0 0 0-3.42 0Z"></path>'
                       '<line x1="12" y1="9" x2="12" y2="13"></line><line x1="12" y1="17" x2="12.01" y2="17"></line>',
    "x-circle": '<circle cx="12" cy="12" r="10"></circle>'
                '<line x1="15" y1="9" x2="9" y2="15"></line><line x1="9" y1="9" x2="15" y2="15"></line>',
    "x": '<line x1="18" y1="6" x2="6" y2="18"></line><line x1="6" y1="6" x2="18" y2="18"></line>',
    "plus": '<line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line>',
    "bar-chart": '<line x1="18" y1="20" x2="18" y2="10"></line>'
                 '<line x1="12" y1="20" x2="12" y2="4"></line><line x1="6" y1="20" x2="6" y2="14"></line>',
    "file-text": '<path d="M14 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V8Z"></path>'
                 '<polyline points="14 2 14 8 20 8"></polyline>'
                 '<line x1="16" y1="13" x2="8" y2="13"></line><line x1="16" y1="17" x2="8" y2="17"></line>',
    "file-spreadsheet": '<path d="M13 2H6a2 2 0 0 0-2 2v16a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2V9z"></path>'
                         '<polyline points="13 2 13 9 20 9"></polyline>'
                         '<line x1="8" y1="13" x2="16" y2="13"></line><line x1="8" y1="17" x2="16" y2="17"></line>',
    "image": '<rect x="3" y="3" width="18" height="18" rx="2"></rect>'
             '<circle cx="8.5" cy="8.5" r="1.5"></circle><polyline points="21 15 16 10 5 21"></polyline>',
    "eye": '<path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8Z"></path><circle cx="12" cy="12" r="3"></circle>',
    "inbox": '<polyline points="22 12 16 12 14 15 10 15 8 12 2 12"></polyline>'
             '<path d="M5.45 5.11 2 12v6a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2v-6l-3.45-6.89A2 2 0 0 0 16.76 4H7.24a2 2 0 0 0-1.79 1.11Z"></path>',
    "arrow-back": '<line x1="19" y1="12" x2="5" y2="12"></line><polyline points="12 19 5 12 12 5"></polyline>',
}


def icon(name: str, size: int = 18, cls: str = "") -> Markup:
    path = _PATHS.get(name)
    if path is None:
        return Markup("")
    classes = f"icon icon-{name} {cls}".strip()
    return Markup(
        f'<svg class="{classes}" width="{size}" height="{size}" viewBox="0 0 24 24" '
        f'fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" '
        f'stroke-linejoin="round" aria-hidden="true">{path}</svg>'
    )
