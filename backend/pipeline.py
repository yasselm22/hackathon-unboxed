"""
Analysis pipeline.

For a given Orthanc study:
  1. Fetch study metadata (MainDicomTags)
  2. Download the DICOM archive (ZIP) from Orthanc
  3. Extract the ZIP
  4. Run extract_seg  → parse output into structured dict
  5. Save structured data as JSON
  6. Send JSON to Mistral LLM → generate radiology report text
  7. Wrap everything in an HTML report → reports/<StudyInstanceUID>.html
"""

import json
import threading
import zipfile
import uuid
from pathlib import Path
from datetime import datetime
from typing import Any

import httpx

from orthanc import ORTHANC_URL, AUTH

try:
    from dcm_seg_nodules import extract_seg
    SEG_AVAILABLE = True
except ImportError:
    SEG_AVAILABLE = False

try:
    from mistralai import Mistral
    MISTRAL_AVAILABLE = True
except ImportError:
    MISTRAL_AVAILABLE = False

try:
    import SimpleITK as sitk
    import matplotlib
    matplotlib.use('Agg')  # Non-interactive backend
    import matplotlib.pyplot as plt
    import numpy as np
    VISUALIZATION_AVAILABLE = True
except ImportError:
    VISUALIZATION_AVAILABLE = False

# ── Config ────────────────────────────────────────────────────────────
MISTRAL_API_KEY = "HtxRNKpTEWLLeItdYokmbvBMP6cmx8Kd"
MISTRAL_MODEL   = "mistral-small-latest"

# ── Directories ───────────────────────────────────────────────────────
BASE_DIR      = Path(__file__).parent.parent
DOWNLOADS_DIR = BASE_DIR / "downloads"
REPORTS_DIR   = BASE_DIR / "reports"
HISTORY_FILE  = BASE_DIR / "reports.json" # <--- AJOUT : Chemin vers le fichier JSON généré

# ── In-memory job tracker  ────────────────────────────────────────────
JOBS: dict[str, dict] = {}


# ─────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────

def start_pipeline(study_orthanc_id: str, study_uid: str) -> str:
    """Launch the pipeline in a background thread. Returns the job_id."""
    job_id = str(uuid.uuid4())
    JOBS[job_id] = {
        "status": "pending",
        "message": "En attente de démarrage…",
        "study_uid": study_uid,
        "study_orthanc_id": study_orthanc_id,
    }
    t = threading.Thread(
        target=_run,
        args=(job_id, study_orthanc_id, study_uid),
        daemon=True,
    )
    t.start()
    return job_id


def get_job(job_id: str) -> dict | None:
    return JOBS.get(job_id)


# ─────────────────────────────────────────────────────────────────────
# Helper : Get History
# ─────────────────────────────────────────────────────────────────────
def _get_patient_history(patient_id: str) -> str:
    """
    Lit reports.json et retourne l'historique du patient sous forme de texte.
    """
    if not HISTORY_FILE.exists():
        return "No previous history file found."

    try:
        with open(HISTORY_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        patients = data.get("patients", {})
        patient_data = patients.get(patient_id)

        if not patient_data:
            return "No previous records found for this patient."

        series = patient_data.get("series", [])
        if not series:
            return "Patient found but no prior series recorded."

        # On construit un texte lisible pour le LLM
        history_txt = []
        for s in series:
            date = s.get("date", "Unknown Date")
            summary = s.get("summary", "No details")
            accession = s.get("accession_id", "N/A")
            history_txt.append(f"- Date: {date} (Acc: {accession})\n  Report: {summary}")
        
        return "\n".join(history_txt)

    except Exception as e:
        return f"Error reading history: {str(e)}"

# ─────────────────────────────────────────────────────────────────────
# Main pipeline runner
# ─────────────────────────────────────────────────────────────────────

def _run(job_id: str, study_orthanc_id: str, study_uid: str):
    try:
        print(f"[{job_id}] Pipeline started for StudyInstanceUID={study_uid} (Orthanc ID={study_orthanc_id})")
        # Step 1 — Metadata
        _update(job_id, "running", "Récupération des métadonnées de l'examen…")
        study_info = _fetch_study_info(study_orthanc_id)
        
        # --- AJOUT : Récupération de l'ID patient pour l'historique ---
        patient_tags = study_info.get("PatientMainDicomTags", {})
        patient_id = patient_tags.get("PatientID", "")
        
        # Récupération de l'historique
        patient_history = _get_patient_history(patient_id) 
        # -------------------------------------------------------------

        # Step 2 — Download
        _update(job_id, "running", "Téléchargement de l'archive DICOM depuis Orthanc…")
        zip_path = _download_archive(study_orthanc_id, study_uid)

        # Step 3 — Extract ZIP
        _update(job_id, "running", "Extraction de l'archive ZIP…")
        ct_dir = _extract_zip(zip_path, study_uid)

        # Step 4 — Segmentation → structured dict
        _update(job_id, "running", "Analyse de segmentation en cours (extract_seg)…")
        seg_data = _run_seg_and_parse(ct_dir)

        # Step 5 — Save JSON
        _update(job_id, "running", "Sauvegarde des données structurées en JSON…")
        json_path = _save_seg_json(study_uid, study_info, seg_data)

        # Step 6 — LLM report generation
        _update(job_id, "running", "Génération du rapport via Mistral LLM…")
        
        # --- MODIFICATION : On passe l'historique à la fonction ---
        llm_report = _generate_llm_report(study_info, seg_data, patient_history)
        # ----------------------------------------------------------

        # Step 7 — Final HTML
        _update(job_id, "running", "Génération du rapport HTML final…")
        _generate_html_report(study_uid, study_info, ct_dir, seg_data, llm_report)

        _update(job_id, "done", "Rapport généré avec succès.")

    except Exception as exc:
        _update(job_id, "error", f"Erreur : {exc}")


def _update(job_id: str, status: str, message: str):
    JOBS[job_id]["status"]  = status
    JOBS[job_id]["message"] = message


# ─────────────────────────────────────────────────────────────────────
# Step 1 : metadata
# ─────────────────────────────────────────────────────────────────────

def _fetch_study_info(study_orthanc_id: str) -> dict:
    url      = f"{ORTHANC_URL}/studies/{study_orthanc_id}"
    response = httpx.get(url, auth=AUTH, timeout=15.0)
    response.raise_for_status()
    return response.json()


# ─────────────────────────────────────────────────────────────────────
# Step 2 : download
# ─────────────────────────────────────────────────────────────────────

def _download_archive(study_orthanc_id: str, study_uid: str) -> Path:
    work_dir = DOWNLOADS_DIR / study_uid
    work_dir.mkdir(parents=True, exist_ok=True)
    zip_path = work_dir / "archive.zip"

    url = f"{ORTHANC_URL}/studies/{study_orthanc_id}/archive"
    with httpx.stream("GET", url, auth=AUTH, timeout=600.0) as r:
        r.raise_for_status()
        with open(zip_path, "wb") as f:
            for chunk in r.iter_bytes(chunk_size=65536):
                f.write(chunk)
    return zip_path


# ─────────────────────────────────────────────────────────────────────
# Step 3 : extract ZIP
# ─────────────────────────────────────────────────────────────────────

def _extract_zip(zip_path: Path, study_uid: str) -> Path:
    ct_dir = zip_path.parent / "dicom"
    ct_dir.mkdir(exist_ok=True)
    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(ct_dir)

    # Orthanc archives nest files: Patient/Study/Series/*.dcm
    # Walk down to find the deepest folder that actually contains .dcm files.
    return _find_dcm_folder(ct_dir)


def _find_dcm_folder(root: Path) -> Path:
    """
    Recursively find the first directory that contains .dcm files.
    If multiple series exist, return the one with the most files.
    """
    best_dir = root
    best_count = 0

    for dirpath in root.rglob("*"):
        if not dirpath.is_dir():
            continue
        dcm_count = sum(1 for f in dirpath.iterdir() if f.suffix.lower() == ".dcm")
        if dcm_count > best_count:
            best_count = dcm_count
            best_dir = dirpath

    # Fallback: if no .dcm found in subdirs, check root itself
    if best_count == 0:
        root_count = sum(1 for f in root.iterdir() if f.suffix.lower() == ".dcm")
        if root_count > 0:
            return root

    return best_dir


def _generate_seg_visualizations(seg_dcm_path: Path) -> list[str]:
    """
    Generate PNG visualizations from a DICOM SEG file.
    Returns a list of generated image filenames (relative to REPORTS_DIR).
    """
    if not VISUALIZATION_AVAILABLE:
        print("Warning: SimpleITK or matplotlib not available. Skipping visualizations.")
        return []

    try:
        # Read the DICOM SEG file
        print(f"Reading DICOM SEG from: {seg_dcm_path}")
        seg = sitk.ReadImage(str(seg_dcm_path))
        segment_array = sitk.GetArrayFromImage(seg)
        
        print(f"Segment array shape: {segment_array.shape}")
        print(f"Segment array dtype: {segment_array.dtype}")
        print(f"Segment array min/max: {segment_array.min()} / {segment_array.max()}")
        print(f"Unique values in segment: {np.unique(segment_array)}")
        
        # Generate a unique timestamp for the images
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        image_files = []

        # DICOM SEG contains binary masks (0 or segment_id)
        # We need to ensure we're displaying the mask correctly
        # Convert to binary if needed
        if segment_array.max() <= 1:
            # Already binary, multiply by 255 for visibility
            segment_array = (segment_array * 255).astype(np.uint8)
        
        # Maximum intensity projection (MIP) view
        mip_view = segment_array.max(axis=0)
        print(f"MIP view shape: {mip_view.shape}, max value: {mip_view.max()}")
        
        if mip_view.max() > 0:  # Only save if there's something to display
            fig, ax = plt.subplots(figsize=(10, 8))
            im = ax.imshow(mip_view, cmap='hot', interpolation='nearest', vmin=0, vmax=255)
            ax.set_title("Segmentation - Maximum Intensity Projection", fontsize=14)
            ax.axis('off')
            plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label='Segment Mask')
            
            filename = f"seg_mip_{timestamp}.png"
            filepath = REPORTS_DIR / filename
            plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
            plt.close(fig)
            image_files.append(filename)
            print(f"Saved MIP image: {filename}")

        # Middle axial slice
        num_slices = segment_array.shape[0]
        if num_slices > 0:
            middle_slice = segment_array[num_slices // 2, :, :]
            print(f"Middle slice max: {middle_slice.max()}")
            
            if middle_slice.max() > 0:
                fig, ax = plt.subplots(figsize=(10, 8))
                im = ax.imshow(middle_slice, cmap='hot', interpolation='nearest', vmin=0, vmax=255)
                ax.set_title(f"Segmentation - Axial Slice {num_slices // 2}/{num_slices}", fontsize=14)
                ax.axis('off')
                plt.colorbar(im, ax=ax, fraction=0.046, pad=0.04, label='Segment Mask')
                
                filename = f"seg_axial_{timestamp}.png"
                filepath = REPORTS_DIR / filename
                plt.savefig(filepath, dpi=150, bbox_inches='tight', facecolor='white')
                plt.close(fig)
                image_files.append(filename)
                print(f"Saved axial slice image: {filename}")

        if len(image_files) == 0:
            print("Warning: No images generated. Segment array might be all zeros.")
            
        print(f"Generated {len(image_files)} visualization(s): {image_files}")
        return image_files

    except Exception as e:
        print(f"Error generating visualizations: {e}")
        import traceback
        traceback.print_exc()
        return []


# ─────────────────────────────────────────────────────────────────────
# Step 4 : extract_seg → parse into structured dict
# ─────────────────────────────────────────────────────────────────────

def _run_seg_and_parse(ct_dir: Path) -> dict:
    """
    Run extract_seg then parse the text output into a structured dict.
    Returns a dict like:
      {"Accession Number": "...", "Summary": {...}, ..., "_images": [...]}
    """
    if not SEG_AVAILABLE:
        return {"_error": "Module dcm_seg_nodules non installé"}

    print(f"Running extract_seg on: {ct_dir}")
    print(f"Output dir: {REPORTS_DIR}")
    seg_result = extract_seg(str(ct_dir), output_dir=str(REPORTS_DIR))
    
    print(f"extract_seg result type: {type(seg_result)}")
    print(f"extract_seg result: {seg_result}")

    # extract_seg returns a tuple (seg_path, text_content) or just a string
    if isinstance(seg_result, tuple):
        seg_path = seg_result[0]  # Path to the DICOM SEG file
        txt = seg_result[-1]
        print(f"Extracted seg_path: {seg_path}")
        print(f"Extracted text length: {len(txt)}")
    else:
        txt = str(seg_result)
        seg_path = None
        print("extract_seg did not return a tuple, no seg_path available")
        
        # Try to find the DICOM SEG file manually in REPORTS_DIR
        seg_files = list(REPORTS_DIR.glob("*.dcm"))
        if seg_files:
            seg_path = str(seg_files[0])  # Take the first one
            print(f"Found DICOM SEG file manually: {seg_path}")

    # Parse the text into key-value pairs
    lines = txt.split("\n")
    data = {}
    summary = {}

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith("- "):
            # Summary line (starts with "- ")
            if ":" in line[2:]:
                key, value = line[2:].split(":", 1)
                summary[key.strip()] = value.strip()
        elif ":" in line:
            key, value = line.split(":", 1)
            data[key.strip()] = value.strip()

    if summary:
        data["Summary"] = summary

    # Keep the raw text too for debugging
    data["_raw_seg_output"] = txt

    # Generate visualization images from DICOM SEG
    image_files = []
    if seg_path:
        seg_path_obj = Path(seg_path)
        print(f"Checking if seg_path exists: {seg_path_obj} -> {seg_path_obj.exists()}")
        if seg_path_obj.exists():
            print(f"File size: {seg_path_obj.stat().st_size} bytes")
            image_files = _generate_seg_visualizations(seg_path_obj)
        else:
            print(f"WARNING: Seg path does not exist: {seg_path}")
    else:
        print("WARNING: No seg_path available for visualization")
        
    data["_images"] = image_files

    return data


# ─────────────────────────────────────────────────────────────────────
# Step 5 : save structured data as JSON
# ─────────────────────────────────────────────────────────────────────

def _save_seg_json(study_uid: str, study_info: dict, seg_data: dict) -> Path:
    """Merge Orthanc metadata + seg data and save as JSON."""
    tags         = study_info.get("MainDicomTags", {})
    patient_tags = study_info.get("PatientMainDicomTags", {})

    full_data = {
        "study_instance_uid": study_uid,
        "patient_id":   patient_tags.get("PatientID", "N/A"),
        "patient_name": patient_tags.get("PatientName", "Unknown").replace("^", " ").strip(),
        "study_date":   tags.get("StudyDate", ""),
        "study_description": tags.get("StudyDescription", ""),
        "accession_number":  tags.get("AccessionNumber", ""),
        "modality":     tags.get("ModalitiesInStudy", tags.get("Modality", "")),
        "seg_data":     seg_data,
    }

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    json_path = REPORTS_DIR / f"{study_uid}.json"
    json_path.write_text(json.dumps(full_data, indent=2, ensure_ascii=False), encoding="utf-8")
    return json_path


# ─────────────────────────────────────────────────────────────────────
# Step 6 : send to Mistral LLM → get radiology report text
# ─────────────────────────────────────────────────────────────────────

# --- MODIFICATION DE LA SIGNATURE : ajout de previous_history_text ---
def _generate_llm_report(study_info: dict, seg_data: dict, previous_history_text: str) -> str:
    """
    Build a prompt from the structured seg data and Orthanc metadata,
    send it to Mistral, and return the generated report text.
    """
    if not MISTRAL_AVAILABLE:
        return (
            "⚠ Le module `mistralai` n'est pas installé. "
            "Le rapport LLM n'a pas pu être généré. "
            "Installez-le avec : pip install mistralai"
        )

    tags         = study_info.get("MainDicomTags", {})
    patient_tags = study_info.get("PatientMainDicomTags", {})

    patient_id   = patient_tags.get("PatientID", "N/A")
    patient_name = patient_tags.get("PatientName", "Unknown").replace("^", " ").strip()
    study_date   = tags.get("StudyDate", "N/A")
    description  = tags.get("StudyDescription", "N/A")
    acc_number   = tags.get("AccessionNumber", "N/A")


    # Build a readable summary of SEG findings
    seg_summary_parts = []
    for k, v in seg_data.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            # Summary sub-dict
            for sk, sv in v.items():
                seg_summary_parts.append(f"  - {sk}: {sv}")
        else:
            seg_summary_parts.append(f"- {k}: {v}")
    seg_text = "\n".join(seg_summary_parts) if seg_summary_parts else "No structured findings available."

    # --- MODIFICATION DU PROMPT ---
    prompt = f"""You are a senior thoracic radiologist.

    You get three inputs: 
1. Validated automated CT findings (nodules, volumes).
2. The patient's clinical metadata.
3. The patient's previous radiology history.

=== CURRENT EXAM DATA ===
Patient ID: {patient_id}
Exam Date: {study_date}
Study Description: {description}
Accession Number: {acc_number}

=== AUTOMATED FINDINGS ===
{seg_text}

=== PATIENT HISTORY (Previous Reports) ===
{previous_history_text}

=== INSTRUCTIONS ===
Based on the current findings and history, write a structured radiology report:
1. **Clinical Indication**: Briefly mention context if available.
2. **Technique**: Standard CT protocol.
3. **Findings**: Describe the nodules/lesions found in the automated findings.
4. **Comparison**: Compare explicitly with the 'Patient History' provided above if dates/lesions match.
   - If a previous report mentions a nodule, check if the current findings show stability, progression, or regression (RECIST).
   - If no history matches, state "No prior comparison available".
5. **Impression**: Final conclusion and recommendations.

Rules:
- be concise.
- Comparison with history is CRITICAL.
- Write in English.
"""

    try:
        client = Mistral(api_key=MISTRAL_API_KEY)
        response = client.chat.complete(
            model=MISTRAL_MODEL,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You are a precise and factual medical report generator. "
                        "You only report the data given — never fabricate findings."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
            temperature=0.2,
        )
        return response.choices[0].message.content
    except Exception as exc:
        return f"⚠ Erreur lors de l'appel à Mistral : {exc}"


# ─────────────────────────────────────────────────────────────────────
# Step 7 : generate final HTML report
# ─────────────────────────────────────────────────────────────────────

def _generate_html_report(
    study_uid: str,
    study_info: dict,
    ct_dir: Path,
    seg_data: dict,
    llm_report: str,
):
    tags         = study_info.get("MainDicomTags", {})
    patient_tags = study_info.get("PatientMainDicomTags", {})

    patient_name = patient_tags.get("PatientName", "Inconnu").replace("^", " ").strip()
    patient_id   = patient_tags.get("PatientID",   "N/A")
    study_date   = _fmt_date(tags.get("StudyDate", ""))
    description  = tags.get("StudyDescription", "—")
    acc_number   = tags.get("AccessionNumber",  "—")
    modality     = tags.get("ModalitiesInStudy", tags.get("Modality", "—"))

    dcm_files = list(ct_dir.rglob("*.dcm"))
    n_files   = len(dcm_files)

    # ── Seg data HTML table ──────────────────────────────────────────
    seg_rows = ""
    for k, v in seg_data.items():
        if k.startswith("_"):
            continue
        if isinstance(v, dict):
            sub = "<br>".join(f"&nbsp;&nbsp;• {sk}: {sv}" for sk, sv in v.items())
            seg_rows += f"<tr><th>{_esc(k)}</th><td>{sub}</td></tr>\n"
        else:
            seg_rows += f"<tr><th>{_esc(k)}</th><td>{_esc(str(v))}</td></tr>\n"

    if not seg_rows:
        seg_rows = '<tr><td colspan="2" class="text-center">Aucune donnée de segmentation</td></tr>'

    # ── Convert LLM markdown-ish text to HTML paragraphs ─────────────
    llm_html = _markdown_to_html(llm_report)

    now = datetime.now().strftime("%d/%m/%Y %H:%M")

    html = f"""<!DOCTYPE html>
<html lang="fr">
<head>
  <meta charset="UTF-8"/>
  <title>Rapport — {study_uid}</title>
  <style>
    body{{font-family:'Segoe UI',sans-serif;padding:28px 36px;color:#1f2937;max-width:960px;margin:auto}}
    h2{{color:#1d4ed8;border-bottom:2px solid #dbeafe;padding-bottom:10px}}
    h3{{color:#1d4ed8;margin-top:28px;font-size:1.1rem}}
    table{{border-collapse:collapse;width:100%;margin-bottom:20px}}
    td,th{{border:1px solid #e5e7eb;padding:8px 12px;text-align:left;font-size:.9rem}}
    th{{background:#f3f4f6;font-weight:600;color:#374151;width:220px}}
    .section{{margin-top:22px}}
    .report-body{{background:#f8fafc;border:1px solid #e2e8f0;border-radius:8px;padding:20px 24px;margin-top:8px;line-height:1.8;font-size:.92rem}}
    .report-body h4{{color:#1e40af;margin:18px 0 6px;font-size:.95rem}}
    .report-body p{{margin:4px 0}}
    .report-body ul{{margin:4px 0 4px 18px}}
    .finding{{background:#f0fdf4;border-left:4px solid #22c55e;padding:10px 14px;border-radius:4px;margin-top:8px}}
    .warning{{background:#fff7e6;border-left:4px solid #f59e0b;padding:10px 14px;border-radius:4px;margin-top:8px}}
    .footer{{margin-top:32px;font-size:.78rem;color:#9ca3af;border-top:1px solid #e5e7eb;padding-top:12px}}
    .badge-ai{{display:inline-block;background:#dbeafe;color:#1d4ed8;font-size:.7rem;padding:2px 8px;border-radius:12px;font-weight:600;margin-left:8px;vertical-align:middle}}
  </style>
</head>
<body>

  <h2>Rapport Radiologique</h2>

  <!-- ── Patient info ────────────────────────────── -->
  <div class="section">
    <h3>Informations Patient</h3>
    <table>
      <tr><th>Nom</th><td>{_esc(patient_name)}</td></tr>
      <tr><th>ID Patient</th><td>{_esc(patient_id)}</td></tr>
    </table>
  </div>

  <!-- ── Study info ──────────────────────────────── -->
  <div class="section">
    <h3>Informations Examen</h3>
    <table>
      <tr><th>Date</th><td>{study_date}</td></tr>
      <tr><th>Description</th><td>{_esc(description)}</td></tr>
      <tr><th>Modalité</th><td>{_esc(modality)}</td></tr>
      <tr><th>N° Accession</th><td>{_esc(acc_number)}</td></tr>
      <tr><th>StudyInstanceUID</th><td><code style="font-size:.8rem">{study_uid}</code></td></tr>
      <tr><th>Fichiers DICOM</th><td>{n_files} fichier(s) extrait(s)</td></tr>
    </table>
  </div>

  <!-- ── Segmentation data ───────────────────────── -->
  <div class="section">
    <h3>Données de Segmentation <span class="badge-ai">extract_seg</span></h3>
    <table>
      {seg_rows}
    </table>
    
    <!-- ── Visualization Images ───────────────────── -->
    {_generate_images_html(seg_data)}
  </div>

  <!-- ── LLM Report ──────────────────────────────── -->
  <div class="section">
    <h3>Rapport Radiologique Généré <span class="badge-ai">Mistral AI</span></h3>
    <div class="report-body">
      {llm_html}
    </div>
  </div>

  <div class="footer">
    Rapport généré automatiquement le {now} par l'agent IA de radiologie (segmentation + Mistral LLM).<br>
    <em>Ce rapport doit être validé par un radiologue certifié avant tout usage clinique.</em>
  </div>

</body>
</html>"""

    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    (REPORTS_DIR / f"{study_uid}.html").write_text(html, encoding="utf-8")


# ─────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────

def _fmt_date(raw: str) -> str:
    if len(raw) == 8:
        return f"{raw[6:8]}/{raw[4:6]}/{raw[0:4]}"
    return raw or "—"


def _esc(text: str) -> str:
    """Basic HTML escaping."""
    return (
        text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
    )


def _markdown_to_html(text: str) -> str:
    """
    Lightweight markdown-ish → HTML conversion for LLM output.
    Handles headers (##, **bold**), bullet lists, and paragraphs.
    """
    import re
    lines = text.split("\n")
    html_parts = []
    in_list = False

    for line in lines:
        stripped = line.strip()

        # Close list if needed
        if in_list and not stripped.startswith(("-", "*", "•")):
            html_parts.append("</ul>")
            in_list = False

        if not stripped:
            html_parts.append("")
            continue

        # Headers: ## Title or **Title**
        hdr = re.match(r'^#{1,4}\s+(.+)', stripped)
        if hdr:
            html_parts.append(f'<h4>{_esc(hdr.group(1))}</h4>')
            continue

        bold_hdr = re.match(r'^\*\*(.+?)\*\*\s*$', stripped)
        if bold_hdr:
            html_parts.append(f'<h4>{_esc(bold_hdr.group(1))}</h4>')
            continue

        # Bullet list
        bullet = re.match(r'^[-*•]\s+(.+)', stripped)
        if bullet:
            if not in_list:
                html_parts.append("<ul>")
                in_list = True
            content = _inline_format(bullet.group(1))
            html_parts.append(f"  <li>{content}</li>")
            continue

        # Normal paragraph
        html_parts.append(f"<p>{_inline_format(stripped)}</p>")

    if in_list:
        html_parts.append("</ul>")

    return "\n".join(html_parts)


def _inline_format(text: str) -> str:
    """Handle **bold** and *italic* inline."""
    import re
    text = _esc(text)
    text = re.sub(r'\*\*(.+?)\*\*', r'<strong>\1</strong>', text)
    text = re.sub(r'\*(.+?)\*', r'<em>\1</em>', text)
    return text


def _generate_images_html(seg_data: dict) -> str:
    """Generate HTML for displaying segmentation images."""
    images_list = seg_data.get("_images", [])
    
    if not images_list:
        return '<p style="color:#9ca3af;font-style:italic;margin-top:10px;">Aucune image de visualisation générée.</p>'
    
    html = '<div style="margin-top:20px;"><h4 style="color:#1e40af;margin-bottom:10px;">Visualisations de la segmentation</h4>'
    html += '<div style="display:flex;flex-wrap:wrap;gap:15px;">'
    
    for img_name in images_list:
        img_url = f"/reports/{img_name}"
        html += f'''
        <div style="border:1px solid #e5e7eb;border-radius:8px;padding:8px;background:#f9fafb;">
            <a href="{img_url}" target="_blank">
                <img src="{img_url}" alt="Segmentation" style="max-width:400px;max-height:400px;display:block;border-radius:4px;">
            </a>
        </div>
        '''
    
    html += '</div></div>'
    return html
