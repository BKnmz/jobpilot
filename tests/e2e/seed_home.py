"""Seed a throwaway JOBPILOT_HOME with dummy data.

Run as a subprocess:  python seed_home.py <repo_root> [--no-profiles]

It runs in its own process because jobpilot.paths reads JOBPILOT_HOME once, at import time,
and the pytest process already points somewhere else.
All names, companies and contact details below are invented. The only input file is the
git-tracked master_cv.example.md (fictional "Alex Demo").
"""
import shutil
import sys
from pathlib import Path

repo_root = Path(sys.argv[1])
sys.path.insert(0, str(repo_root))

from jobpilot import db, paths  # noqa: E402

PROFILES = [
    dict(name="Supply Chain Analyst", keywords="supply chain, logistics, SAP, forecasting, inventory",
         headline="Supply Chain Analyst | Logistics",
         focus="Lead with logistics analytics and process improvements with measurable results.",
         cert_tags="data, logistics"),
    dict(name="Operations Analyst", keywords="operations, reporting, Power BI, SQL, process improvement",
         headline="Operations Analyst | Reporting and Process Improvement",
         focus="Lead with reporting, dashboards and process improvements.", cert_tags="data, analytics"),
]

JOBS = [
    ("Supply Chain Analyst", "Hafenlicht Logistics GmbH", "Hamburg, Germany",
     "We run warehouses and delivery routes across northern Europe and need a Supply Chain Analyst. "
     "You analyse inventory and delivery data in SAP and SQL and publish weekly reports in Power BI. "
     "You work closely with warehouse managers and the purchasing team. Experience with demand "
     "forecasting and process improvement is required. Kubernetes knowledge is not needed.",
     "https://example.com/jobs/hafenlicht-sca", "en"),
    ("Logistikanalyst/in (m/w/d)", "Weserkontor Handel AG", "Bremen, Deutschland",
     "Wir suchen eine Logistikanalystin oder einen Logistikanalysten für unser Lager in Bremen. "
     "Sie werten Bestands- und Lieferdaten in SAP und SQL aus und erstellen Berichte in Power BI. "
     "Sie arbeiten eng mit der Lagerleitung und dem Einkauf zusammen. Erfahrung in der "
     "Bedarfsplanung ist von Vorteil.", "https://example.com/jobs/weserkontor-la", "de"),
    ("Tedarik Zinciri Analisti", "Marmara Lojistik A.Ş.", "İstanbul, Türkiye",
     "Depo ve teslimat operasyonlarımız için deneyimli bir Tedarik Zinciri Analisti arıyoruz. "
     "SAP ve SQL ile stok ve teslimat verilerini analiz edecek, Power BI ile haftalık raporlar "
     "hazırlayacaksınız. Depo yöneticileri ve satın alma ekibiyle yakın çalışacaksınız. Talep "
     "tahmini deneyimi gereklidir.", "https://example.com/jobs/marmara-tza", "tr"),
]


def main() -> None:
    with_profiles = "--no-profiles" not in sys.argv
    db.init_db()
    shutil.copy(repo_root / "master_cv.example.md", paths.DEFAULT_MASTER_CV)
    db.set_profile_fields({
        "full_name": "Alex Demo", "email": "alex.demo@example.com", "phone": "+49 151 000 0000",
        "location": "Hamburg, Germany", "linkedin_url": "linkedin.com/in/alexdemo",
    })
    role = None
    if with_profiles and not db.get_role_profiles():
        ids = [db.save_role_profile(None, **p) for p in PROFILES]
        role = ids[1]                  # jobs start tagged "Operations Analyst"
    elif with_profiles:
        role = db.get_role_profiles()[-1]["id"]
    for title, company, location, text, url, lang in JOBS:
        db.insert_job(title, company, location, text, url, role_profile=role, language=lang)


if __name__ == "__main__":
    main()
