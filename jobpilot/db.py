"""
db.py — SQLite storage (jobs.db under JOBPILOT_HOME) and all database helpers.
"""
import json
import os
import re
import sqlite3
from contextlib import contextmanager
from datetime import date, datetime

from . import languages, paths

CONTACT_FIELDS = ("full_name", "email", "phone", "location", "linkedin_url", "website")


@contextmanager
def _connect():
    """Open the database, commit on success, roll back on error, always close."""
    paths.DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(paths.DB_PATH)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _add_column(conn, table: str, column: str, decl: str) -> None:
    existing = [r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()]
    if column not in existing:
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {column} {decl}")


def init_db():
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                title TEXT,
                company TEXT,
                location TEXT,
                jd_text TEXT,
                source_url TEXT UNIQUE,
                date_found TEXT,
                match_score INTEGER,
                status TEXT DEFAULT 'new',
                cv_path TEXT,
                notes TEXT
            );

            CREATE TABLE IF NOT EXISTS profile (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                field_name TEXT UNIQUE,
                field_value TEXT
            );

            CREATE TABLE IF NOT EXISTS certificates (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                filename   TEXT UNIQUE,
                category   TEXT,
                cert_name  TEXT,
                issuer     TEXT,
                year       INTEGER,
                tags       TEXT,
                is_active  INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS searches (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                platform     TEXT,
                role_profile INTEGER,
                search_url   TEXT UNIQUE,
                label        TEXT,
                language     TEXT,
                active       INTEGER DEFAULT 1
            );

            CREATE TABLE IF NOT EXISTS role_cvs (
                id           INTEGER PRIMARY KEY AUTOINCREMENT,
                profile_id   INTEGER,
                language     TEXT,
                cv_path      TEXT,
                generated_at TEXT,
                UNIQUE(profile_id, language)
            );

            CREATE TABLE IF NOT EXISTS settings (
                key   TEXT PRIMARY KEY,
                value TEXT
            );

            CREATE TABLE IF NOT EXISTS role_profiles (
                id        INTEGER PRIMARY KEY AUTOINCREMENT,
                name      TEXT NOT NULL,
                slug      TEXT,
                keywords  TEXT,
                headline  TEXT,
                focus     TEXT,
                cert_tags TEXT,
                cv_path   TEXT,
                active    INTEGER DEFAULT 1
            );
        """)
        _add_column(conn, "jobs", "role_profile", "INTEGER")
        _add_column(conn, "jobs", "language", "TEXT")
        _add_column(conn, "jobs", "matched_keywords", "TEXT")
        _add_column(conn, "jobs", "missing_keywords", "TEXT")
        _add_column(conn, "searches", "last_opened_at", "TEXT")

        for field in CONTACT_FIELDS:
            conn.execute(
                "INSERT OR IGNORE INTO profile (field_name, field_value) VALUES (?, ?)",
                (field, ""),
            )

        _seed_role_profiles(conn)


# ---------------------------------------------------------------------------
# Jobs
# ---------------------------------------------------------------------------

def insert_job(title, company, location, jd_text, source_url, role_profile=None, language=None):
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO jobs
                (title, company, location, jd_text, source_url, date_found, status,
                 role_profile, language)
            VALUES (?, ?, ?, ?, ?, ?, 'new', ?, ?)
            """,
            (title, company, location, jd_text, source_url, date.today().isoformat(),
             role_profile, language),
        )


def get_job(job_id: int) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id=?", (job_id,)).fetchone()
    return dict(row) if row else None


def get_jobs_by_status(status, limit: int | None = None):
    sql = "SELECT * FROM jobs WHERE status=? ORDER BY match_score DESC, id"
    params: tuple = (status,)
    if limit:
        sql += " LIMIT ?"
        params += (int(limit),)
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def count_by_status() -> dict:
    with _connect() as conn:
        rows = conn.execute("SELECT status, COUNT(*) AS n FROM jobs GROUP BY status").fetchall()
    return {r["status"]: r["n"] for r in rows}


def save_score(job_id: int, score: int, reason: str, role_profile: int | None,
               matched: list[str] | None = None, missing: list[str] | None = None):
    with _connect() as conn:
        conn.execute(
            """UPDATE jobs
               SET match_score=?, notes=?, role_profile=COALESCE(?, role_profile),
                   matched_keywords=?, missing_keywords=?, status='scored'
               WHERE id=?""",
            (score, reason, role_profile,
             json.dumps(matched or [], ensure_ascii=False),
             json.dumps(missing or [], ensure_ascii=False),
             job_id),
        )


def job_keywords(job: dict) -> tuple[list[str], list[str]]:
    """Return (matched, missing) keyword lists stored by the scorer."""
    def _load(value):
        try:
            data = json.loads(value) if value else []
            return [str(x) for x in data] if isinstance(data, list) else []
        except (TypeError, ValueError):
            return []
    return _load(job.get("matched_keywords")), _load(job.get("missing_keywords"))


def update_status(job_id, status):
    with _connect() as conn:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))


def update_cv_path(job_id, cv_path):
    with _connect() as conn:
        conn.execute("UPDATE jobs SET cv_path=? WHERE id=?", (cv_path, job_id))


def delete_all_jobs():
    with _connect() as conn:
        conn.execute("DELETE FROM jobs")


# ---------------------------------------------------------------------------
# Contact details (table "profile": name, email, phone, ...)
# ---------------------------------------------------------------------------

def get_profile() -> dict:
    with _connect() as conn:
        rows = conn.execute("SELECT field_name, field_value FROM profile").fetchall()
    return {r["field_name"]: r["field_value"] or "" for r in rows}


def set_profile_fields(values: dict) -> None:
    with _connect() as conn:
        for key, value in values.items():
            conn.execute(
                "INSERT INTO profile (field_name, field_value) VALUES (?, ?) "
                "ON CONFLICT(field_name) DO UPDATE SET field_value=excluded.field_value",
                (key, (value or "").strip()),
            )


def contact_line(profile: dict | None = None) -> str:
    p = profile if profile is not None else get_profile()
    parts = [p.get("location", ""), p.get("phone", ""), p.get("email", ""),
             p.get("linkedin_url", ""), p.get("website", "")]
    return " | ".join(x for x in parts if x)


# ---------------------------------------------------------------------------
# Searches
# ---------------------------------------------------------------------------

def insert_search(platform: str, role_profile: int, search_url: str, label: str, language: str):
    with _connect() as conn:
        conn.execute(
            """
            INSERT OR IGNORE INTO searches (platform, role_profile, search_url, label, language)
            VALUES (?, ?, ?, ?, ?)
            """,
            (platform, role_profile, search_url, label, language),
        )


def get_all_searches() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM searches ORDER BY platform, role_profile").fetchall()
    return [dict(r) for r in rows]


def get_active_searches() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM searches WHERE active=1 ORDER BY platform, role_profile"
        ).fetchall()
    return [dict(r) for r in rows]


def delete_search(search_id: int):
    with _connect() as conn:
        conn.execute("DELETE FROM searches WHERE id=?", (search_id,))


def toggle_search(search_id: int):
    with _connect() as conn:
        conn.execute(
            "UPDATE searches SET active = CASE WHEN active=1 THEN 0 ELSE 1 END WHERE id=?",
            (search_id,),
        )


def get_unopened_searches() -> list[dict]:
    """Active searches that have never been opened in the browser."""
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM searches WHERE active=1 AND last_opened_at IS NULL "
            "ORDER BY platform, role_profile"
        ).fetchall()
    return [dict(r) for r in rows]


def mark_searches_opened(ids: list[int]) -> None:
    now = datetime.now().isoformat(timespec="seconds")
    with _connect() as conn:
        conn.executemany(
            "UPDATE searches SET last_opened_at=? WHERE id=?",
            [(now, sid) for sid in ids],
        )


def reset_search_opened(search_id: int) -> None:
    with _connect() as conn:
        conn.execute("UPDATE searches SET last_opened_at=NULL WHERE id=?", (search_id,))


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_setting(key: str, default: str = "") -> str:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row and row["value"] is not None else default


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_cv_path() -> str:
    """Return the global master CV path, falling back to master_cv.md under HOME."""
    stored = get_setting("master_cv_path", "")
    if stored and os.path.isabs(stored):
        return stored
    return str(paths.DEFAULT_MASTER_CV)


def get_enabled_languages() -> list[str]:
    """Languages the user wants CVs in (setting 'cv_languages'), in a stable order."""
    stored = get_setting("cv_languages", "")
    chosen = [c.strip().lower() for c in stored.split(",") if c.strip()]
    valid = [c for c in languages.codes() if c in chosen]
    return valid or languages.codes()


# ---------------------------------------------------------------------------
# Role profiles (the kinds of job you apply for)
# ---------------------------------------------------------------------------

def slugify(text: str, max_len: int = 24) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", (text or "").lower()).strip("_")
    return slug[:max_len] or "profile"


def _seed_role_profiles(conn) -> None:
    """Fill an empty role_profiles table from the user's seed file or the bundled examples."""
    if conn.execute("SELECT COUNT(*) FROM role_profiles").fetchone()[0]:
        return
    source = paths.ROLE_PROFILE_SEED if paths.ROLE_PROFILE_SEED.exists() else paths.ROLE_PROFILE_EXAMPLE
    try:
        items = json.loads(source.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        items = []

    def _legacy(key: str) -> str:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
        return (row["value"] or "").strip() if row else ""

    for pid, item in enumerate(items, start=1):
        # Older versions stored names and CV paths for profiles 1-3 in settings.
        legacy_name = _legacy(f"profile_{pid}_name")
        if re.fullmatch(r"profile\s*\d+", legacy_name, re.IGNORECASE):
            legacy_name = ""        # a placeholder, not a name the user chose
        name = legacy_name or item.get("name") or f"Profile {pid}"
        cv_path = _legacy(f"profile_{pid}_cv_path") or item.get("cv_path", "")
        conn.execute(
            "INSERT INTO role_profiles (id, name, slug, keywords, headline, focus, cert_tags, cv_path) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (pid, name, item.get("slug") or slugify(name), item.get("keywords", ""),
             item.get("headline", ""), item.get("focus", ""), item.get("cert_tags", ""), cv_path),
        )


def get_role_profiles(active_only: bool = True) -> list[dict]:
    sql = "SELECT * FROM role_profiles"
    if active_only:
        sql += " WHERE active=1"
    with _connect() as conn:
        rows = conn.execute(sql + " ORDER BY id").fetchall()
    return [dict(r) for r in rows]


def get_role_profile(profile_id: int | None) -> dict | None:
    if not profile_id:
        return None
    with _connect() as conn:
        row = conn.execute("SELECT * FROM role_profiles WHERE id=?", (profile_id,)).fetchone()
    return dict(row) if row else None


def save_role_profile(profile_id: int | None = None, *, name: str, keywords: str = "",
                      headline: str = "", focus: str = "", cert_tags: str = "",
                      cv_path: str = "", slug: str = "") -> int:
    """Insert a role profile (profile_id=None) or update an existing one. Returns its id."""
    name = name.strip()
    if not name:
        raise ValueError("A role profile needs a name.")
    values = (name, slug.strip() or slugify(name), keywords.strip(), headline.strip(),
              focus.strip(), cert_tags.strip(), cv_path.strip())
    with _connect() as conn:
        if profile_id is None:
            cur = conn.execute(
                "INSERT INTO role_profiles (name, slug, keywords, headline, focus, cert_tags, cv_path) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", values)
            return int(cur.lastrowid)
        conn.execute(
            "UPDATE role_profiles SET name=?, slug=?, keywords=?, headline=?, focus=?, "
            "cert_tags=?, cv_path=? WHERE id=?", values + (profile_id,))
    return int(profile_id)


def delete_role_profile(profile_id: int) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM role_profiles WHERE id=?", (profile_id,))
        conn.execute("DELETE FROM role_cvs WHERE profile_id=?", (profile_id,))


def get_profile_name(profile_id: int | None) -> str:
    row = get_role_profile(profile_id)
    if row:
        return row["name"]
    return f"Profile {profile_id}" if profile_id else "—"


def get_profile_cv_path(profile_id: int | None) -> str:
    """Source CV for a role profile, falling back to the global master CV."""
    row = get_role_profile(profile_id)
    stored = (row or {}).get("cv_path") or ""
    if stored and os.path.isabs(stored):
        return stored
    return get_cv_path()


# ---------------------------------------------------------------------------
# Base CVs per (role profile, language)
# ---------------------------------------------------------------------------

def upsert_role_cv(profile_id: int, language: str, cv_path: str):
    with _connect() as conn:
        conn.execute(
            """
            INSERT INTO role_cvs (profile_id, language, cv_path, generated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(profile_id, language) DO UPDATE SET
                cv_path=excluded.cv_path,
                generated_at=excluded.generated_at
            """,
            (profile_id, language, cv_path, datetime.now().isoformat(timespec="seconds")),
        )


def get_role_cvs() -> dict:
    """Returns dict keyed by (profile_id, language) -> full row dict."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM role_cvs").fetchall()
    return {(r["profile_id"], r["language"]): dict(r) for r in rows}


def assign_base_cv_to_job(job_id: int) -> bool:
    """Give an approved job the base CV matching its role profile and language."""
    with _connect() as conn:
        job = conn.execute(
            "SELECT role_profile, language FROM jobs WHERE id=?", (job_id,)
        ).fetchone()
        if not job or not job["role_profile"] or not job["language"]:
            return False
        rec = conn.execute(
            "SELECT cv_path FROM role_cvs WHERE profile_id=? AND language=?",
            (job["role_profile"], job["language"]),
        ).fetchone()
        if not rec or not paths.resolve(rec["cv_path"]).exists():
            return False
        conn.execute("UPDATE jobs SET cv_path=? WHERE id=?", (rec["cv_path"], job_id))
    return True


def assign_base_cvs_to_approved() -> int:
    """Give every approved job without a CV its matching base CV. Returns how many changed."""
    with _connect() as conn:
        cur = conn.execute("""
            UPDATE jobs
            SET cv_path = (
                SELECT cv_path FROM role_cvs
                WHERE profile_id = jobs.role_profile AND language = jobs.language
            )
            WHERE status = 'approved' AND cv_path IS NULL
              AND role_profile IS NOT NULL AND language IS NOT NULL
              AND EXISTS (
                SELECT 1 FROM role_cvs
                WHERE profile_id = jobs.role_profile AND language = jobs.language
              )
        """)
        return cur.rowcount


# ---------------------------------------------------------------------------
# Certificates
# ---------------------------------------------------------------------------

def get_certs_for_role(profile_id: int | None, limit: int = 6) -> list[dict]:
    """Newest active certificates whose tags overlap the role profile's cert_tags."""
    row = get_role_profile(profile_id)
    tags = [t.strip().lower() for t in ((row or {}).get("cert_tags") or "").split(",") if t.strip()]
    sql = "SELECT cert_name, issuer, year FROM certificates WHERE is_active=1"
    params: list = []
    if tags:
        sql += " AND (" + " OR ".join("LOWER(tags) LIKE ?" for _ in tags) + ")"
        params = [f"%{t}%" for t in tags]
    sql += " ORDER BY year DESC LIMIT ?"
    params.append(limit)
    with _connect() as conn:
        rows = conn.execute(sql, params).fetchall()
    return [dict(r) for r in rows]


def cert_lines(profile_id: int | None) -> list[str]:
    """Certificates formatted for a CV: 'Name — Issuer (Year)'."""
    out = []
    for c in get_certs_for_role(profile_id):
        if c["issuer"] and c["year"]:
            out.append(f"{c['cert_name']} — {c['issuer']} ({c['year']})")
        elif c["issuer"]:
            out.append(f"{c['cert_name']} — {c['issuer']}")
        else:
            out.append(c["cert_name"])
    return out
