"""
Report manager.
Looks up generated radiology reports on disk by StudyInstanceUID.

Expected convention:
    reports/<StudyInstanceUID>.html   (HTML report)
or
    reports/<StudyInstanceUID>.txt    (plain text report)

The REPORTS_DIR can be changed to match your AI pipeline output folder.
"""

import os
from pathlib import Path

# ── Change this to the folder where your AI saves its reports ──────────
REPORTS_DIR = Path(__file__).parent.parent / "reports"
# ───────────────────────────────────────────────────────────────────────

SUPPORTED_EXTENSIONS = [".html", ".htm", ".txt", ".md"]


def _find_report(study_uid: str) -> Path | None:
    """Return path of the report file if it exists, else None."""
    for ext in SUPPORTED_EXTENSIONS:
        candidate = REPORTS_DIR / f"{study_uid}{ext}"
        if candidate.exists():
            return candidate
    return None


def report_exists(study_uid: str) -> bool:
    return _find_report(study_uid) is not None


def get_report_content(study_uid: str) -> tuple[str, str] | None:
    """
    Returns (content, mime_type) or None if not found.
    """
    path = _find_report(study_uid)
    if path is None:
        return None
    text = path.read_text(encoding="utf-8", errors="replace")
    ext = path.suffix.lower()
    if ext in (".html", ".htm"):
        mime = "text/html"
    elif ext == ".md":
        mime = "text/markdown"
    else:
        mime = "text/plain"
    return text, mime
