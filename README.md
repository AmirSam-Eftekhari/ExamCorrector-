# ExamCorrector

**Offline, template-based OMR and exam assessment platform** for reading bubble-sheet answer forms, detecting uncertain marks, grading against an answer key, reviewing results, and exporting reports.

> **If the image does not contain enough evidence for a reliable answer, ExamCorrector flags it for review instead of guessing.**

ExamCorrector is built around a simple premise: the answer sheet should be the interface, not specialized scanning hardware. A normal printed page can be photographed or scanned, registered using four corner markers, processed locally, and graded deterministically.

---

## Why ExamCorrector?

Traditional manual grading becomes tedious quickly: a 30-student, 100-question class produces **3,000 answers** to mark.

Commercial OMR systems can solve the throughput problem, but may require dedicated scanners, proprietary forms, or recurring cloud services.

ExamCorrector takes a different approach:

- **Local-first:** processing happens on the machine running the application.
- **Ordinary paper:** answer sheets can be printed on a normal printer.
- **Camera-friendly:** the pipeline is designed for photographed pages, not only clean scanner images.
- **Conservative:** uncertainty is surfaced for human review instead of being silently converted into a guess.
- **Template-based:** layouts are explicit and calibratable rather than tied to one hard-coded sheet.

---

## ✨ Features

### Computer vision & OMR

- Four-corner fiducial-marker registration
- Homography-based perspective correction
- Local-background-relative bubble analysis
- Four independent bubble measurements:
  - fill ratio
  - Otsu-threshold ratio
  - adaptive-threshold ratio
  - edge density
- Conservative consensus/confidence handling
- Explicit states such as `BLANK`, `MULTIPLE_MARK`, `LOW_CONFIDENCE`, `AMBIGUOUS`, and `UNREADABLE`
- Detection of uneven/partially erased marks
- Shadow-robust processing
- Automatic template calibration
- Student-ID region editor

### Exam workflow

- Keyboard-driven answer-key editor
- Single-sheet and batch processing
- Multi-page PDF input
- Class roster import
- Student-ID based roster matching
- Manual review and correction queue
- Original machine reading retained alongside manual corrections
- Deterministic grading
- Configurable negative marking
- Configurable handling of blank and multiple-marked answers

### Reporting & analytics

- CSV export
- Multi-sheet XLSX export
- PDF reports
- Exam-level and question-level analytics
- Color-coded diagnostic views

### Interface

- Local Flask web application
- English and Persian interfaces
- Full RTL support for Persian
- Light, dark, and system themes
- CLI utilities for processing and calibration

---

## 🧠 Pipeline

```text
Input Image / PDF
       │
       ▼
Page Detection & Registration
       │
       ▼
Preprocessing Candidates
       │
       ▼
Bubble Analysis
       │
       ▼
Confidence Engine
       │
       ├── Reliable Answer
       ├── Blank
       ├── Multiple Mark
       └── Review Required
       │
       ▼
Student ID / OCR
       │
       ▼
Deterministic Grading
       │
       ▼
Database
       │
       ▼
Review • Analytics • Export
```

The implementation is separated into computer vision, OMR, grading, database, OCR, analytics, export, template, and web-interface layers.

---

## 🔬 Validation

The current project includes **52 automated unit and integration tests**, covering registration, OMR/bubble consensus, shadow robustness, template calibration, Student-ID geometry, grading, SQLite persistence, roster import, analytics, and PDF/XLSX export.

Current baseline:

```text
52 passed
```

The testing strategy deliberately includes independent checks for cases where a test can otherwise agree with the same faulty coordinate or geometry assumption as the code under test.

The project proposal documents the measured validation results and known limitations:

**[`docs/ExamCorrector_Project_Proposal.pdf`](docs/ExamCorrector_Project_Proposal.pdf)**

Selected measurements documented in the proposal include:

- **0.00 px** mean corner-marker reprojection error after registration across the test fixtures
- **93.3%** bubble-reading confidence retained under a simulated 50-unit directional lighting gradient
- **100 × 4** questions/options on the default configurable template

These figures are project-specific test results, not claims of universal real-world accuracy.

---

## 🚀 Quick Start

### Requirements

- Python **3.11+**
- For PDF input: Poppler
- For optional free-text OCR: Tesseract

OMR bubble recognition itself does **not** require Tesseract.

### 1. Clone

```bash
git clone https://github.com/AmirSam-Eftekhari/ExamCorrector-.git
cd ExamCorrector-
```

### 2. Create a virtual environment

**Windows**

```powershell
python -m venv .venv
.venv\Scripts\activate
```

**Linux / macOS**

```bash
python3 -m venv .venv
source .venv/bin/activate
```

### 3. Install Python dependencies

```bash
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 4. Run

```bash
python main.py
```

Then open:

```text
http://127.0.0.1:5050
```

The application is intentionally bound to localhost for local use.

### 5. Run tests

```bash
python -m pytest -q
```

---

## 🖨️ Printable templates

Ready-to-print templates are included in [`best-templates/`](best-templates/):

- English 100-question / 4-option A4 sheet
- Persian 100-question / 4-option A4 sheet
- Blank and filled examples
- A4 PDF versions

New layouts can be calibrated from a photograph of a blank page. The calibration workflow measures the grid geometry instead of requiring every coordinate to be hard-coded manually.

---

## 🛠️ Technology

| Area | Technology |
|---|---|
| Language | Python |
| Computer vision | OpenCV, NumPy |
| OCR | Tesseract / pytesseract |
| Web UI | Flask, HTML, CSS, JavaScript |
| Desktop UI | PySide6 |
| Database | SQLite |
| PDF | PyMuPDF, ReportLab, pdf2image |
| Spreadsheet | OpenPyXL |
| Testing | pytest / unittest |
| Packaging | PyInstaller |
| CI | GitHub Actions |

---

## 📁 Repository structure

```text
ExamCorrector/
├── app/
│   ├── analytics/
│   ├── core/
│   ├── cv/
│   ├── database/
│   ├── diagnostics/
│   ├── export/
│   ├── grading/
│   ├── localization/
│   ├── ocr/
│   ├── omr/
│   ├── settings/
│   ├── templates/
│   └── ui/
├── webapp/
├── resources/
├── scripts/
├── tests/
├── best-templates/
├── docs/
│   └── ExamCorrector_Project_Proposal.pdf
├── .github/
├── main.py
├── app_launcher.py
├── requirements.txt
├── pyproject.toml
├── LICENSE
├── CITATION.cff
├── SECURITY.md
└── README.md
```

Runtime data such as the SQLite database and uploaded sheets is intentionally excluded from the repository.

---

## 📌 Project status

**Version:** `0.1.0`  
**Status:** Active development

### Implemented

- Core registration and CV pipeline
- Bubble consensus and confidence handling
- Shadow robustness
- Exam workflow
- Roster matching
- Multi-format export
- Bilingual English/Persian interface with RTL support
- Template calibration
- Automated test suite
- GitHub Actions CI
- PyInstaller build scripts

### Still open

- Verified one-click desktop packaging across target operating systems
- Asynchronous background processing for larger batches
- Individual per-student report cards
- More general custom-template verification for non-standard Student-ID layouts
- Complete template versioning
- Full visual editing of answer blocks
- Immutable review history

---

## 📄 Project proposal

A full six-page project proposal is included in the repository:

**[`ExamCorrector Project Proposal`](docs/ExamCorrector_Project_Proposal.pdf)**

It describes the problem, architecture, validation methodology, current capabilities, measured results, and remaining work.

---

## 🤝 Contributing

Issues, bug reports, test cases, and pull requests are welcome.

When reporting an OMR issue, include:

1. the template used,
2. the type of input (photo, scan, PDF, etc.),
3. the expected reading,
4. the observed reading,
5. relevant logs or a minimal reproducible example when possible.

Do not upload real student records or other private educational data.

---

## 📜 License

MIT License © 2026 **Amirsam Eftekharinia**

See [`LICENSE`](LICENSE).

---

<p align="center">
  Built for reliable, local-first exam assessment.
</p>
