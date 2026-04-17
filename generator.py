"""
generator.py — Converts a tailored CV markdown file into an ATS-compliant .docx

Usage:
    python generator.py cv_outputs/company_title_tailored.md

Output:
    cv_outputs/company_title_tailored.docx
    Prints the output path on success.

Requires: pip install python-docx
"""

import sys
import os
import re
from docx import Document
from docx.shared import Pt, Cm, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml.ns import qn
from docx.oxml import OxmlElement
from docx.opc.constants import RELATIONSHIP_TYPE as RT


# ---------------------------------------------------------------------------
# Document style setup
# ---------------------------------------------------------------------------

def _setup_document() -> Document:
    doc = Document()

    # A4 page, tight margins for 2-page fit
    for section in doc.sections:
        section.page_width  = int(21.0 * 914400 / 2.54)
        section.page_height = int(29.7 * 914400 / 2.54)
        section.top_margin    = Cm(1.2)
        section.bottom_margin = Cm(1.2)
        section.left_margin   = Cm(1.4)
        section.right_margin  = Cm(1.4)

    # Normal style
    normal = doc.styles["Normal"]
    normal.font.name = "Calibri"
    normal.font.size = Pt(10)
    normal.paragraph_format.space_before = Pt(0)
    normal.paragraph_format.space_after  = Pt(2)

    # Heading 2 — section titles
    h2 = doc.styles["Heading 2"]
    h2.font.name  = "Calibri"
    h2.font.size  = Pt(11)
    h2.font.bold  = True
    h2.font.color.rgb = RGBColor(0, 0, 0)
    h2.font.underline = False
    h2.paragraph_format.space_before = Pt(7)
    h2.paragraph_format.space_after  = Pt(1)

    # Heading 3 — candidate name
    h3 = doc.styles["Heading 3"]
    h3.font.name  = "Calibri"
    h3.font.size  = Pt(16)
    h3.font.bold  = True
    h3.font.color.rgb = RGBColor(0, 0, 0)
    h3.font.underline = False
    h3.paragraph_format.space_before = Pt(0)
    h3.paragraph_format.space_after  = Pt(1)

    # List Paragraph — bullets
    if "List Paragraph" in [s.name for s in doc.styles]:
        lp = doc.styles["List Paragraph"]
    else:
        lp = doc.styles.add_style("List Paragraph", 1)
    lp.font.name = "Calibri"
    lp.font.size = Pt(10)
    lp.paragraph_format.left_indent   = Cm(0.4)
    lp.paragraph_format.space_before  = Pt(0)
    lp.paragraph_format.space_after   = Pt(1)

    return doc


def _add_bottom_border(paragraph):
    pPr = paragraph._p.get_or_add_pPr()
    pBdr = OxmlElement("w:pBdr")
    bottom = OxmlElement("w:bottom")
    bottom.set(qn("w:val"), "single")
    bottom.set(qn("w:sz"), "4")
    bottom.set(qn("w:space"), "1")
    bottom.set(qn("w:color"), "000000")
    pBdr.append(bottom)
    pPr.append(pBdr)


# ---------------------------------------------------------------------------
# Hyperlink helper
# ---------------------------------------------------------------------------

def _add_hyperlink_run(paragraph, text, url, font_size=Pt(10), color=None):
    """Append a hyperlinked run to an existing paragraph."""
    part = paragraph.part
    r_id = part.relate_to(url, RT.HYPERLINK, is_external=True)

    hyperlink = OxmlElement("w:hyperlink")
    hyperlink.set(qn("r:id"), r_id)

    run_elem = OxmlElement("w:r")
    rPr = OxmlElement("w:rPr")

    # Font
    rFonts = OxmlElement("w:rFonts")
    rFonts.set(qn("w:ascii"), "Calibri")
    rFonts.set(qn("w:hAnsi"), "Calibri")
    rPr.append(rFonts)

    sz = OxmlElement("w:sz")
    sz.set(qn("w:val"), str(int(font_size.pt * 2)))
    rPr.append(sz)

    # Color (default: hyperlink blue)
    col = OxmlElement("w:color")
    col.set(qn("w:val"), color or "0563C1")
    rPr.append(col)

    # Underline
    u = OxmlElement("w:u")
    u.set(qn("w:val"), "single")
    rPr.append(u)

    run_elem.append(rPr)

    t = OxmlElement("w:t")
    t.text = text
    t.set("{http://www.w3.org/XML/1998/namespace}space", "preserve")
    run_elem.append(t)
    hyperlink.append(run_elem)
    paragraph._p.append(hyperlink)


def _plain_run(paragraph, text, font_size=Pt(10), color=None, bold=False):
    """Append a plain (non-hyperlinked) run to a paragraph."""
    run = paragraph.add_run(text)
    run.font.name = "Calibri"
    run.font.size = font_size
    run.bold = bold
    if color:
        run.font.color.rgb = color
    return run


def _render_contact_line(doc, contact_str):
    """
    Render the contact line with clickable hyperlinks for email,
    LinkedIn profile, and personal website.
    Format: City | Phone | email@... | linkedin.com/... | website.me
    """
    p = doc.add_paragraph(style="Normal")
    p.paragraph_format.space_after = Pt(1)

    parts = [s.strip() for s in contact_str.split("|")]
    separator = "  |  "
    gray = RGBColor(60, 60, 60)

    for i, part in enumerate(parts):
        prefix = separator if i > 0 else ""

        # Email
        if "@" in part and "." in part:
            if prefix:
                _plain_run(p, prefix, font_size=Pt(10), color=gray)
            _add_hyperlink_run(p, part, f"mailto:{part}", font_size=Pt(10), color="0563C1")

        # LinkedIn or other URL-like (contains .com, .de, .me etc. but no @)
        elif re.search(r'\b(linkedin\.com|\.me|\.de|\.io|\.net|\.org)\b', part, re.IGNORECASE):
            url = part if part.startswith("http") else f"https://{part}"
            if prefix:
                _plain_run(p, prefix, font_size=Pt(10), color=gray)
            _add_hyperlink_run(p, part, url, font_size=Pt(10), color="0563C1")

        # Plain text (city, phone)
        else:
            _plain_run(p, prefix + part, font_size=Pt(10), color=gray)


# ---------------------------------------------------------------------------
# Markdown parser
# ---------------------------------------------------------------------------

def _clean_name(name: str) -> str:
    """Remove parenthetical nicknames, e.g. 'Jane (JJ) Doe' → 'Jane Doe'."""
    return re.sub(r'\s*\([^)]*\)', '', name).strip()


def _parse(text: str) -> dict:
    lines = text.splitlines()
    result = {
        "name":     "",
        "contact":  "",
        "headline": "",
        "sections": [],
    }

    header_done  = False
    header_count = 0
    section_lines = []
    current_section = None
    i = 0

    while i < len(lines):
        line = lines[i]

        if not header_done:
            stripped = line.strip()
            if stripped:
                if header_count == 0:
                    result["name"] = _clean_name(stripped)
                    header_count += 1
                elif header_count == 1:
                    result["contact"] = stripped
                    header_count += 1
                elif header_count == 2:
                    result["headline"] = stripped
                    header_count += 1
                    header_done = True
            i += 1
            continue

        if line.startswith("## "):
            if current_section is not None:
                result["sections"].append({
                    "title": current_section,
                    "lines": section_lines,
                })
            current_section = line[3:].strip()
            section_lines = []
        else:
            if current_section is not None:
                section_lines.append(line)

        i += 1

    if current_section is not None:
        result["sections"].append({
            "title": current_section,
            "lines": section_lines,
        })

    return result


# ---------------------------------------------------------------------------
# Document builder
# ---------------------------------------------------------------------------

def _add_section_heading(doc, title):
    p = doc.add_paragraph(title, style="Heading 2")
    # Explicitly set paragraph spacing (not just style)
    p.paragraph_format.space_before = Pt(7)
    p.paragraph_format.space_after = Pt(2)
    # Ensure runs inherit heading style properties
    for run in p.runs:
        run.font.name = "Calibri"
        run.font.size = Pt(11)
        run.font.bold = True
    _add_bottom_border(p)
    return p


def _add_experience_section(doc, lines):
    date_pattern = re.compile(
        r'\b(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec|'
        r'Dez|Okt|Mai|Mrz|'
        r'\d{4}|Heute|Present)\b', re.IGNORECASE
    )

    i = 0
    while i < len(lines):
        line = lines[i].rstrip()

        if not line.strip():
            i += 1
            continue

        if line.startswith("- "):
            p = doc.add_paragraph(style="List Paragraph")
            p.paragraph_format.left_indent = Cm(0.4)
            run = p.add_run("- " + line[2:])
            run.font.name = "Calibri"
            run.font.size = Pt(10)
            i += 1
            continue

        next_line = lines[i + 1].rstrip() if i + 1 < len(lines) else ""

        if "|" in line and not line.startswith("- ") and (date_pattern.search(next_line) or "|" in next_line):
            # Company | Location line
            p = doc.add_paragraph(style="Normal")
            p.paragraph_format.space_before = Pt(5)
            p.paragraph_format.space_after  = Pt(1)
            run = p.add_run(line)
            run.bold = True
            run.font.name = "Calibri"
            run.font.size = Pt(10)
            i += 1
        elif date_pattern.search(line) and "|" in line and i > 0:
            # Position | Date line
            p = doc.add_paragraph(style="Normal")
            p.paragraph_format.space_before = Pt(0)
            p.paragraph_format.space_after  = Pt(1)
            parts = line.split("|", 1)
            run1 = p.add_run(parts[0].strip())
            run1.italic = True
            run1.font.name = "Calibri"
            run1.font.size = Pt(10)
            if len(parts) > 1:
                run2 = p.add_run("  |  " + parts[1].strip())
                run2.font.name = "Calibri"
                run2.font.size = Pt(9)
                run2.font.color.rgb = RGBColor(80, 80, 80)
            i += 1
        else:
            p = doc.add_paragraph(line, style="Normal")
            i += 1


def _add_simple_section(doc, lines):
    for line in lines:
        line = line.rstrip()
        if not line.strip():
            continue
        if line.startswith("- "):
            p = doc.add_paragraph(style="List Paragraph")
            p.paragraph_format.left_indent = Cm(0.4)
            run = p.add_run("- " + line[2:])
            run.font.name = "Calibri"
            run.font.size = Pt(10)
        else:
            bold_match = re.match(r'^\*\*(.+?)\*\*:?\s*(.*)', line)
            if bold_match:
                p = doc.add_paragraph(style="Normal")
                # Avoid double colons if the bold text ends with :
                bold_text = bold_match.group(1).rstrip(':')
                rl = p.add_run(bold_text + ": ")
                rl.bold = True
                rl.font.name = "Calibri"
                rl.font.size = Pt(10)
                if bold_match.group(2):
                    rr = p.add_run(bold_match.group(2))
                    rr.font.name = "Calibri"
                    rr.font.size = Pt(10)
            else:
                colon_match = re.match(r'^([^:\n]{3,40}):\s+(.+)', line)
                if colon_match and len(colon_match.group(1).split()) <= 5:
                    p = doc.add_paragraph(style="Normal")
                    rl = p.add_run(colon_match.group(1) + ": ")
                    rl.bold = True
                    rl.font.name = "Calibri"
                    rl.font.size = Pt(10)
                    rr = p.add_run(colon_match.group(2))
                    rr.font.name = "Calibri"
                    rr.font.size = Pt(10)
                else:
                    p = doc.add_paragraph(line, style="Normal")
                    for run in p.runs:
                        run.font.name = "Calibri"
                        run.font.size = Pt(10)


# ---------------------------------------------------------------------------
# Main render function
# ---------------------------------------------------------------------------

def render(md_path: str) -> str:
    md_path = os.path.abspath(md_path)
    if not os.path.isfile(md_path):
        raise FileNotFoundError(f"Markdown file not found: {md_path}")

    with open(md_path, encoding="utf-8") as f:
        text = f.read()

    data = _parse(text)
    doc  = _setup_document()

    # --- Header ---
    if data["name"]:
        p = doc.add_paragraph(data["name"], style="Heading 3")
        p.paragraph_format.space_after = Pt(2)
        for run in p.runs:
            run.font.name = "Calibri"
            run.font.size = Pt(16)
            run.font.bold = True

    if data["contact"]:
        _render_contact_line(doc, data["contact"])

    if data["headline"]:
        p = doc.add_paragraph(style="Normal")
        p.paragraph_format.space_after = Pt(4)
        run = p.add_run(data["headline"])
        run.font.name = "Calibri"
        run.font.size = Pt(10)
        run.bold = True

    # --- Sections ---
    experience_keys = {"professional experience", "experience", "work experience",
                       "berufserfahrung"}

    # Detect and extract footer (last line of last section matching "City, Month Year")
    footer_text = ""
    if data["sections"]:
        last_sec = data["sections"][-1]
        non_empty = [l for l in last_sec["lines"] if l.strip()]
        if non_empty:
            candidate = non_empty[-1].strip()
            if re.match(r'^[A-Za-zÄÖÜäöüß\s]+,\s+\w+\s+\d{4}$', candidate):
                footer_text = candidate
                last_sec["lines"] = [l for l in last_sec["lines"]
                                     if l.strip() != candidate]

    for sec in data["sections"]:
        title = sec["title"]
        lines = sec["lines"]

        _add_section_heading(doc, title)

        if title.lower() in experience_keys:
            _add_experience_section(doc, lines)
        else:
            _add_simple_section(doc, lines)

    # --- Footer ---
    if footer_text:
        p = doc.add_paragraph(style="Normal")
        p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
        p.paragraph_format.space_before = Pt(8)
        run = p.add_run(footer_text)
        run.font.name = "Calibri"
        run.font.size = Pt(9)
        run.font.color.rgb = RGBColor(100, 100, 100)

    # --- Save ---
    out_path = os.path.splitext(md_path)[0] + ".docx"
    doc.save(out_path)
    return out_path


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python generator.py <path/to/tailored_cv.md>")
        sys.exit(1)

    try:
        out = render(sys.argv[1])
        print(f"Output: {out}")
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)
