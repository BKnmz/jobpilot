# 🚀 JobPilot — AI-Powered Job Application Pipeline

> Scrape jobs → Score with AI → Tailor your CV → Apply smarter.
> **Free and open source. Runs locally. Your data is never stored on third-party servers; AI features send text only to the AI provider you choose.**

![Python](https://img.shields.io/badge/Python-3.11+-blue) ![Gemini](https://img.shields.io/badge/AI-Google_Gemini-orange) ![Streamlit](https://img.shields.io/badge/UI-Streamlit-red) ![License](https://img.shields.io/badge/License-MIT-green) [![Ko-fi](https://img.shields.io/badge/☕-Buy_me_a_coffee-ff5e5b)](https://ko-fi.com/consultbknmz)

---

## What It Does

JobPilot is a local desktop tool that takes the repetitive work out of job hunting:

| Step | What happens |
|------|-------------|
| 🔍 **Scrape** | Opens your LinkedIn/Stepstone searches in your own browser and reads the listings |
| 🤖 **Score** | AI rates each job 1–10 against your CV and shows which requirements you cover and miss |
| ✅ **Review** | You approve or reject in a dashboard — nothing is sent automatically |
| 📄 **Tailor** | AI rewrites your summary and reorders your bullets for the job, in English, German or Turkish |
| 📤 **Apply** | Optional form filler that stops before Submit |

**A human approves every step.**

---

## Features

- **AI job scoring** — score 1–10, a one-line reason, matched and missing keywords
- **Your own role profiles** — define the kinds of job you apply for; each posting is sorted into one
- **Base CVs per role and language** — English, German and Turkish, written natively, not translated
- **Per-job CV tailoring** — one click on an approved job, download the .docx
- **ATS-friendly .docx output** — plain Word document, no tables or graphics
- **Pick your model** — choose from the models your API key offers; nothing is hardcoded
- **Certificate database** — import certificates from PDFs, the relevant ones go into each CV
- **Extensible** — add-ons can register extra tabs and AI providers (see `jobpilot/plugins.py`)

---

## Requirements

- Python 3.11+
- Microsoft Edge or Google Chrome (built and tested on Windows)
- A Google Gemini API key ([free tier available](https://aistudio.google.com/app/apikey), no credit card)

Google's free tier has per-model daily limits that change over time. If scoring stops with a quota
message, pick another model in Settings or continue the next day.

---

## Quick Start

### Windows, one click

Download the repo and double-click **`run.bat`**. It creates a local Python environment, installs the
dependencies and starts the app.

### Manual

```bash
git clone https://github.com/BKnmz/jobpilot.git
cd jobpilot
pip install -r requirements.txt
cp master_cv.example.md master_cv.md     # then replace it with your own CV
streamlit run app.py
```

Then, in the app:

1. **⚙️ Settings** → paste your Gemini key, fill in contact details, adjust the role profiles to your field
2. **🔍 Searches** → add your LinkedIn/Stepstone search URLs
3. **🌐 Scrape** → open browser, log in, scrape
4. **⭐ Review & Score** → score, then approve or reject
5. **✅ Approved** → build base CVs, tailor per job, download

---

## Project Structure

```
jobpilot/
├── app.py                     ← entry point (streamlit run app.py)
├── jobpilot/
│   ├── paths.py               ← where your data lives (JOBPILOT_HOME)
│   ├── db.py                  ← SQLite storage and helpers
│   ├── llm.py                 ← all AI calls, pluggable providers
│   ├── languages.py           ← English / German / Turkish conventions
│   ├── scraper.py             ← browser scraper (no AI calls)
│   ├── generator.py           ← markdown → .docx
│   ├── apply.py               ← form filler that stops before Submit
│   ├── cert_reader.py         ← import certificates from PDFs
│   ├── plugins.py             ← add-on hooks
│   ├── pipeline/              ← score.py, base_cvs.py, tailor.py, health.py
│   └── ui/                    ← Streamlit tabs
├── agents/                    ← small command-line wrappers
├── tests/
├── master_cv.example.md       ← CV template (copy to master_cv.md)
└── run.bat                    ← Windows one-click launcher
```

`master_cv.md`, `jobs.db`, `.env` and `cv_outputs/` are gitignored. Set `JOBPILOT_HOME` to keep
them in a different folder.

---

## Command Line

```bash
python -m jobpilot.pipeline.health --models     # health check, list usable models
python -m jobpilot.pipeline.score --limit 5     # score new jobs
python -m jobpilot.pipeline.base_cvs --profiles 1:en 2:de
python -m jobpilot.pipeline.tailor --job-id 5 --lang tr
python -m jobpilot.scraper --diagnose           # inspect open tabs without writing
python -m pytest                                # run the tests
```

---

## Supported Job Platforms

| Platform | Status |
|----------|--------|
| LinkedIn (`/jobs/search/`) | ✅ Supported |
| Stepstone (DE) | ✅ Supported |
| Others | Planned |

JobPilot reads pages in your own logged-in browser at your pace. You are responsible for using it
within each platform's terms of service.

---

## Support

JobPilot is free and maintained in spare time. If it saved you an evening of copy-pasting, you can
[buy me a coffee on Ko-fi](https://ko-fi.com/consultbknmz) (card, PayPal, Apple Pay or Google Pay, no account needed). Bug reports and pull requests help just as much.

A Pro add-on is in the works: cover letters written in your own voice, in English, German and
Turkish, learned from texts you wrote yourself.

---

## License

MIT — free to use, modify, and share.
