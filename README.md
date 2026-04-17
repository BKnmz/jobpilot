# 🚀 JobPilot — AI-Powered Job Application Pipeline

> Scrape jobs → Score with AI → Tailor your CV → Apply smarter.
> **100% free. Runs locally. Your data never leaves your machine.**

![Python](https://img.shields.io/badge/Python-3.11+-blue) ![Gemini](https://img.shields.io/badge/Gemini_AI-Free_Tier-orange) ![Streamlit](https://img.shields.io/badge/UI-Streamlit-red) ![License](https://img.shields.io/badge/License-MIT-green)

---

## What It Does

JobPilot is a local desktop tool that automates the boring parts of job hunting:

| Step | What happens |
|------|-------------|
| 🔍 **Scrape** | Opens your LinkedIn/Stepstone search in Edge, scrapes all job listings |
| 🤖 **Score** | Gemini AI rates each job 1–10 against your CV, detects role fit |
| ✅ **Review** | You approve or reject in a clean dashboard — nothing auto-submitted |
| 📄 **CV Tailoring** | AI rewrites your summary & reorders bullets to match the job |
| 📤 **Apply** | Semi-automated form filler that stops before hitting Submit |

**Human approval at every step. No surprises.**

---

## Features

- **AI job scoring** — match score 1–10 + role profile detection (e.g. Cybersec / PO / BA)
- **6 base CVs** — pre-built for 3 role profiles × 2 languages (EN/DE), ready to send
- **Per-job CV tailoring** — Gemini rewrites your CV specifically for each job's JD
- **ATS-friendly .docx output** — clean Word doc, no LaTeX, no LibreOffice
- **Configurable profiles** — rename profiles, set separate CV files per profile
- **Smart scraping** — only opens newly-added search URLs, skips already-seen jobs
- **Certificate database** — import certs from PDFs, auto-included in CVs
- **Free forever** — uses Gemini 2.5 Flash free tier (1500 requests/day)

---

## Requirements

- Python 3.11+
- Microsoft Edge (for scraping — Windows only)
- A **free** Google Gemini API key (no credit card)

---

## Quick Start

### 1. Clone & install

```bash
git clone https://github.com/YOUR_USERNAME/jobpilot.git
cd jobpilot
pip install -r requirements.txt
playwright install chromium
```

Or on Windows, just run **`run.bat`** — it installs everything automatically.

### 2. Get your free Gemini API key

1. Go to [aistudio.google.com/app/apikey](https://aistudio.google.com/app/apikey)
2. Sign in with a Google account → **Create API key** (free, no credit card)
3. Copy the key

### 3. Set up your CV

```bash
cp master_cv.example.md master_cv.md
```

Open `master_cv.md` and replace the example with your own experience.

### 4. Launch the app

```bash
streamlit run app.py
```

Or double-click **`run.bat`** on Windows.

Then:
- Go to **⚙️ Settings** → paste your Gemini API key
- Go to **🔍 Searches** → add your LinkedIn/Stepstone search URLs
- Go to **🌐 Scrape** → open browser, scrape jobs
- Go to **⭐ Review & Score** → score and approve
- Go to **✅ Approved** → build tailored CVs

---

## Daily Workflow

```
Searches tab  →  Add/manage your job search URLs
Scrape tab    →  Open Browser → Ready to Scrape
Review tab    →  Score New Jobs → Approve / Reject
Approved tab  →  Build Base CVs → Mark as Applied
```

---

## Project Structure

```
jobpilot/
├── app.py                  ← Streamlit UI (main entry point)
├── db.py                   ← SQLite helper
├── scraper.py              ← Playwright job scraper (no AI tokens used)
├── llm.py                  ← Gemini AI wrapper (all AI calls)
├── generator.py            ← Markdown → .docx CV renderer
├── build_base_cvs.py       ← Build base CVs (called by UI)
├── score_jobs.py           ← Score jobs (called by UI)
├── apply.py                ← Semi-automated form filler
├── cert_reader.py          ← Import certificates from PDFs
├── agents/
│   ├── job_assessor.py     ← CLI: score new jobs
│   ├── cv_tailor.py        ← CLI: tailor CV for one job
│   ├── cv_base_builder.py  ← CLI: build base CVs
│   └── pipeline_tester.py  ← CLI: health check
├── master_cv.example.md    ← CV template (copy to master_cv.md)
├── .env.example            ← API key template (copy to .env)
├── requirements.txt
└── run.bat                 ← Windows one-click launcher
```

`master_cv.md`, `jobs.db`, `.env`, and `cv_outputs/` are gitignored — your personal data stays local.

---

## Supported Job Platforms

| Platform | Status |
|----------|--------|
| LinkedIn (`/jobs/search/`) | ✅ Supported |
| Stepstone (DE) | ✅ Supported |
| Others | Planned |

---

## Configuration

All settings are in the **⚙️ Settings** tab in the UI — no config files to edit manually.

To use a different Gemini model, set in `.env`:

```
GEMINI_MODEL=gemini-2.5-flash
GEMINI_SCORE_MODEL=gemini-2.5-flash
```

---

## Health Check

```bash
python agents/pipeline_tester.py
```

---

## Notes

- **Windows only** for scraping (uses Microsoft Edge). Linux/Mac users can adapt `EDGE_EXE` in `scraper.py`.
- Nothing is ever submitted automatically — you always review before applying.
- Your CV, job data, and API key stay on your local machine.

---

## License

MIT — free to use, modify, and share.
