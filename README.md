# ExamCorrector

**Offline, template-based OMR and exam assessment platform** for reading bubble-sheet answer forms, detecting uncertain marks instead of guessing, grading against an answer key, reviewing results, and exporting reports.

ExamCorrector is designed around a simple principle:

> **If the image does not contain enough evidence for a reliable answer, the system should flag it for review instead of inventing one.**

The application runs locally and its web UI listens on `127.0.0.1`. Student sheets, templates, results, and the SQLite database stay on the machine running the application.

---

## Highlights

- Template-based OMR with fiducial-marker registration and perspective correction
- Multi-feature bubble analysis rather than a single darkness threshold
- Local ring-relative darkness measurement for better shadow/lighting robustness
- Multiple preprocessing candidates with per-page selection and consensus
- Explicit outcomes for `BLANK`, `MULTIPLE_MARK`, `LOW_CONFIDENCE`, `AMBIGUOUS`, and `UNREADABLE`
- Student-ID recognition with confidence reporting
- Optional OCR for Name/Class/Date and other text fields
- Automatic template calibration from a clean answer sheet
- Visual Student-ID region editor
- Deterministic grading engine with configurable negative marking
- Human review and correction workflow
- Student roster import/export and conservative ID matching
- Batch processing with per-file fault tolerance
- PDF and multi-page PDF input
- CSV, XLSX, and PDF exports
- Exam/question analytics
- Persian RTL and English LTR UI
- Light, dark, and system themes
- CLI tools for calibration and single-sheet processing
- PyInstaller build scripts for Windows, Linux, and macOS
- Automated unit/integration test suite

---

## Current status

This repository is an actively developed **0.1.x** project. The core OMR, grading, database, analytics, and export paths are implemented and covered by automated tests.

The current test suite passes:

```text
52 passed
```

The tests exercise real OpenCV processing, SQLite persistence, OCR-dependent behavior where applicable, and actual XLSX/PDF generation rather than mocked output.

Some larger production features are intentionally still marked as planned; see [Known limitations](#known-limitations).

---

## Quick start

### 1. Clone the repository

```bash
git clone <your-repository-url>
cd ExamCorrector
```

### 2. Create a virtual environment

**Windows**

```powershell
python -m venv .venv
.venv\Scripts\activate
```

**Linux/macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
pip install -r requirements.txt
```

### 4. Start ExamCorrector

```bash
python main.py
```

The local web application starts on:

```text
http://127.0.0.1:5050
```

The browser is opened automatically by the application.

### Typical workflow

1. **Templates** — upload a clean/blank sample sheet and calibrate a template.
2. **Exams** — create an exam and select its template.
3. **Answer Key** — enter the correct options through the visual editor.
4. **Batch** — upload one or more completed answer sheets.
5. **Results** — inspect scores, confidence, diagnostics, and overlays.
6. **Review** — correct uncertain or incorrectly detected answers manually.
7. **Analytics** — inspect exam- and question-level statistics.
8. **Export** — generate CSV, Excel, or PDF reports.
9. **Students** — optionally import a roster for ID/name matching.
10. **Settings** — switch language and theme.

---

## OCR requirements

Bubble recognition **does not require Tesseract**.

Tesseract is only needed for free-text fields such as Name, Class, or Date.

The application automatically detects Tesseract in common installation locations. If it is not available, OCR fields are reported honestly as unavailable/unreadable rather than blocking OMR grading.

For Persian OCR, install the `fas` Tesseract language data in addition to the Tesseract engine.

The application automatically uses available language packs; it can combine English and Persian when both are installed.

---

## PDF input

PDF upload is supported for:

- Batch processing
- Quick/single-sheet processing
- Template calibration

Each PDF page is treated as an individual answer sheet.

PDF rendering uses `pdf2image`, which requires the **Poppler** command-line tools to be installed separately.

### Debian/Ubuntu

```bash
sudo apt-get install poppler-utils tesseract-ocr
```

For Persian OCR:

```bash
sudo apt-get install tesseract-ocr-fas
```

### Windows

Install Poppler and make its `bin` directory available on `PATH`.

Install Tesseract separately if text-field OCR is required.

---

## Command-line tools

### Interactive console launcher

```bash
python app_launcher.py
```

This provides a lightweight console workflow for:

- Template calibration
- Single-sheet processing
- Optional grading against an answer-key JSON
- Saving a machine-readable result JSON

### Calibrate a template

```bash
python scripts/calibrate_template.py path/to/clean_sheet.png --name "My Template"
```

### Process a single sheet

```bash
python scripts/run_single_sheet.py \
  path/to/sheet.png \
  --template resources/templates/default_100q_4opt.json \
  --answer-key path/to/key.json
```

Check the script `--help` output for the exact options supported by the current version.

---

## Building a standalone executable

The repository includes PyInstaller build scripts.

### Windows

Run on a Windows machine with Python 3.11+:

```text
build_exe.bat
```

Output:

```text
dist\ExamCorrector.exe
```

### Linux/macOS

```bash
chmod +x build_exe.sh
./build_exe.sh
```

Output:

```text
dist/ExamCorrector
```

PyInstaller builds for the operating system on which it runs; it does **not** cross-compile Windows executables from Linux/macOS.

The executable bundles the application and shipped templates. User data is intentionally stored outside the temporary PyInstaller bundle so that the SQLite database and user-created templates survive application restarts.

> Tesseract remains a separate system dependency for OCR text fields.

---

## Architecture

```text
ExamCorrector/
├── app/
│   ├── analytics/       Exam and question statistics
│   ├── core/            Domain models and central configuration
│   ├── cv/              Page detection, registration, preprocessing, quality
│   ├── database/        SQLite database, repository, roster import
│   ├── diagnostics/     Diagnostic summaries and annotated result images
│   ├── export/          CSV, XLSX and PDF export
│   ├── grading/         Deterministic grading engine
│   ├── localization/    Persian/English strings and RTL support
│   ├── ocr/             Optional text-field OCR
│   ├── omr/             Bubble analysis and OMR orchestration
│   ├── settings/        Application settings
│   ├── templates/       Template schema and auto-calibration
│   └── ui/              PySide6 desktop-shell code
│
├── webapp/
│   ├── server.py        Primary Flask application
│   ├── templates/       HTML templates
│   ├── static/          CSS/JS/assets
│   └── icons.py         Inline SVG icon system
│
├── resources/
│   ├── templates/       Shipped OMR templates
│   └── translations/    Resource translations
│
├── scripts/             CLI utilities
├── tests/
│   ├── unit/
│   ├── integration/
│   └── fixtures/
│
├── main.py              Primary application entry point
├── app_launcher.py      Lightweight console entry point
├── requirements.txt
├── pyproject.toml
├── build_exe.bat
├── build_exe.sh
└── README.md
```

### Processing pipeline

At a high level, a sheet follows this path:

```text
Input image/PDF
      │
      ▼
Page loading / PDF rendering
      │
      ▼
Fiducial-marker detection
      │
      ▼
Perspective correction / registration
      │
      ▼
Image-quality analysis
      │
      ▼
Candidate preprocessing pipelines
      │
      ▼
Bubble feature extraction
      │
      ▼
Per-question confidence analysis
      │
      ├── reliable answer
      ├── blank
      ├── multiple mark
      └── review-required state
      │
      ▼
Student ID + optional OCR fields
      │
      ▼
Deterministic grading
      │
      ▼
Database persistence
      │
      ▼
Review / analytics / export
```

---

## OMR confidence engine

The OMR engine intentionally avoids relying on one global threshold.

For each bubble, the system can consider features including:

- Local ring-relative darkness
- Fill ratio
- Otsu-based dark-pixel ratio
- Adaptive-threshold ratio
- Edge density
- Interior intensity variation

The answer analyzer then compares the options **within the same question** and considers agreement between independent measurements.

### Important behaviors

**Blank**

If all options are sufficiently similar and below the mark floor, the question is treated as blank.

**Multiple mark**

If multiple options show meaningful marks, the system reports `MULTIPLE_MARK` rather than choosing the strongest one.

**Low confidence / ambiguous**

If the evidence is insufficient or conflicting, the system reports a review state.

**Possible erasure/residue**

A nominally blank bubble with suspicious internal variation can be flagged instead of being silently accepted.

**High confidence**

A clear winner with adequate separation and supporting evidence can be promoted to `HIGH_CONFIDENCE`.

This architecture is deliberately conservative: a false "confident answer" is generally more damaging than a question sent to human review.

---

## Shadow and lighting robustness

A major part of the OMR implementation is handling uneven illumination.

Bubble darkness is measured relative to a local paper ring around each bubble instead of relying only on fixed page-wide paper/ink thresholds.

That means a shadow affecting both the bubble interior and its surrounding paper can largely cancel out in the local comparison.

The integration suite includes shadow-robustness fixtures to guard this behavior against regressions.

---

## Templates

Templates describe the logical layout of a registered answer sheet in normalized coordinates.

A template can contain:

- Fiducial registration configuration
- One or more answer blocks
- Question ranges
- Option labels
- Bubble geometry
- Student-ID region
- Free-text OCR fields
- Template revision metadata

### Auto-calibration

A clean sheet can be analyzed to estimate:

- Registration markers
- Answer blocks
- Question rows
- Option positions
- Bubble radius
- Student-ID geometry
- Text-field regions

Auto-calibration produces a JSON template that can then be inspected and adjusted.

### Student-ID editor

The web UI includes a Student-ID geometry editor with a live preview. This is preferable to manually editing JSON when a physical sheet needs a small geometry adjustment.

### Template caveat

The general auto-calibrator has limitations around unusual Student-ID layouts. The shipped default template uses explicitly measured geometry for its vertical Student-ID design, while custom layouts may require manual confirmation in the editor.

---

## Grading

The grading engine is intentionally independent of computer vision.

It operates on structured answer results and supports configurable:

- Correct-answer score
- Wrong-answer score
- Blank-answer score
- Multiple-mark policy
- Multiple-mark score

Supported multiple-mark policies include:

```text
wrong
invalid
manual_review
```

Human corrections become the authoritative final answer for the affected question and are reflected in recalculated results.

---

## Data storage

ExamCorrector uses SQLite for persistent application data.

Typical runtime data includes:

```text
data/
├── examcorrector.sqlite3
└── uploads/
```

The database stores application state such as:

- Exams
- Answer keys
- Students
- Submissions
- Detected answers
- Review/correction state
- Scores
- Settings

Source images are persisted so that review/overlay functionality can continue after a restart.

The `data/` directory and SQLite files are excluded from Git by `.gitignore`.

---

## Exports

The application can generate:

### CSV

- Exam results
- Per-answer detail
- Student roster

### Excel

A multi-sheet workbook containing:

- Summary
- Students
- Answers
- Question Analysis

### PDF

An exam-level report containing:

- Summary statistics
- Score distribution
- Student results
- Question analysis

Individual per-student PDF reports are not implemented yet.

---

## Localization and UI

The primary interface is a local Flask web application.

Supported interface languages:

- فارسی
- English

The UI handles:

- RTL/LTR layout
- Persistent language selection
- Light theme
- Dark theme
- System theme
- Keyboard navigation in the answer-key editor
- Loading states for slower operations
- Inline SVG icons
- Toast-style notifications

The PySide6 code under `app/ui/` is an additional desktop-shell implementation, but the **Flask web UI is the tested and recommended interface**.

---

## Testing

Run the complete test suite with:

```bash
python -m pytest -q
```

or:

```bash
python -m unittest discover -s tests -p "test_*.py" -v
```

The current suite covers:

- Page registration
- OMR answer detection
- Blank/multiple/low-confidence handling
- Shadow robustness
- Template calibration
- Grading arithmetic
- SQLite persistence and migrations
- Student roster import
- Analytics
- XLSX generation and content
- PDF generation and content

The suite uses real image-processing and export operations rather than replacing those systems with mocks.

---

## Known limitations

The following are intentionally not presented as finished features:

- **Large asynchronous batch processing:** batch processing currently runs synchronously. It is suitable for normal classroom-sized batches, but hundreds/thousands of sheets would benefit from a background worker and progress polling.
- **Processing cache:** unchanged images are not fingerprinted and skipped automatically.
- **Template versioning:** templates have revision metadata, but there is no complete version-pinning system that preserves multiple independently selectable revisions per exam.
- **Full visual answer-block editor:** Student-ID editing is available, but a full drag/resize editor for arbitrary answer blocks is not implemented.
- **Per-question image-quality scoring:** quality is currently assessed primarily at page level.
- **Dedicated diagnostics page:** diagnostics are available in submission/result views rather than as a separate diagnostics workspace.
- **Review-history audit log:** the current final correction/review state is persisted, but a complete immutable change history is not yet implemented.
- **Individual student PDF reports:** only exam-level PDF reporting is currently available.
- **Custom Student-ID auto-calibration:** unusual ID-grid layouts may require manual confirmation/adjustment.
- **OCR quality:** free-text OCR is inherently dependent on the image quality, handwriting, Tesseract version, and installed language data.

---

## Project principles

ExamCorrector follows a few engineering principles:

1. **Do not guess when the image is ambiguous.**
2. **Keep grading deterministic and independent from CV heuristics.**
3. **Persist enough information to reproduce and review decisions.**
4. **Prefer local measurements over brittle global thresholds.**
5. **Test real image-processing and export paths.**
6. **Keep experimental or incomplete functionality explicitly labeled instead of presenting it as production-ready.**

---

## License

No license is currently declared in this repository.

If you publish the project publicly, add a license file before accepting external contributions or redistributing the code.
