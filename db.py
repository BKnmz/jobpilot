import sqlite3
import os
from datetime import date, datetime

DB_PATH = os.path.join(os.path.dirname(__file__), "jobs.db")
ROOT    = os.path.dirname(os.path.abspath(__file__))


def _connect():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


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
        """)
        # Add role_profile and language columns to jobs if they don't exist yet
        existing = [r[1] for r in conn.execute("PRAGMA table_info(jobs)").fetchall()]
        if "role_profile" not in existing:
            conn.execute("ALTER TABLE jobs ADD COLUMN role_profile INTEGER")
        if "language" not in existing:
            conn.execute("ALTER TABLE jobs ADD COLUMN language TEXT")

        # Add last_opened_at column to searches if it doesn't exist yet
        s_cols = [r[1] for r in conn.execute("PRAGMA table_info(searches)").fetchall()]
        if "last_opened_at" not in s_cols:
            conn.execute("ALTER TABLE searches ADD COLUMN last_opened_at TEXT")

        # Insert empty profile rows if they don't exist yet
        for field in ("full_name", "email", "phone", "location", "linkedin_url"):
            conn.execute(
                "INSERT OR IGNORE INTO profile (field_name, field_value) VALUES (?, ?)",
                (field, ""),
            )


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


def update_score(job_id, score, notes):
    with _connect() as conn:
        conn.execute(
            "UPDATE jobs SET match_score=?, notes=? WHERE id=?",
            (score, notes, job_id),
        )


def update_status(job_id, status):
    with _connect() as conn:
        conn.execute("UPDATE jobs SET status=? WHERE id=?", (status, job_id))


def update_cv_path(job_id, cv_path):
    with _connect() as conn:
        conn.execute("UPDATE jobs SET cv_path=? WHERE id=?", (cv_path, job_id))


def get_jobs_by_status(status):
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status=? ORDER BY match_score DESC",
            (status,),
        ).fetchall()
    return [dict(r) for r in rows]


def get_profile():
    with _connect() as conn:
        rows = conn.execute("SELECT field_name, field_value FROM profile").fetchall()
    return {r["field_name"]: r["field_value"] for r in rows}


# ---------------------------------------------------------------------------
# Search management
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


# ---------------------------------------------------------------------------
# Role CV management
# ---------------------------------------------------------------------------

def upsert_role_cv(profile_id: int, language: str, cv_path: str):
    from datetime import datetime
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
    """Returns dict keyed by (profile_id, language) → full row dict."""
    with _connect() as conn:
        rows = conn.execute("SELECT * FROM role_cvs").fetchall()
    return {(r["profile_id"], r["language"]): dict(r) for r in rows}


# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------

def get_setting(key: str, default: str = "") -> str:
    with _connect() as conn:
        row = conn.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return row["value"] if row else default


def set_setting(key: str, value: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
            (key, value),
        )


def get_cv_path() -> str:
    """Return the global master CV path, falling back to project-root master_cv.md."""
    stored = get_setting("master_cv_path", "")
    if stored and os.path.isabs(stored):
        return stored
    return os.path.join(ROOT, "master_cv.md")


def get_profile_name(profile_id: int) -> str:
    """Return the user-configured display name for a profile, or the built-in default."""
    defaults = {1: "Cybersecurity/GRC", 2: "Product Owner", 3: "Requirements/BA"}
    stored = get_setting(f"profile_{profile_id}_name", "")
    return stored if stored else defaults.get(profile_id, f"Profile {profile_id}")


def get_profile_cv_path(profile_id: int) -> str:
    """Return the CV path for a specific profile, falling back to the global master CV."""
    stored = get_setting(f"profile_{profile_id}_cv_path", "")
    if stored and os.path.isabs(stored):
        return stored
    return get_cv_path()


# ---------------------------------------------------------------------------
# Search open-tracking
# ---------------------------------------------------------------------------

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
# CV assignment helper
# ---------------------------------------------------------------------------

def assign_base_cv_to_job(job_id: int) -> bool:
    """Try to assign a matching base CV to a single job. Returns True if assigned."""
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
        if not rec:
            return False
        cv_abs = os.path.join(ROOT, rec["cv_path"])
        if not os.path.exists(cv_abs):
            return False
        conn.execute("UPDATE jobs SET cv_path=? WHERE id=?", (rec["cv_path"], job_id))
    return True


def get_certs_for_role(profile_num: int) -> list[dict]:
    """Return top 6 certs for a role profile (1=Cybersec, 2=PO, 3=BA)."""
    tag_filters = {
        1: "tags LIKE '%cybersec%' OR tags LIKE '%grc%' OR tags LIKE '%compliance%'",
        2: "tags LIKE '%product%' OR tags LIKE '%agile%' OR tags LIKE '%ai%'",
        3: "tags LIKE '%data%' OR tags LIKE '%ba%' OR tags LIKE '%cybersec%'",
    }
    where = tag_filters.get(profile_num, "1=1")
    with _connect() as conn:
        rows = conn.execute(
            f"SELECT cert_name, issuer, year FROM certificates "
            f"WHERE is_active=1 AND ({where}) ORDER BY year DESC LIMIT 6"
        ).fetchall()
    return [dict(r) for r in rows]


# --- Smoke test ---
if __name__ == "__main__":
    init_db()
    print("DB initialised.")

    insert_job(
        title="Dummy Developer",
        company="Test Corp",
        location="Berlin",
        jd_text="We need a dummy developer for testing purposes.",
        source_url="https://example.com/dummy-job",
    )

    jobs = get_jobs_by_status("new")
    print(f"Jobs with status='new': {len(jobs)}")
    for j in jobs:
        print(f"  [{j['id']}] {j['title']} @ {j['company']} — {j['location']}")

    profile = get_profile()
    print(f"Profile fields: {list(profile.keys())}")

    # Clean up dummy row
    with _connect() as conn:
        conn.execute("DELETE FROM jobs WHERE source_url='https://example.com/dummy-job'")
    print("Dummy row deleted. Smoke test passed.")
