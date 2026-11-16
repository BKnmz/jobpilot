import json

from jobpilot import db, paths


def test_fresh_database_has_no_predefined_role_profiles():
    assert db.get_role_profiles(active_only=False) == []
    assert db.get_profile_name(999) == "Profile 999"
    assert not (paths.PKG_DIR / "data" / "profiles.example.json").exists()


def test_user_seed_file_wins_over_examples():
    paths.ROLE_PROFILE_SEED.write_text(json.dumps([
        {"name": "Nurse", "keywords": "care, ward", "headline": "Registered Nurse", "focus": "x"}
    ]), encoding="utf-8")
    with db._connect() as conn:
        conn.execute("DELETE FROM role_profiles")
    db.init_db()
    assert [p["name"] for p in db.get_role_profiles()] == ["Nurse"]


def test_legacy_profile_names_survive_migration():
    with db._connect() as conn:
        conn.execute("DELETE FROM role_profiles")
    db.set_setting("profile_1_name", "Profile 1")          # placeholder, ignored
    db.set_setting("profile_2_name", "Product Lead")
    db.init_db()
    assert db.get_profile_name(2) == "Product Lead"
    assert [p["id"] for p in db.get_role_profiles()] == [2]


def test_role_profile_crud():
    pid = db.save_role_profile(name="Data Analyst", keywords="sql, bi", cert_tags="data")
    assert db.get_role_profile(pid)["slug"] == "data_analyst"
    db.save_role_profile(pid, name="Senior Data Analyst", keywords="sql")
    assert db.get_profile_name(pid) == "Senior Data Analyst"
    db.delete_role_profile(pid)
    assert db.get_role_profile(pid) is None


def test_jobs_scoring_and_keywords_roundtrip():
    db.insert_job("Dev", "O'Reilly & Sons", "Köln", "jd", "https://example.com/1", language="de")
    db.insert_job("Dev", "Dup", "Köln", "jd", "https://example.com/1")  # same URL is ignored
    job = db.get_jobs_by_status("new")[0]
    assert job["company"] == "O'Reilly & Sons"

    db.save_score(job["id"], 8, "It's a strong match", 2, ["SQL", "Scrum"], ["Müşteri yönetimi"])
    scored = db.get_job(job["id"])
    assert scored["status"] == "scored"
    assert scored["notes"] == "It's a strong match"          # apostrophe stored once, not doubled
    assert scored["role_profile"] == 2
    assert db.job_keywords(scored) == (["SQL", "Scrum"], ["Müşteri yönetimi"])
    assert db.count_by_status() == {"scored": 1}


def test_score_keeps_search_role_when_model_gives_none():
    db.insert_job("Dev", "Acme", "Berlin", "jd", "https://example.com/2", role_profile=3)
    job = db.get_jobs_by_status("new")[0]
    db.save_score(job["id"], 5, "ok", None)
    assert db.get_job(job["id"])["role_profile"] == 3


def test_certificates_filtered_by_profile_tags():
    with db._connect() as conn:
        conn.executemany(
            "INSERT INTO certificates (filename, cert_name, issuer, year, tags) VALUES (?,?,?,?,?)",
            [("a.pdf", "Security Cert", "ISC2", 2023, "cybersec,grc"),
             ("b.pdf", "Scrum Cert", "Scrum Alliance", 2022, "product,agile"),
             ("c.pdf", "Old Cert", None, None, "cybersec")])
    pid = db.save_role_profile(name="Security Analyst", cert_tags="cybersec, grc")
    names = [c["cert_name"] for c in db.get_certs_for_role(pid)]
    assert "Security Cert" in names and "Scrum Cert" not in names
    assert db.cert_lines(pid)[0] == "Security Cert — ISC2 (2023)"


def test_contact_details_and_languages():
    db.set_profile_fields({"full_name": " Jane Doe ", "email": "jane@example.com", "location": "Izmir"})
    assert db.get_profile()["full_name"] == "Jane Doe"
    assert db.contact_line() == "Izmir | jane@example.com"

    assert db.get_enabled_languages() == ["en", "de", "tr"]
    db.set_setting("cv_languages", "tr, xx, en")
    assert db.get_enabled_languages() == ["en", "tr"]


def test_base_cv_assignment(tmp_path):
    cv = paths.BASE_CV_DIR / "profile_1_x_en.docx"
    cv.parent.mkdir(parents=True)
    cv.write_bytes(b"docx")
    db.upsert_role_cv(1, "en", paths.relative(cv))
    db.insert_job("A", "B", "C", "jd", "https://example.com/3", role_profile=1, language="en")
    job = db.get_jobs_by_status("new")[0]
    db.update_status(job["id"], "approved")
    assert db.assign_base_cvs_to_approved() == 1
    assert db.get_job(job["id"])["cv_path"] == "cv_outputs/base/profile_1_x_en.docx"
    assert paths.resolve(db.get_job(job["id"])["cv_path"]) == cv
