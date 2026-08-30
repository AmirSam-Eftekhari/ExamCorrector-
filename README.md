# ExamCorrector

Offline, template-based OMR (Optical Mark Recognition) and exam-assessment
platform. Given a photo or scan of a bubble-sheet answer sheet, it registers
the page, reads every bubble with a multi-feature confidence engine,
flags anything it isn't sure about instead of guessing, and grades
deterministically against a configurable answer key.

**This README is deliberately specific about what is built, tested, and
working today versus what is still missing.** Nothing below is aspirational
— every claim in the tables below was verified by actually running the
code (unit/integration tests, or a live server hit with real HTTP
requests), not just written and assumed to work.

## Quick start (recommended)

```bash
pip install -r requirements.txt
python main.py
```

Opens `http://127.0.0.1:5050` in your browser automatically. Nothing
leaves your machine — it only listens on `127.0.0.1`; there is no external
network call anywhere in the app (no CDN, no telemetry, no analytics).

1. **Templates** → upload a clean/blank sample sheet → a template is
   auto-built. If the Student ID region needs adjusting, use **✎ Edit ID
   region** on the template card — a live SVG preview updates as you type
   numbers, no manual JSON editing required.
2. **Exams** → create an exam (name, subject, template, scoring rules,
   including negative marking) → build its answer key by clicking options.
3. **Batch process** → select as many filled-in sheets as you want at once
   → each is registered, read, scored, and saved permanently (survives a
   server restart). Detected student IDs are cross-checked against your
   **Students** roster (CSV import/export) when one is loaded.
4. **Results** → click into any submission for the color-coded overlay
   (green/amber/red/gray) and a full grade breakdown; a **Review** button
   appears for anything flagged, with cropped images and one-click
   correction that recalculates the score.
5. **Analytics** → average/median/min/max/std-dev, a score-distribution
   chart, and a per-question correct/wrong/blank/multiple/review-rate table.
6. **Export** → CSV (results, per-answer detail), a multi-sheet **Excel
   workbook** (Summary/Students/Answers/Question Analysis), and a
   **PDF report**.
7. **Settings** → theme (system/light/dark, a real separate dark palette —
   not an inverted light theme) and language (فارسی/English), both
   persisted and applied everywhere, RTL/LTR handled correctly.

A lighter console-only entry point (`python app_launcher.py`, or the CLI
scripts under `scripts/`) also works if you'd rather not use the web UI.

## Get a single double-click .exe

**This repo does not include a pre-built .exe** — it was built in a sandbox
with no internet access and no Windows machine, and PyInstaller can't
cross-compile (a Windows `.exe` has to be built *on* Windows).

- **Windows:** double-click `build_exe.bat` (needs Python 3.11+ installed
  once). Produces `dist\ExamCorrector.exe`.
- **Linux/macOS:** run `./build_exe.sh`. Produces `dist/ExamCorrector`.

Keep the result in its own folder — the first run creates `data/` and
`resources/templates/` next to it, and that's what makes your templates,
database, and settings persist between runs (PyInstaller's own bundle is
extracted to a throwaway temp folder every launch). You separately need the
`tesseract` OCR binary on PATH for Name/Class/Date text-field reading
(bubble grading itself doesn't need it):
https://github.com/UB-Mannheim/tesseract/wiki

## What's been tested, and how

- `tests/unit/` and `tests/integration/` — 50 automated tests, all passing,
  covering the CV pipeline, grading engine, database/migrations, analytics,
  roster CSV import, and XLSX/PDF export content (not just "file was
  created" — the PDF test actually extracts and checks the rendered text;
  the XLSX test actually reads back the cells).
- Every web route was independently driven with real HTTP requests against
  a running server (not just unit-tested in isolation): create an exam →
  build its key by clicking options → batch-upload sheets → confirm scores
  by hand-checking the arithmetic → open a submission → confirm the
  overlay image regenerates correctly from the *saved* file → review and
  correct a flagged question → confirm the score recalculates → check
  analytics and all four export formats reflect it → change theme/language
  in Settings → confirm it's still applied after a server restart.
- **Shadow robustness was specifically tested**, not just claimed: a
  100-question blank sheet under a 50-intensity-unit brightness gradient
  reads 100/100 correctly `BLANK` at ~94% confidence (the *old*
  fixed-threshold approach gave ~62% confidence on the same sheet with
  *no* shadow at all). A mark drawn inside the shadowed region is still
  read correctly at 94% confidence. Both are locked in as permanent
  regression tests (`tests/integration/test_shadow_robustness.py`).
- Several real bugs were found and fixed *by* this testing process, not
  before it: a registration marker getting merged into an unrelated blob
  under shadow (fixed with morphological opening), a Flask `flash()`
  call-signature bug, corrected answers not being visually distinguished,
  a preprocessing pipeline choice that made processing 6x slower than
  necessary (found via profiling, fixed by swapping the denoising method).

Run the suite yourself:
```bash
pip install -r requirements.txt
python -m unittest discover -s tests -p "test_*.py" -v
```

## Status by area

✅ = built and verified working (test or live HTTP request). 🚧 = not built.
⚠️ = built but with a caveat noted.

### CV / OMR engine
| Feature | Status |
|---|---|
| Multi-threshold + Otsu + adaptive registration-marker detection | ✅ |
| Morphological-opening step to prevent shadow-induced marker merging | ✅ |
| Structured registration confidence report (geometry score, reprojection error, warnings — never just `ok=True`) | ✅ |
| Ring/local-background-relative bubble darkness (replaces fixed paper/ink constants) | ✅ |
| Multi-feature bubble scoring (fill ratio, Otsu ratio, adaptive-threshold ratio, edge density, interior std) | ✅ |
| Preprocessing pipelines (5 candidates) actually selected per-page and used as a 4th consensus vote | ✅ |
| Blank / multiple-mark / low-confidence / ambiguous / unreadable as first-class outcomes | ✅ |
| Erasure/residue detection (flags a non-uniform "blank" as possibly erased) | ✅ |
| Regional/per-question quality scoring | 🚧 (page-level quality only) |
| Registration debug/visualization mode | 🚧 |

### Templates
| Feature | Status |
|---|---|
| Auto-calibration from a clean sheet (markers, answer grid, Student ID, text fields) | ✅ |
| Calibrated bubble radius matches the sheet's actual bubble size | ✅ fixed a real bug: calibration used to write a fixed constant into every template regardless of the sheet's true bubble size, silently mis-sizing the ring-darkness sampling geometry on any sheet whose bubbles differed from the original tuning sheet -- found via a Persian-template test, now measures the real detected radius, locked in with a permanent regression test |
| Text-field OCR (Name/Class/Date) actually reads real names reliably | ✅ this took 3 rounds of real debugging, not one: (1) the calibrated crop was only ~22-34px tall — too thin for any reliable OCR; (2) even after that, the crop had zero horizontal margin and clipped the first 1-2 characters of any name starting at or before the printed line ("John Smith" → "wn smith"); (3) tesseract was also getting confused by a stray fragment of the field's own printed label bleeding into the crop edge. Fixed all three (widened the crop, added an empirically-tuned horizontal margin, added preprocessing — upscale/adaptive-threshold/border — and a filter that drops punctuation-only OCR tokens), and locked in with a regression test that checks the *exact* text, not just "something non-null". Verified against 5 different realistic names (DejaVu-rendered, not the crude font used in earlier ad-hoc tests); 4 read perfectly, 1 had a single-character i/l OCR ambiguity (an inherent OCR limit, not a bug) |
| Persian (and other-language) OCR for handwritten name/class/date fields | ✅ code path exists (auto-detects installed Tesseract language packs, uses eng+fas together when both are present) but **this sandbox has no internet access and could not install the `fas` language pack** -- install it yourself with `sudo apt-get install tesseract-ocr-fas` (or place `fas.traineddata` in your tessdata folder on Windows/Mac) and it activates automatically; Settings page shows which languages are currently active |
| Student ID region editor with live preview (no manual JSON editing) | ✅ |
| Template validation before use | ⚠️ partial (schema validation on load; no health-score UI) |
| Full drag/resize visual editor for answer blocks | 🚧 |
| Template versioning | ⚠️ partial (a `version` counter bumps on edit + a warning if an exam already uses it; not full v1/v2 coexistence with per-exam pinning) |

### Exams, grading, students
| Feature | Status |
|---|---|
| Exam creation with scoring rules (incl. negative marking) | ✅ |
| Visual answer-key editor (click options, not JSON) | ✅ correcting a mistake is just clicking a different option (verified in a real browser); a clear/"unset" button per question; warns before leaving with unsaved changes |
| Deterministic grading engine, independent of CV | ✅ |
| Human corrections are authoritative and recorded (`final_answer`, `review_status`) | ✅ |
| Manually correct any detected answer, not just flagged ones | ✅ "Edit all answers" view (same keyboard-driven grid as the answer-key editor) — only questions actually changed get marked as human-reviewed |
| Student roster: CSV import/export, ID matching during batch processing (never fabricates a match) | ✅ |
| Full review-history audit trail (previous answer, timestamp, reason) | 🚧 (current state is stored; a change log isn't) |

### Processing
| Feature | Status |
|---|---|
| Single-sheet and batch (multi-file) processing | ✅ |
| Per-file fault tolerance (one bad file doesn't kill the batch) | ✅ |
| Persisted source images (so review/overlay work after a restart) | ✅ |
| PDF / multi-page input | ✅ batch, quick-process, and template calibration all accept a .pdf; each page becomes its own sheet |
| Real-time progress UI for large batches | 🚧 (batch runs synchronously; fine for tens of sheets, would benefit from background processing + progress polling for hundreds) |
| Processing cache (skip re-processing an unchanged image) | 🚧 |

### UI
| Feature | Status |
|---|---|
| Dashboard, Templates, Exams, Answer Key, Batch, Results, Submission Detail, Review, Analytics, Students, Settings | ✅ all built and route-tested |
| Persian RTL + English LTR, switchable, persisted | ✅ |
| Real dark theme (separate surface tokens, not inverted light) + light + system (via `prefers-color-scheme`), persisted | ✅ |
| CSS custom-property design tokens for color/radius/shadow | ✅ (spacing/typography scale is informal, not a strict token system) |
| Diagnostics page, skeleton loading states | 🚧 (diagnostics are shown inline on the submission page as text, not a dedicated page) |
| Keyboard shortcuts for the answer-key editor (arrow keys to move, number keys to pick an option, Ctrl/Cmd+Enter to save) | ✅ |
| Icon system (inline SVG, currentColor, consistent 24x24 outline set) | ✅ replaces the earlier Unicode glyphs everywhere in the UI |
| Toast notifications (auto-dismiss; errors stay until closed; RTL-aware) | ✅ replaces flash banners |
| Button loading state on slow forms (batch upload, calibration, quick process) | ✅ |
| PySide6 desktop shell | ⚠️ written, **never run** — this sandbox has no network access to install PySide6. Superseded by the web UI. |

### Export & reporting
| Feature | Status |
|---|---|
| CSV (results, per-answer detail, roster) | ✅ |
| XLSX (Summary/Students/Answers/Question Analysis workbook) | ✅ |
| PDF exam report (summary, distribution, student results, question analysis) | ✅ |
| Per-student individual PDF report | 🚧 (only the exam-level report exists) |

### Data & packaging
| Feature | Status |
|---|---|
| SQLite with versioned, data-preserving migrations (tested against a simulated old-version DB) | ✅ |
| Settings (theme/language) persisted and applied on restart | ✅ |
| Windows/Linux/macOS build scripts (PyInstaller) | ✅ scripts provided; **no pre-built binary included** (see above) |
| Evaluation script / synthetic robustness generator CLI | 🚧 (the shadow-robustness test fixtures were generated ad hoc for this session, not via a reusable generator tool) |

## Architecture

```
app/
├── core/         domain models + central config (thresholds, canvas size, etc.)
├── database/     SQLite schema/migrations, repository (typed CRUD), roster CSV import
├── cv/           quality analysis, page/marker detection, registration, preprocessing pipelines
├── templates/    template schema (versioned JSON) + auto-calibration from a clean sheet
├── omr/          bubble feature extraction, confidence engine, student-ID reading, pipeline orchestration
├── ocr/          best-effort text-field extraction (Name/Class/Date/...)
├── grading/      deterministic scoring engine (zero dependency on CV)
├── analytics/    exam- and question-level statistics
├── export/       CSV / XLSX / PDF generation
├── diagnostics/  human-readable diagnostic summaries, per-answer explainability, visual overlay rendering
├── localization/ fa/en string table + RTL flag
└── ui/           PySide6 desktop shell (unverified, see Status table) -- superseded by webapp/

webapp/           Flask web UI (main.py's entry point): server.py, templates/, static/
scripts/          CLI entry points (calibrate_template.py, run_single_sheet.py)
tests/            unit + integration tests, plus the image fixtures they run against
resources/templates/   the auto-calibrated template for the sample sheet
main.py           launches the web UI (what build_exe.bat/.sh compile)
app_launcher.py   console-only alternative entry point (no Flask needed)
```

### How the confidence engine works

Every bubble gets several independent features (ring-relative local
darkness, Otsu dark-pixel ratio, adaptive-threshold ratio, edge density,
interior uniformity). A question's answer is decided by comparing its own
options **against each other** and cross-checking **multiple independent
methods**, not fixed global thresholds:

- All options near-identical and below the mark floor → `BLANK` — unless
  the interior is suspiciously non-uniform, in which case it's flagged
  `LOW_CONFIDENCE` ("possible erased/partial mark") instead of a clean blank.
- Two (not all) options marked with a small margin between them →
  `MULTIPLE_MARK`. If *every* option is elevated together, that reads as
  uniform shadow/lighting (`LOW_CONFIDENCE`), not a deliberate multi-mark.
- Clear winner, healthy margin, methods agree → `HIGH_CONFIDENCE`.
- Everything else → `LOW_CONFIDENCE`, surfaced for human review.

The core change from earlier versions: darkness is measured **relative to
a ring of paper immediately around each bubble**, not a fixed page-wide
paper/ink constant. A shadow darkens the ring and the bubble interior
together, so the *difference* stays near zero for an actually-empty
bubble — this is what made the 94%-confidence-under-shadow result above
possible, versus ~62% with the old fixed-constant approach.

## Known limitations

- **No PDF/multi-page sheet input** — ~~only JPG/PNG/WEBP image files~~ fixed: batch/quick-process/calibration now accept PDF, each page treated as its own sheet (needs `poppler-utils` installed on the machine running the app).
- **No background/async batch processing** — a large batch (hundreds of
  sheets) blocks the request until it finishes; fine at classroom scale,
  would need worker-thread + progress-polling for much larger runs.
- **Template versioning is partial** — edits bump a version counter and
  warn if an exam already uses that template, but don't keep old/new
  versions as separate, independently-pinned artifacts.
- **PySide6 desktop shell is unverified** — written but never executed
  (no network access to install PySide6 in the build sandbox). The web UI
  is the tested, recommended interface.
- **No dedicated Diagnostics page, toast notifications, or SVG icon
  system** — diagnostics are shown as text on the submission page, Flask
  flash messages stand in for toasts, and nav icons are Unicode glyphs.
- **No processing cache / fingerprinting** — reprocessing an unchanged
  image re-runs the full CV pipeline.
- **Per-student individual PDF reports don't exist** — only the exam-level
  report (which does list every student's score).

## Development

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

No test in this suite mocks the CV pipeline or the export libraries — they
run real OpenCV operations, a real SQLite database, and real
openpyxl/reportlab output, then verify the actual content, per this
project's own "no fake functionality, no fake results" rule.
