"""
languages.py — everything that differs per output language.

Adding a language means adding one entry to LANGUAGES. CVs are written
directly in the target language by the model, never translated from English.
"""
from dataclasses import dataclass, field


@dataclass(frozen=True)
class Language:
    code: str
    name: str            # English name, used in prompts
    native: str          # shown in the UI
    headings: dict       # CV section headings, in output order
    cv_rules: str        # conventions the CV writer must follow
    present: str         # word for an ongoing job ("Present")
    months: tuple        # month names, for dated letters and footers
    experience_aliases: tuple = field(default_factory=tuple)


LANGUAGES: dict[str, Language] = {
    "en": Language(
        code="en",
        name="English",
        native="English",
        headings={
            "summary": "Professional Summary",
            "experience": "Professional Experience",
            "education": "Education",
            "certifications": "Certifications",
            "skills": "Skills",
            "languages": "Languages",
        },
        cv_rules=(
            "Write entirely in English. No photo, no date of birth, no marital status. "
            "Use strong, plain verbs; no first-person pronouns in bullets."
        ),
        present="Present",
        months=("January", "February", "March", "April", "May", "June", "July",
                "August", "September", "October", "November", "December"),
        experience_aliases=("experience", "work experience", "professional experience"),
    ),
    "de": Language(
        code="de",
        name="German",
        native="Deutsch",
        headings={
            "summary": "Berufsprofil",
            "experience": "Berufserfahrung",
            "education": "Ausbildung",
            "certifications": "Zertifizierungen",
            "skills": "Kernkompetenzen",
            "languages": "Sprachen",
        },
        cv_rules=(
            "Schreibe vollständig auf Deutsch, mit korrekten Umlauten und ß. "
            "Fachbegriffe, die im Deutschen üblicherweise auf Englisch verwendet werden "
            "(z. B. Software, Marketing, Know-how, Team Lead), bleiben auf Englisch. "
            "Kein Foto, kein Geburtsdatum, kein Familienstand. "
            "Stichpunkte im Nominalstil oder mit Verb am Anfang, ohne 'ich'."
        ),
        present="heute",
        months=("Januar", "Februar", "März", "April", "Mai", "Juni", "Juli",
                "August", "September", "Oktober", "November", "Dezember"),
        experience_aliases=("berufserfahrung", "berufliche erfahrung", "berufspraxis"),
    ),
    "tr": Language(
        code="tr",
        name="Turkish",
        native="Türkçe",
        headings={
            "summary": "Profesyonel Özet",
            "experience": "İş Deneyimi",
            "education": "Eğitim",
            "certifications": "Sertifikalar",
            "skills": "Yetkinlikler",
            "languages": "Diller",
        },
        cv_rules=(
            "Tamamen Türkçe yaz; Türkçe karakterleri (ç, ğ, ı, İ, ö, ş, ü) doğru kullan. "
            "Türkçede İngilizce kullanılan teknik terimler (ör. Software, Marketing, "
            "Roadmap) İngilizce kalsın. Fotoğraf, doğum tarihi, medeni durum, T.C. kimlik "
            "numarası ve askerlik bilgisi ekleme. Maddelerde 'ben' kullanma; kısa, "
            "sonuç odaklı ifadeler yaz."
        ),
        present="Halen",
        months=("Ocak", "Şubat", "Mart", "Nisan", "Mayıs", "Haziran", "Temmuz",
                "Ağustos", "Eylül", "Ekim", "Kasım", "Aralık"),
        experience_aliases=("iş deneyimi", "deneyim", "iş tecrübesi", "profesyonel deneyim"),
    ),
}

DEFAULT_LANGUAGE = "en"


def get(code: str | None) -> Language:
    """Return the language for a code, falling back to English for unknown codes."""
    return LANGUAGES.get((code or "").lower(), LANGUAGES[DEFAULT_LANGUAGE])


def codes() -> list[str]:
    return list(LANGUAGES)


def experience_headings() -> set[str]:
    """Lower-cased headings that mark the work-experience section in any language."""
    out: set[str] = set()
    for lang in LANGUAGES.values():
        out.add(lang.headings["experience"].lower())
        out.update(a.lower() for a in lang.experience_aliases)
    return out


def format_date(lang_code: str, year: int, month: int, day: int | None = None) -> str:
    """'15 November 2026' / '15. November 2026' / '15 Kasım 2026' (day optional)."""
    lang = get(lang_code)
    m = lang.months[month - 1]
    if day is None:
        return f"{m} {year}"
    if lang.code == "de":
        return f"{day}. {m} {year}"
    return f"{day} {m} {year}"
