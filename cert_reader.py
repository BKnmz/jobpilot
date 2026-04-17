"""
cert_reader.py — Build the certificates database from a folder of PDFs.

Filename convention: NN_CATEGORY_Cert_Name_Here.pdf
  NN        = sequential number (ignored)
  CATEGORY  = DATA | SEC | AI | MGMT | CLOUD | ISO | PM | DEV | etc.
  Rest      = certificate name (underscores become spaces)

Usage:
    python cert_reader.py --folder certificates/        # read local PDFs
    python cert_reader.py --drive-link <URL>            # download from Drive then read
    python cert_reader.py --list                        # print all certs in DB
    python cert_reader.py --set-tags <id> <tags>        # manually fix tags for a cert
"""

import argparse
import os
import re
import sys

from db import _connect, init_db


# ---------------------------------------------------------------------------
# Category → role-tag mapping
# ---------------------------------------------------------------------------

CATEGORY_TAGS = {
    "DATA":  "data,analytics",
    "SEC":   "cybersec,grc,compliance",
    "AI":    "ai,product",
    "MGMT":  "product,agile,management",
    "CLOUD": "cloud,engineering",
    "ISO":   "cybersec,compliance,grc",
    "PM":    "product,agile,management",
    "DEV":   "engineering,data",
    "GRC":   "cybersec,grc,compliance",
    "CYBER": "cybersec,grc,compliance",
    "BA":    "ba,data,analytics",
    "AGILE": "product,agile,management",
    "ML":    "ai,data,analytics",
}

# Known issuers — matched by substring in PDF text (order matters: more specific first)
KNOWN_ISSUERS = [
    "Proofpoint",
    "TÜV Nord", "TUV Nord", "TÜV",
    "ISC2", "ISC²", "(ISC)²",
    "IBM",
    "Google",
    "Coursera",
    "LinkedIn Learning",
    "Microsoft",
    "AWS", "Amazon Web Services",
    "SAFe", "Scaled Agile",
    "Scrum Alliance",
    "PMI",
    "ISACA",
    "CompTIA",
    "Udemy",
    "DataCamp",
    "Pluralsight",
    "edX",
    "Cisco",
    "Oracle",
    "Salesforce",
]


# ---------------------------------------------------------------------------
# Filename parser
# ---------------------------------------------------------------------------

def _parse_filename(filename: str) -> tuple[str, str]:
    """
    Parse 'NN_CATEGORY_Cert_Name.pdf' → (category, cert_name).
    Falls back gracefully if the convention isn't followed.
    """
    stem = os.path.splitext(filename)[0]          # drop .pdf
    tokens = stem.split("_")

    # First token is a number → skip it
    start = 1 if tokens and tokens[0].isdigit() else 0
    tokens = tokens[start:]

    if not tokens:
        return ("UNKNOWN", stem.replace("_", " "))

    category = tokens[0].upper() if tokens else "UNKNOWN"
    cert_name = " ".join(tokens[1:]).strip() if len(tokens) > 1 else tokens[0]

    return category, cert_name


# ---------------------------------------------------------------------------
# PDF text extraction
# ---------------------------------------------------------------------------

def _extract_pdf_text(pdf_path: str) -> str:
    """Return all text from a PDF. Returns '' on failure."""
    try:
        import pdfplumber
        with pdfplumber.open(pdf_path) as pdf:
            parts = []
            for page in pdf.pages:
                t = page.extract_text()
                if t:
                    parts.append(t)
        return "\n".join(parts)
    except Exception:
        return ""


def _extract_year(text: str) -> int | None:
    """Find the most recent plausible cert year in the text (2010–2030)."""
    years = re.findall(r'\b(20[1-3]\d)\b', text)
    if years:
        return max(int(y) for y in years)
    return None


def _extract_issuer(text: str) -> str:
    """Match first known issuer found in the text."""
    text_lower = text.lower()
    for issuer in KNOWN_ISSUERS:
        if issuer.lower() in text_lower:
            return issuer
    return ""


# ---------------------------------------------------------------------------
# DB helpers
# ---------------------------------------------------------------------------

def _upsert_cert(filename, category, cert_name, issuer, year, tags):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO certificates (filename, category, cert_name, issuer, year, tags)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(filename) DO UPDATE SET
                category=excluded.category,
                cert_name=excluded.cert_name,
                issuer=excluded.issuer,
                year=excluded.year,
                tags=excluded.tags
            """,
            (filename, category, cert_name, issuer or None, year, tags or None),
        )


def _list_certs():
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, cert_name, issuer, year, category, tags, is_active "
            "FROM certificates ORDER BY year DESC, id"
        ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Drive download
# ---------------------------------------------------------------------------

def _download_from_drive(url: str, dest_folder: str):
    """Download a public Google Drive folder using gdown."""
    try:
        import gdown
    except ImportError:
        print("gdown not installed. Run: pip install gdown")
        sys.exit(1)

    os.makedirs(dest_folder, exist_ok=True)
    print(f"Downloading from Google Drive to {dest_folder}/ ...")
    gdown.download_folder(url, output=dest_folder, quiet=False, use_cookies=False)
    print("Download complete.\n")


# ---------------------------------------------------------------------------
# Main processing
# ---------------------------------------------------------------------------

def process_folder(folder: str) -> tuple[int, int]:
    """
    Read all PDFs in folder, insert/update certificates table.
    Returns (inserted_or_updated, failed).
    """
    pdfs = [f for f in os.listdir(folder) if f.lower().endswith(".pdf")]
    if not pdfs:
        print(f"No PDF files found in {folder}/")
        return 0, 0

    print(f"Found {len(pdfs)} PDF(s). Processing...\n")

    ok = fail = 0
    results = []

    for filename in sorted(pdfs):
        path = os.path.join(folder, filename)
        category, cert_name = _parse_filename(filename)

        # Try PDF text extraction
        text = _extract_pdf_text(path)
        year   = _extract_year(text)   if text else None
        issuer = _extract_issuer(text) if text else ""

        tags = CATEGORY_TAGS.get(category, "")

        try:
            _upsert_cert(filename, category, cert_name, issuer, year, tags)
            status = "OK" if text else "OK (filename only)"
            ok += 1
        except Exception as e:
            status = f"ERROR: {e}"
            fail += 1

        results.append({
            "id":        "",
            "file":      filename[:45],
            "category":  category,
            "name":      cert_name[:40],
            "issuer":    issuer[:20] if issuer else "-",
            "year":      str(year) if year else "-",
            "tags":      tags or "-",
            "status":    status,
        })

    # Print summary table
    print(f"{'FILE':<46} {'CAT':<7} {'ISSUER':<22} {'YEAR':<6} {'TAGS':<35} STATUS")
    print("-" * 130)
    for r in results:
        print(f"{r['file']:<46} {r['category']:<7} {r['issuer']:<22} {r['year']:<6} {r['tags']:<35} {r['status']}")

    print(f"\n{ok} processed, {fail} errors.")
    return ok, fail


def print_cert_list():
    """Print all certs currently in the DB."""
    certs = _list_certs()
    if not certs:
        print("No certificates in database yet.")
        return

    print(f"\n{'ID':<4} {'YEAR':<6} {'CATEGORY':<8} {'ISSUER':<22} {'TAGS':<35} CERT NAME")
    print("-" * 120)
    for c in certs:
        active = "" if c["is_active"] else " [inactive]"
        print(
            f"{c['id']:<4} {str(c['year'] or '-'):<6} {(c['category'] or '-'):<8} "
            f"{(c['issuer'] or '-'):<22} {(c['tags'] or '-'):<35} "
            f"{c['cert_name']}{active}"
        )
    print(f"\nTotal: {len(certs)} certificates")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(description="Certificate database builder")
    parser.add_argument("--folder",     help="Local folder containing PDF certificates")
    parser.add_argument("--drive-link", help="Google Drive public folder link")
    parser.add_argument("--list",       action="store_true", help="List all certs in DB")
    parser.add_argument("--set-tags",   nargs=2, metavar=("ID", "TAGS"),
                        help="Manually set tags for a cert: --set-tags 3 'cybersec,grc'")
    args = parser.parse_args()

    init_db()

    if args.list:
        print_cert_list()
        return

    if args.set_tags:
        cert_id, tags = args.set_tags
        with _connect() as conn:
            conn.execute("UPDATE certificates SET tags=? WHERE id=?", (tags, int(cert_id)))
        print(f"Tags updated for cert ID {cert_id}: {tags}")
        return

    folder = args.folder or "certificates"

    if args.drive_link:
        _download_from_drive(args.drive_link, folder)

    if not os.path.isdir(folder):
        print(f"Folder not found: {folder}")
        print("Use --folder <path> or --drive-link <url>")
        sys.exit(1)

    process_folder(folder)
    print()
    print_cert_list()


if __name__ == "__main__":
    main()
