"""
Localization foundation.

This is intentionally a small, dependency-free string table rather than
compiled Qt .ts/.qm files -- generating .qm files requires the Qt Linguist
tools (lrelease), which need PySide6/Qt installed to run, and this sandbox
has no network access to install them. The lookup API below
(`tr(key, lang)`) is the seam: swapping in real .ts/.qm-based translation
later means changing this module's internals only, not any call site.

Every UI string used anywhere in app/ui must go through `tr()` -- never a
hard-coded literal (spec section 41).
"""
from __future__ import annotations

SUPPORTED_LANGUAGES = ("en", "fa", "ar")
RTL_LANGUAGES = {"fa", "ar"}

STRINGS: dict[str, dict[str, str]] = {
    "app_title": {"en": "ExamCorrector", "fa": "اگزم‌کارکتور", "ar": "إكزام كوركتور"},
    "nav.dashboard": {"en": "Dashboard", "fa": "داشبورد", "ar": "لوحة التحكم"},
    "nav.exams": {"en": "Exams", "fa": "آزمون‌ها", "ar": "الاختبارات"},
    "nav.students": {"en": "Students", "fa": "دانش‌آموزان", "ar": "الطلاب"},
    "nav.answer_keys": {"en": "Answer Keys", "fa": "کلید پاسخ‌ها", "ar": "مفاتيح الإجابة"},
    "nav.templates": {"en": "Templates", "fa": "قالب‌ها", "ar": "القوالب"},
    "nav.results": {"en": "Results", "fa": "نتایج", "ar": "النتائج"},
    "nav.reports": {"en": "Reports", "fa": "گزارش‌ها", "ar": "التقارير"},
    "nav.review_queue": {"en": "Review Queue", "fa": "صف بازبینی", "ar": "قائمة المراجعة"},
    "nav.settings": {"en": "Settings", "fa": "تنظیمات", "ar": "الإعدادات"},
    "action.new_exam": {"en": "+ New Exam", "fa": "+ آزمون جدید", "ar": "+ اختبار جديد"},
    "action.import_sheets": {"en": "Import Answer Sheets", "fa": "وارد کردن پاسخ‌برگ‌ها", "ar": "استيراد أوراق الإجابة"},
    "action.new_template": {"en": "+ New Template", "fa": "+ قالب جدید", "ar": "+ قالب جديد"},
    "empty.exams.title": {"en": "No exams yet.", "fa": "هنوز آزمونی ثبت نشده است.", "ar": "لا توجد اختبارات بعد."},
    "empty.exams.body": {"en": "Create your first exam to begin.", "fa": "برای شروع، اولین آزمون خود را بسازید.", "ar": "أنشئ اختبارك الأول للبدء."},
    "empty.templates.title": {"en": "No templates yet.", "fa": "هنوز قالبی ساخته نشده است.", "ar": "لا توجد قوالب بعد."},
    "empty.templates.body": {"en": "Import a clean sample sheet to auto-generate a template.", "fa": "یک پاسخ‌برگ خالی وارد کنید تا قالب به‌صورت خودکار ساخته شود.", "ar": "استورد نموذج ورقة فارغة لإنشاء قالب تلقائيًا."},
    "empty.review_queue.title": {"en": "Nothing needs review right now.", "fa": "در حال حاضر چیزی برای بازبینی وجود ندارد.", "ar": "لا يوجد شيء يحتاج إلى مراجعة الآن."},
    "status.high_confidence": {"en": "High confidence", "fa": "اطمینان بالا", "ar": "ثقة عالية"},
    "status.low_confidence": {"en": "Low confidence", "fa": "اطمینان پایین", "ar": "ثقة منخفضة"},
    "status.blank": {"en": "Blank", "fa": "خالی", "ar": "فارغ"},
    "status.multiple_mark": {"en": "Multiple marks", "fa": "چند علامت", "ar": "علامات متعددة"},
    "theme.light": {"en": "Light", "fa": "روشن", "ar": "فاتح"},
    "theme.dark": {"en": "Dark", "fa": "تیره", "ar": "داكن"},
    "theme.gray": {"en": "Gray", "fa": "خاکستری", "ar": "رمادي"},
    "theme.system": {"en": "System", "fa": "سیستم", "ar": "النظام"},
}


def tr(key: str, lang: str = "en") -> str:
    entry = STRINGS.get(key)
    if entry is None:
        return key  # never crash the UI over a missing translation
    return entry.get(lang, entry.get("en", key))


def is_rtl(lang: str) -> bool:
    return lang in RTL_LANGUAGES
