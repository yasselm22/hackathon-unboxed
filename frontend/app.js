/**
 * Radiology Portal – Frontend Logic
 * Communicates with the FastAPI backend at /api/*
 */

const API = "";            // same origin as the backend
let allPatients = [];      // cached patient list
let selectedPatientId = null;

// ── Bootstrap modal instances ────────────────────────────────────────
const reportModalEl  = document.getElementById("reportModal");
const reportModal    = new bootstrap.Modal(reportModalEl);
const analyzeModalEl = document.getElementById("analyzeModal");
const analyzeModal   = new bootstrap.Modal(analyzeModalEl);

// ─────────────────────────────────────────────────────────────────
// Init
// ─────────────────────────────────────────────────────────────────
document.addEventListener("DOMContentLoaded", () => {
  loadPatients();
});

// ─────────────────────────────────────────────────────────────────
// Load patients from /api/patients
// ─────────────────────────────────────────────────────────────────
async function loadPatients() {
  const listEl  = document.getElementById("patient-list");
  const statusEl = document.getElementById("orthanc-status");

  try {
    const response = await fetch(`${API}/api/patients`);
    if (!response.ok) throw new Error(`HTTP ${response.status}`);

    allPatients = await response.json();

    statusEl.innerHTML =
      `<i class="bi bi-circle-fill text-success me-1"></i>Orthanc connecté — ${allPatients.length} patient(s)`;

    renderPatientList(allPatients);
  } catch (err) {
    statusEl.innerHTML =
      `<i class="bi bi-circle-fill text-danger me-1"></i>Orthanc inaccessible`;
    listEl.innerHTML = `
      <div class="alert alert-danger mx-2 mt-2 small">
        <i class="bi bi-exclamation-triangle-fill me-1"></i>
        Impossible de joindre le serveur Orthanc.<br>
        Vérifiez qu'il tourne sur <code>http://localhost:8042</code>.
      </div>`;
  }
}

// ─────────────────────────────────────────────────────────────────
// Render patient list
// ─────────────────────────────────────────────────────────────────
function renderPatientList(patients) {
  const listEl = document.getElementById("patient-list");

  if (patients.length === 0) {
    listEl.innerHTML =
      `<p class="text-center text-muted small py-4">Aucun patient trouvé.</p>`;
    return;
  }

  listEl.innerHTML = patients
    .map(
      (p) => `
        <div class="patient-item" id="pat-${p.orthanc_id}"
             onclick="selectPatient('${p.orthanc_id}')">
          <div class="patient-avatar-sm">
            <i class="bi bi-person-fill"></i>
          </div>
          <div>
            <div class="patient-name">${escapeHtml(p.patient_name || "Inconnu")}</div>
            <div class="patient-sub">
              ID: ${escapeHtml(p.patient_id)}
              ${p.birth_date ? "· " + formatDate(p.birth_date) : ""}
              · ${p.nb_studies} examen(s)
            </div>
          </div>
        </div>`
    )
    .join("");
}

// ─────────────────────────────────────────────────────────────────
// Filter patients by search input
// ─────────────────────────────────────────────────────────────────
function filterPatients() {
  const q = document.getElementById("search-input").value.toLowerCase();
  const filtered = allPatients.filter(
    (p) =>
      p.patient_name.toLowerCase().includes(q) ||
      p.patient_id.toLowerCase().includes(q)
  );
  renderPatientList(filtered);

  // Re-highlight selected patient if still visible
  if (selectedPatientId) {
    const el = document.getElementById(`pat-${selectedPatientId}`);
    if (el) el.classList.add("active");
  }
}

// ─────────────────────────────────────────────────────────────────
// Select a patient → load exams
// ─────────────────────────────────────────────────────────────────
async function selectPatient(orthancId) {
  // Update selected state
  document.querySelectorAll(".patient-item").forEach((el) =>
    el.classList.remove("active")
  );
  const el = document.getElementById(`pat-${orthancId}`);
  if (el) el.classList.add("active");

  selectedPatientId = orthancId;
  const patient = allPatients.find((p) => p.orthanc_id === orthancId);

  // Update patient header
  document.getElementById("patient-header").classList.remove("d-none");
  document.getElementById("header-name").textContent =
    patient?.patient_name || "Patient inconnu";
  document.getElementById("header-meta").textContent = [
    patient?.patient_id ? `ID : ${patient.patient_id}` : null,
    patient?.birth_date ? `Né(e) le ${formatDate(patient.birth_date)}` : null,
    patient?.sex ? sexLabel(patient.sex) : null,
  ]
    .filter(Boolean)
    .join("  ·  ");

  // Show exams panel, hide welcome
  document.getElementById("welcome-panel").classList.add("d-none");
  const examsPanel  = document.getElementById("exams-panel");
  const loadingEl   = document.getElementById("exams-loading");
  const examListEl  = document.getElementById("exam-list");

  examsPanel.classList.remove("d-none");
  loadingEl.classList.remove("d-none");
  examListEl.innerHTML = "";

  try {
    const res = await fetch(`${API}/api/exams/${orthancId}`);
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const exams = await res.json();
    loadingEl.classList.add("d-none");
    renderExamList(exams, patient);
  } catch (err) {
    loadingEl.classList.add("d-none");
    examListEl.innerHTML = `
      <div class="alert alert-warning small">
        <i class="bi bi-exclamation-triangle-fill me-1"></i>
        Impossible de charger les examens.
      </div>`;
  }
}

// ─────────────────────────────────────────────────────────────────
// Render exam timeline
// ─────────────────────────────────────────────────────────────────
function renderExamList(exams, patient) {
  const listEl = document.getElementById("exam-list");

  if (exams.length === 0) {
    listEl.innerHTML =
      `<p class="text-muted small text-center py-3">Aucun examen trouvé pour ce patient.</p>`;
    return;
  }

  listEl.innerHTML = exams
    .map((exam) => {
      const hasReport  = exam.has_report;
      const iconClass  = hasReport ? "has-report" : "no-report";
      const icon       = hasReport ? "bi-file-earmark-check-fill" : "bi-file-earmark-x";

      const modBadges = (exam.modalities || [])
        .map((m) => `<span class="badge-modality">${escapeHtml(m)}</span>`)
        .join("");

      const actionHtml = hasReport
        ? `<span class="report-badge badge bg-success-subtle text-success border border-success-subtle">
             <i class="bi bi-check-circle me-1"></i>Rapport disponible
           </span>`
        : `<button class="btn btn-sm btn-outline-primary py-1"
                   id="analyze-btn-${escapeHtml(exam.orthanc_id)}"
                   onclick="event.stopPropagation();
                            analyzeExam(
                              '${escapeHtml(exam.orthanc_id)}',
                              '${escapeHtml(exam.study_instance_uid)}',
                              '${escapeHtml(exam.study_description)}',
                              '${escapeHtml(exam.study_date)}'
                            )">
             <i class="bi bi-cpu me-1"></i>Analyser
           </button>`;

      const clickAttr = hasReport
        ? `onclick="openReport('${escapeHtml(exam.study_instance_uid)}', '${escapeHtml(exam.study_description)}', '${escapeHtml(exam.study_date)}')"`
        : "";

      return `
        <div class="exam-card ${!hasReport ? "no-report-clickable" : ""}" ${clickAttr}
             id="exam-card-${escapeHtml(exam.orthanc_id)}">
          <div class="exam-icon ${iconClass}">
            <i class="bi ${icon}"></i>
          </div>
          <div class="exam-info">
            <div class="exam-date">${formatDate(exam.study_date)}</div>
            <div class="exam-desc">${escapeHtml(exam.study_description || "Examen sans description")}</div>
            <div class="mt-1">${modBadges}</div>
          </div>
          <div>${actionHtml}</div>
        </div>`;
    })
    .join("");
}

// ─────────────────────────────────────────────────────────────────
// Analyze exam (launch pipeline)
// ─────────────────────────────────────────────────────────────────

// Step keyword → HTML element id mapping
const STEP_MAP = [
  { keyword: "Métadonnées",    id: "step-meta"     },
  { keyword: "Téléchargement", id: "step-download" },
  { keyword: "Extraction",     id: "step-extract"  },
  { keyword: "segmentation",   id: "step-seg"      },
  { keyword: "JSON",           id: "step-json"     },
  { keyword: "Mistral",        id: "step-llm"      },
  { keyword: "HTML final",     id: "step-report"   },
];

let _analyzePollingTimer = null;

async function analyzeExam(orthancStudyId, studyUid, description, date) {
  // ─ Reset modal UI ──────────────────────────────────────────────
  document.getElementById("analyze-spinner").classList.remove("d-none");
  document.getElementById("analyze-done-icon").classList.add("d-none");
  document.getElementById("analyze-error-icon").classList.add("d-none");
  document.getElementById("analyze-title").textContent = escapeHtml(description) || "Analyse…";
  document.getElementById("analyze-message").textContent = "Lancement du pipeline…";
  document.getElementById("analyze-close-btn").disabled = true;
  document.getElementById("analyze-view-btn").classList.add("d-none");
  STEP_MAP.forEach(({ id }) => {
    document.querySelector(`#${id} .step-badge`).innerHTML = "";
  });

  // Disable the analyse button to prevent double-click
  const analyzeBtn = document.getElementById(`analyze-btn-${orthancStudyId}`);
  if (analyzeBtn) {
    analyzeBtn.disabled = true;
    analyzeBtn.innerHTML = `<span class="spinner-border spinner-border-sm me-1"></span>Analyse…`;
  }

  analyzeModal.show();

  // ─ Start pipeline ───────────────────────────────────────────────
  let jobId;
  try {
    const res = await fetch(
      `${API}/api/analyze/${encodeURIComponent(orthancStudyId)}?study_uid=${encodeURIComponent(studyUid)}`,
      { method: "POST" }
    );
    if (!res.ok) throw new Error(`HTTP ${res.status}`);
    const data = await res.json();
    jobId = data.job_id;
  } catch (err) {
    _analyzeError(`Impossible de lancer l'analyse : ${err.message}`);
    return;
  }

  // ─ Poll status ─────────────────────────────────────────────────
  if (_analyzePollingTimer) clearInterval(_analyzePollingTimer);

  _analyzePollingTimer = setInterval(async () => {
    try {
      const res = await fetch(`${API}/api/analyze/status/${jobId}`);
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const job = await res.json();

      document.getElementById("analyze-message").textContent = job.message || "";
      _updateSteps(job.message || "");

      if (job.status === "done") {
        clearInterval(_analyzePollingTimer);
        _analyzeSuccess(studyUid, description, date, orthancStudyId);
      } else if (job.status === "error") {
        clearInterval(_analyzePollingTimer);
        _analyzeError(job.message);
      }
    } catch (err) {
      // Network hiccup — keep polling
    }
  }, 2000);
}

function _updateSteps(message) {
  const lower = message.toLowerCase();
  // Mark steps as done based on which keyword appears in the current message
  const order = ["métadonnées", "téléchargement", "extraction", "segmentation", "rapport"];
  let activeFound = false;
  STEP_MAP.forEach(({ keyword, id }, idx) => {
    const badge = document.querySelector(`#${id} .step-badge`);
    if (!badge) return;
    if (lower.includes(keyword.toLowerCase())) {
      // Current step — mark previous ones as done
      STEP_MAP.slice(0, idx).forEach(({ id: pid }) => {
        const pb = document.querySelector(`#${pid} .step-badge`);
        if (pb && !pb.innerHTML.includes("check")) {
          pb.innerHTML = `<i class="bi bi-check-circle-fill text-success"></i>`;
        }
      });
      badge.innerHTML = `<span class="spinner-border spinner-border-sm text-info" style="width:14px;height:14px"></span>`;
      activeFound = true;
    } else if (!activeFound) {
      badge.innerHTML = `<i class="bi bi-check-circle-fill text-success"></i>`;
    }
  });
}

function _analyzeSuccess(studyUid, description, date, orthancStudyId) {
  document.getElementById("analyze-spinner").classList.add("d-none");
  document.getElementById("analyze-done-icon").classList.remove("d-none");
  document.getElementById("analyze-title").textContent = "Analyse terminée !";
  document.getElementById("analyze-message").textContent = "Le rapport a été généré avec succès.";
  document.getElementById("analyze-close-btn").disabled = false;
  // Mark all steps done
  STEP_MAP.forEach(({ id }) => {
    const b = document.querySelector(`#${id} .step-badge`);
    if (b) b.innerHTML = `<i class="bi bi-check-circle-fill text-success"></i>`;
  });
  // Show "Voir le rapport" button
  const viewBtn = document.getElementById("analyze-view-btn");
  viewBtn.classList.remove("d-none");
  viewBtn.onclick = () => {
    analyzeModal.hide();
    openReport(studyUid, description, date);
  };
  // Update the exam card in the list
  _markExamCardDone(orthancStudyId, studyUid, description, date);
}

function _analyzeError(message) {
  document.getElementById("analyze-spinner").classList.add("d-none");
  document.getElementById("analyze-error-icon").classList.remove("d-none");
  document.getElementById("analyze-title").textContent = "Erreur";
  document.getElementById("analyze-message").textContent = message;
  document.getElementById("analyze-close-btn").disabled = false;
}

function _markExamCardDone(orthancStudyId, studyUid, description, date) {
  const card = document.getElementById(`exam-card-${orthancStudyId}`);
  if (!card) return;
  // Update icon
  card.querySelector(".exam-icon").className = "exam-icon has-report";
  card.querySelector(".exam-icon i").className = "bi bi-file-earmark-check-fill";
  // Remove no-report class, make card clickable
  card.classList.remove("no-report-clickable");
  card.setAttribute("onclick",
    `openReport('${escapeHtml(studyUid)}', '${escapeHtml(description)}', '${escapeHtml(date)}')`
  );
  // Replace Analyser button with green badge
  const btn = document.getElementById(`analyze-btn-${orthancStudyId}`);
  if (btn) {
    btn.outerHTML = `<span class="report-badge badge bg-success-subtle text-success border border-success-subtle">
      <i class="bi bi-check-circle me-1"></i>Rapport disponible
    </span>`;
  }
}

// ─────────────────────────────────────────────────────────────────
// Open report modal
// ─────────────────────────────────────────────────────────────────
async function openReport(studyUid, description, date) {
  document.getElementById("reportModalLabel").innerHTML =
    `<i class="bi bi-file-medical me-2"></i>${escapeHtml(description || "Rapport Radiologique")}`;

  document.getElementById("modal-meta").innerHTML =
    `<i class="bi bi-calendar3 me-1"></i>${formatDate(date)}
     &nbsp;·&nbsp;
     <i class="bi bi-fingerprint me-1"></i><code>${escapeHtml(studyUid)}</code>`;

  const contentEl = document.getElementById("report-content");
  const loadingEl = document.getElementById("report-loading");

  contentEl.innerHTML = "";
  loadingEl.classList.remove("d-none");

  // Set print/open link
  document.getElementById("report-print-btn").href =
    `${API}/api/report/${encodeURIComponent(studyUid)}`;

  reportModal.show();

  try {
    const res = await fetch(`${API}/api/report/${encodeURIComponent(studyUid)}`);
    loadingEl.classList.add("d-none");

    if (!res.ok) throw new Error(`HTTP ${res.status}`);

    const contentType = res.headers.get("content-type") || "";

    if (contentType.includes("text/html")) {
      // Render HTML in a sandboxed iframe
      const html = await res.text();
      const blob = new Blob([html], { type: "text/html" });
      const url  = URL.createObjectURL(blob);
      contentEl.innerHTML = `<iframe src="${url}" onload="URL.revokeObjectURL('${url}')"></iframe>`;
    } else {
      // Plain text / markdown
      const text = await res.text();
      contentEl.innerHTML = `<pre class="report-pre">${escapeHtml(text)}</pre>`;
    }
  } catch (err) {
    loadingEl.classList.add("d-none");
    contentEl.innerHTML = `
      <div class="alert alert-danger">
        <i class="bi bi-exclamation-triangle-fill me-1"></i>
        Erreur lors du chargement du rapport.
      </div>`;
  }
}

// ─────────────────────────────────────────────────────────────────
// Helpers
// ─────────────────────────────────────────────────────────────────
function formatDate(raw) {
  if (!raw || raw.length < 8) return raw || "Date inconnue";
  // YYYYMMDD → DD/MM/YYYY
  return `${raw.slice(6, 8)}/${raw.slice(4, 6)}/${raw.slice(0, 4)}`;
}

function sexLabel(sex) {
  const map = { M: "Homme", F: "Femme", O: "Autre" };
  return map[sex?.toUpperCase()] || sex;
}

function escapeHtml(str) {
  if (!str) return "";
  return String(str)
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;")
    .replace(/'/g, "&#039;");
}
