"""
Orthanc REST API connector.
All communication with the Orthanc server goes through this module.

Connection priority:
  1. Internal URL (http://10.0.1.215:8042)  — used when on the same network
  2. Public URL  (https://orthanc.unboxed-2026.ovh) — automatic fallback
"""

import httpx
from typing import Any

# ── Orthanc server settings ───────────────────────────────────────────
ORTHANC_URL_INTERNAL = "http://10.0.1.215:8042"
ORTHANC_URL_PUBLIC   = "https://orthanc.unboxed-2026.ovh"
ORTHANC_USER         = "unboxed"
ORTHANC_PASS         = "unboxed2026"
# ─────────────────────────────────────────────────────────────────────

AUTH    = (ORTHANC_USER, ORTHANC_PASS)
TIMEOUT = 10.0


def _resolve_base_url() -> str:
    """
    Try the internal URL first (faster, no SSL).
    Fall back to the public HTTPS URL if unreachable.
    """
    for url in (ORTHANC_URL_INTERNAL, ORTHANC_URL_PUBLIC):
        try:
            httpx.get(f"{url}/system", auth=AUTH, timeout=3.0).raise_for_status()
            return url
        except Exception:
            continue
    # Return public as last resort (will raise properly in _get)
    return ORTHANC_URL_PUBLIC


# Resolved once at import time; can be refreshed by calling _resolve_base_url()
ORTHANC_URL: str = _resolve_base_url()


def _get(path: str) -> Any:
    url = f"{ORTHANC_URL}{path}"
    response = httpx.get(url, auth=AUTH, timeout=TIMEOUT)
    response.raise_for_status()
    return response.json()


# ───────────────────────────── Patients ──────────────────────────────

def list_patients() -> list[dict]:
    """Return a list of patients with their metadata."""
    ids = _get("/patients")
    patients = []
    for pid in ids:
        info = _get(f"/patients/{pid}")
        main_tags = info.get("MainDicomTags", {})
        patients.append(
            {
                "orthanc_id": pid,
                "patient_id": main_tags.get("PatientID", "N/A"),
                "patient_name": main_tags.get("PatientName", "Unknown").replace("^", " ").strip(),
                "birth_date": main_tags.get("PatientBirthDate", ""),
                "sex": main_tags.get("PatientSex", ""),
                "nb_studies": len(info.get("Studies", [])),
            }
        )
    return patients


def get_patient(orthanc_id: str) -> dict:
    return _get(f"/patients/{orthanc_id}")


# ───────────────────────────── Studies ───────────────────────────────

def list_studies_for_patient(orthanc_id: str) -> list[dict]:
    """Return all studies (exams) for a given patient."""
    info = _get(f"/patients/{orthanc_id}")
    study_ids = info.get("Studies", [])
    studies = []
    for sid in study_ids:
        study = _get(f"/studies/{sid}")
        tags = study.get("MainDicomTags", {})
        series = study.get("Series", [])

        # Collect modalities across series
        modalities = set()
        for ser_id in series:
            ser = _get(f"/series/{ser_id}")
            mod = ser.get("MainDicomTags", {}).get("Modality", "")
            if mod:
                modalities.add(mod)

        studies.append(
            {
                "orthanc_id": sid,
                "study_instance_uid": tags.get("StudyInstanceUID", sid),
                "study_date": tags.get("StudyDate", ""),
                "study_description": tags.get("StudyDescription", "No description"),
                "accession_number": tags.get("AccessionNumber", ""),
                "modalities": list(modalities),
                "nb_series": len(series),
            }
        )
    # Sort by date descending (most recent first)
    studies.sort(key=lambda s: s["study_date"], reverse=True)
    return studies


def get_study(orthanc_id: str) -> dict:
    return _get(f"/studies/{orthanc_id}")
