# ExamCorrector

**Offline, template-based OMR and exam assessment platform** for reading bubble-sheet answer forms, detecting uncertain marks, grading against an answer key, reviewing results, and exporting reports.

> **If the image does not contain enough evidence for a reliable answer, ExamCorrector flags it for review instead of guessing.**

---

## ✨ Highlights

* 📄 Template-based OMR with fiducial-marker registration and perspective correction
* 🔍 Multi-feature bubble analysis with local ring-relative measurements
* 🛡️ Conservative confidence engine — `BLANK`, `MULTIPLE_MARK`, `LOW_CONFIDENCE`, `AMBIGUOUS`, `UNREADABLE`
* 🧠 Optional OCR for Name, Class, Date, and other text fields
* 🎯 Automatic template calibration and Student-ID region editor
* 📊 Deterministic grading with configurable negative marking
* 👤 Student roster management and conservative ID matching
* 🔄 Batch processing with per-file fault tolerance
* 📑 PDF, CSV, XLSX exports
* 📈 Exam and question-level analytics
* 🌐 Persian RTL and English LTR interface
* 🌓 Light, dark, and system themes
* 💻 Local web application with CLI utilities
* 🧪 Automated unit and integration tests
* ⚙️ GitHub Actions CI
* 📦 PyInstaller build scripts for Windows, Linux, and macOS

---

## 🏗️ Architecture

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

The project is organized into independent layers for computer vision, OMR, grading, database persistence, OCR, analytics, exports, templates, and the web interface.

---

## 🚀 Quick Start

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

### 3. Install dependencies

```bash
pip install -r requirements.txt
```

### 4. Run

```bash
python main.py
```

The local web application runs at:

```text
http://127.0.0.1:5050
```

---

## 🧪 Testing

Run the test suite:

```bash
python -m pytest -q
```

The test suite covers real OpenCV processing, SQLite persistence, grading, template calibration, analytics, and PDF/XLSX generation.

Current baseline:

```text
52 passed
```

---

## 🖨️ OCR & PDF Requirements

**Tesseract** is optional and is only required for free-text OCR fields.

**Poppler** is required for PDF input.

OMR bubble recognition does **not** require Tesseract.

---

## 🛠️ Tech Stack

**Language:** Python

**Computer Vision:** OpenCV, NumPy

**OCR:** Tesseract / pytesseract

**Web:** Flask, HTML, CSS, JavaScript

**Desktop:** PySide6

**Database:** SQLite

**Exports:** ReportLab, OpenPyXL, CSV

**Testing:** pytest / unittest

**Build:** PyInstaller

**CI:** GitHub Actions

---

## 📁 Project Structure

```text
ExamCorrector/
├── app/                 Core application modules
├── webapp/              Flask web interface
├── resources/           Templates and translations
├── scripts/             CLI utilities
├── tests/               Unit and integration tests
├── best-templates/      Example answer-sheet templates
├── main.py              Application entry point
├── app_launcher.py      Console launcher
├── requirements.txt
├── pyproject.toml
├── LICENSE
└── README.md
```

---

## 🔬 Project Status

**Version:** `0.1.x`

The core OMR, grading, database, analytics, export, template, and review workflows are implemented and covered by automated tests.

ExamCorrector is actively developed. Some advanced features — such as asynchronous large-scale batch processing, complete template versioning, full answer-block visual editing, and immutable review history — remain future work.

---

## 📄 License

MIT License © 2026 **Amirsam Eftekharinia**

See [`LICENSE`](LICENSE) for the full license text.

---

<p align="center">
  Built for reliable, local-first exam assessment.
</p>
