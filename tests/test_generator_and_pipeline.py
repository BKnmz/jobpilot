from docx import Document

from jobpilot import db, generator, languages, paths, plugins
from jobpilot.pipeline import base_cvs, health, score, tailor

CV_DE = """# Jane (JJ) Doe

München | jane@example.com | linkedin.com/in/janedoe

## Product Owner | Agile Entwicklung

## Berufsprofil

Erfahrene Product Ownerin.

## Berufserfahrung

**Acme GmbH** · München
*Product Owner* · Jan 2021 – heute
- **Roadmap** für drei Teams verantwortet
- Backlog priorisiert

## Sprachen

Deutsch, Englisch, Türkisch

München, November 2026
"""


def test_parse_handles_heading_style_header():
    data = generator._parse(CV_DE)
    assert data["name"] == "Jane Doe"
    assert data["headline"] == "Product Owner | Agile Entwicklung"
    assert [s["title"] for s in data["sections"]] == ["Berufsprofil", "Berufserfahrung", "Sprachen"]


def test_parse_without_headline_keeps_first_section():
    data = generator._parse("Jane Doe\nBerlin | jane@example.com\n\n## Summary\n\nText\n")
    assert data["headline"] == ""
    assert data["sections"][0]["title"] == "Summary"


def test_render_writes_clean_docx(tmp_path):
    md = tmp_path / "cv.md"
    md.write_text(CV_DE, encoding="utf-8")
    out = generator.render(str(md))
    text = "\n".join(p.text for p in Document(out).paragraphs)
    assert "Jane Doe" in text and "#" not in text and "**" not in text
    assert "Acme GmbH | München" in text
    assert "- Roadmap für drei Teams verantwortet" in text
    assert text.strip().endswith("München, November 2026")


def test_languages_cover_three_locales():
    assert languages.codes() == ["en", "de", "tr"]
    assert {"berufserfahrung", "iş deneyimi", "professional experience"} <= languages.experience_headings()
    assert languages.get("xx").code == "en"
    assert languages.format_date("de", 2026, 11, 15) == "15. November 2026"
    assert languages.format_date("tr", 2026, 11, 15) == "15 Kasım 2026"


def test_scoring_run_end_to_end(fake_llm, master_cv, capsys):
    db.insert_job("Product Owner", "Müller's AG", "Köln", "Scrum, Roadmap", "https://example.com/a")
    db.insert_job("Analyst", "Beta", "Izmir", "SQL", "https://example.com/b")
    fake_llm.answers += [
        '{"score": 9, "reason": "It\'s a fit", "role_profile": 2, "matched": ["Scrum"], "missing": []}',
        "this is not json",
    ]
    scored, errors = score.score_new_jobs(limit=10)
    assert (scored, errors) == (1, 1)
    good = db.get_jobs_by_status("scored")[0]
    assert good["notes"] == "It's a fit" and good["match_score"] == 9
    assert len(db.get_jobs_by_status("new")) == 1          # the failed one stays 'new'
    assert "Top match: Product Owner at Müller's AG" in capsys.readouterr().out


def test_base_cv_build_and_tailor(fake_llm, master_cv):
    fake_llm.answers.append("Alex Demo\nMunich | alex@example.com\nProduct Owner\n\n## Profesyonel Özet\n\nÖzet.\n")
    built, requested = base_cvs.build([(2, "tr")])
    assert (built, requested) == (1, 1)
    rec = db.get_role_cvs()[(2, "tr")]
    assert rec["cv_path"] == "cv_outputs/base/profile_2_po_tr.docx"
    assert paths.resolve(rec["cv_path"]).exists()

    db.insert_job("PO / Şef", "Örnek A.Ş.", "İstanbul", "JD", "https://example.com/c",
                  role_profile=2, language="tr")
    job = db.get_jobs_by_status("new")[0]
    fake_llm.answers.append("Alex Demo\nMunich | alex@example.com\nProduct Owner\n\n## Profesyonel Özet\n\nUyarlanmış.\n")
    rel = tailor.tailor_job(job["id"])
    assert rel.endswith("_tr_tailored.docx") and paths.resolve(rel).exists()
    assert db.get_job(job["id"])["cv_path"] == rel
    assert "Turkish" in fake_llm.prompts[-1] and "Örnek A.Ş." in fake_llm.prompts[-1]


def test_health_check_runs_without_ai_calls(fake_llm, master_cv, capsys):
    passed, total = health.run()
    out = capsys.readouterr().out
    assert "Role profiles" in out and total >= 6 and passed >= 4
    assert fake_llm.prompts == []


def test_plugin_registry_is_idempotent():
    before = len(plugins.tabs)
    plugins.register_tab("Demo", lambda: None)
    plugins.register_tab("Demo", lambda: None)
    assert len(plugins.tabs) == before + 1
    plugins.tabs.pop()
    assert plugins.load_plugins() == []        # disabled in tests via JOBPILOT_DISABLE_PLUGINS
