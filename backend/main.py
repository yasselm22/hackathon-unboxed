"""
Main FastAPI application.
Run with:
    uvicorn main:app --reload --port 8000
"""

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, PlainTextResponse, FileResponse
from fastapi.staticfiles import StaticFiles
from pathlib import Path
import httpx

import orthanc
import reports
import pipeline

app = FastAPI(title="Radiology Report Viewer", version="1.0.0")

# ── CORS (needed if you serve the frontend from a different origin) ───
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# ── Serve the frontend static files ──────────────────────────────────
FRONTEND_DIR = Path(__file__).parent.parent / "frontend"
app.mount("/static", StaticFiles(directory=str(FRONTEND_DIR)), name="static")


# ─────────────────────────────────────────────────────────────────────
# Root – serve the main page
# ─────────────────────────────────────────────────────────────────────
@app.get("/", response_class=HTMLResponse)
async def root():
    index = FRONTEND_DIR / "index.html"
    if index.exists():
        return HTMLResponse(content=index.read_text(encoding="utf-8"))
    raise HTTPException(status_code=404, detail="index.html not found")


# ─────────────────────────────────────────────────────────────────────
# Patients
# ─────────────────────────────────────────────────────────────────────
@app.get("/api/patients")
async def get_patients():
    """Return list of all patients from Orthanc."""
    try:
        return orthanc.list_patients()
    except httpx.ConnectError:
        raise HTTPException(
            status_code=503,
            detail=(
                "Cannot connect to Orthanc server. "
                "Tried internal (http://10.0.1.215:8042) and public (https://orthanc.unboxed-2026.ovh). "
                "Check network access and credentials."
            ),
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))


# ─────────────────────────────────────────────────────────────────────
# Exams (Studies)
# ─────────────────────────────────────────────────────────────────────
@app.get("/api/exams/{patient_id}")
async def get_exams(patient_id: str):
    """Return all studies for a patient (by Orthanc patient ID)."""
    try:
        studies = orthanc.list_studies_for_patient(patient_id)
        # Annotate each study with report availability
        for study in studies:
            uid = study["study_instance_uid"]
            study["has_report"] = reports.report_exists(uid)
        return studies
    except httpx.ConnectError:
        raise HTTPException(status_code=503, detail="Cannot connect to Orthanc server.")
    except httpx.HTTPStatusError as e:
        raise HTTPException(status_code=e.response.status_code, detail=str(e))


# ─────────────────────────────────────────────────────────────────────
# Analysis pipeline
# ─────────────────────────────────────────────────────────────────────
@app.post("/api/analyze/{study_orthanc_id}")
async def start_analysis(study_orthanc_id: str, study_uid: str):
    """
    Launch the full pipeline (download → extract_seg → report) for a study.
    Returns a job_id to poll with GET /api/analyze/status/{job_id}.
    """
    try:
        job_id = pipeline.start_pipeline(study_orthanc_id, study_uid)
        return {"job_id": job_id, "status": "pending"}
    except Exception as exc:
        raise HTTPException(status_code=500, detail=str(exc))


@app.get("/api/analyze/status/{job_id}")
async def analysis_status(job_id: str):
    """Poll the status of a running pipeline job."""
    job = pipeline.get_job(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="Job introuvable.")
    return job


# ─────────────────────────────────────────────────────────────────────
# Report
# ─────────────────────────────────────────────────────────────────────
@app.get("/api/report/{study_uid}")
async def get_report(study_uid: str):
    """Return the generated radiology report for a study."""
    result = reports.get_report_content(study_uid)
    if result is None:
        raise HTTPException(
            status_code=404,
            detail=f"No report found for StudyInstanceUID: {study_uid}",
        )
    content, mime = result
    if mime == "text/html":
        return HTMLResponse(content=content)
    return PlainTextResponse(content=content, media_type=mime)
