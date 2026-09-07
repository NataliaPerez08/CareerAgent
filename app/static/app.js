const API_TEXT = "/api/v1/evaluations";
const API_UPLOAD = "/api/v1/evaluations/upload";
const API_JOB_FETCH = "/api/v1/jobs/fetch";
const MIN_LENGTH = 20;

const EXAMPLE_RESUME = `Junior Backend Developer

Backend developer with 2 years of professional backend development
experience building internal services and automation tools.

Skills and evidence:
- Python for backend services, scripting, and automation.
- REST API design and integration for internal tooling.
- PostgreSQL for relational persistence and reporting queries.
- Docker for local development and deployment packaging.
- Git for version control and code review workflows.

Experience:
- Built and maintained internal REST services for the operations team.
- Wrote PostgreSQL reporting queries used by two other teams.
- Packaged every service with Docker for one-command local setup.`;

const EXAMPLE_JOB = `Junior Backend Engineer

We build logistics software for small retailers. You will join the
backend team that owns order processing and inventory services.

Requirements:
- 2+ years of backend development experience.
- Python.
- REST API development.
- PostgreSQL.
- Docker.
- AWS.

Preferred:
- Kubernetes.
- CI/CD.`;

const el = (id) => document.getElementById(id);

const tabPaste = el("tab-paste");
const tabUpload = el("tab-upload");
const panelPaste = el("panel-paste");
const panelUpload = el("panel-upload");
const resumeText = el("resume-text");
const resumeFile = el("resume-file");
const fileName = el("file-name");
const jobDescription = el("job-description");
const jobUrl = el("job-url");
const loadJobBtn = el("load-job");
const jobSource = el("job-source");
const analyzeBtn = el("analyze");
const statusBox = el("status");
const statusText = el("status-text");
const errorBox = el("error");
const result = el("result");

let uploadMode = false;
let timer = null;

function switchTab(upload) {
  uploadMode = upload;
  tabPaste.classList.toggle("active", !upload);
  tabUpload.classList.toggle("active", upload);
  tabPaste.setAttribute("aria-selected", String(!upload));
  tabUpload.setAttribute("aria-selected", String(upload));
  panelPaste.hidden = upload;
  panelUpload.hidden = !upload;
}

tabPaste.addEventListener("click", () => switchTab(false));
tabUpload.addEventListener("click", () => switchTab(true));

resumeFile.addEventListener("change", () => {
  fileName.textContent = resumeFile.files.length
    ? `Selected: ${resumeFile.files[0].name}`
    : "No file selected";
});

el("load-example").addEventListener("click", () => {
  switchTab(false);
  resumeText.value = EXAMPLE_RESUME;
  jobDescription.value = EXAMPLE_JOB;
});

loadJobBtn.addEventListener("click", async () => {
  const url = jobUrl.value.trim();
  if (!/^https?:\/\/.+/.test(url)) {
    showError("Enter a full job URL, e.g. https://company.com/jobs/123 (http or https).");
    return;
  }

  loadJobBtn.disabled = true;
  errorBox.hidden = true;
  result.hidden = true;
  jobSource.hidden = true;
  jobSource.textContent = "Loading job…";
  jobSource.hidden = false;
  let loaded = false;

  try {
    const response = await fetch(API_JOB_FETCH, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      showError(formatApiError(data, response.status));
      return;
    }

    loaded = true;
    const parts = [data.title, data.company].filter(Boolean);
    jobDescription.value = [...parts, data.description].filter(Boolean).join("\n\n");

    jobSource.textContent = "";
    const link = document.createElement("a");
    link.href = data.source_url || url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = `Loaded: ${data.title || "Untitled job"}${data.company ? " · " + data.company : ""}`;
    jobSource.appendChild(link);
  } catch {
    showError("Could not reach the CareerAgent server. Is it still running?");
  } finally {
    jobSource.hidden = !loaded;
    loadJobBtn.disabled = false;
  }
});

function showError(message) {
  result.hidden = true;
  errorBox.textContent = message;
  errorBox.hidden = false;
}

function startStatus() {
  const started = Date.now();
  statusBox.hidden = false;
  statusText.textContent = "Analyzing…";
  timer = setInterval(() => {
    statusText.textContent = `Analyzing… ${Math.round((Date.now() - started) / 1000)}s`;
  }, 1000);
}

function stopStatus() {
  clearInterval(timer);
  timer = null;
  statusBox.hidden = true;
}

function clientError() {
  if (uploadMode) {
    if (!resumeFile.files.length) {
      return "Choose a resume file, or switch to “Paste text”.";
    }
  } else if (resumeText.value.trim().length < MIN_LENGTH) {
    return "Your resume looks too short — paste at least a few lines (20+ characters).";
  }
  if (jobDescription.value.trim().length < MIN_LENGTH) {
    return "Paste the job description first (20+ characters).";
  }
  return null;
}

function formatApiError(payload, statusCode) {
  if (payload && Array.isArray(payload.detail)) {
    return payload.detail
      .map((item) => {
        const field = (item.loc || []).filter((part) => part !== "body").join(" → ");
        return field ? `${field}: ${item.msg}` : item.msg;
      })
      .join("\n");
  }
  if (payload && typeof payload.detail === "string") {
    return payload.detail;
  }
  return `Request failed (HTTP ${statusCode}).`;
}

async function callApi() {
  if (uploadMode) {
    const form = new FormData();
    form.append("resume", resumeFile.files[0]);
    form.append("job_description", jobDescription.value);
    const response = await fetch(API_UPLOAD, { method: "POST", body: form });
    return { response, data: await response.json().catch(() => null) };
  }
  const response = await fetch(API_TEXT, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      resume_text: resumeText.value,
      job_description: jobDescription.value,
    }),
  });
  return { response, data: await response.json().catch(() => null) };
}

function chip(parent, text) {
  const node = document.createElement("span");
  node.className = "chip";
  node.textContent = text;
  parent.appendChild(node);
}

function clearNode(node) {
  while (node.firstChild) node.removeChild(node.firstChild);
}

function renderMissing(data) {
  const container = el("missing");
  clearNode(container);
  const groups = [
    ["critical", "Critical", data.missing_critical_skills],
    ["required", "Required", data.missing_required_skills],
    ["preferred", "Preferred (nice to have)", data.missing_preferred_skills],
  ];
  let any = false;
  for (const [severity, label, skills] of groups) {
    if (!skills || !skills.length) continue;
    any = true;
    const group = document.createElement("div");
    group.className = `missing-group ${severity}`;
    const groupLabel = document.createElement("div");
    groupLabel.className = "label";
    groupLabel.textContent = label;
    const chips = document.createElement("div");
    chips.className = "chips";
    skills.forEach((skill) => chip(chips, skill));
    group.append(groupLabel, chips);
    container.appendChild(group);
  }
  if (!any) {
    const none = document.createElement("div");
    none.className = "label";
    none.textContent = "None — every listed skill matched.";
    container.appendChild(none);
  }
}

function renderGaps(data) {
  const container = el("gaps");
  clearNode(container);
  (data.skill_gaps || []).forEach((gap) => {
    const node = document.createElement("div");
    node.className = "gap";
    const head = document.createElement("div");
    head.className = "gap-head";
    const skill = document.createElement("span");
    skill.textContent = gap.skill;
    const severity = document.createElement("span");
    severity.className = `severity ${gap.severity}`;
    severity.textContent = gap.severity;
    head.append(skill, severity);
    node.appendChild(head);
    if (gap.preparation_steps && gap.preparation_steps.length) {
      const steps = document.createElement("ol");
      gap.preparation_steps.forEach((step) => {
        const li = document.createElement("li");
        li.textContent = step;
        steps.appendChild(li);
      });
      node.appendChild(steps);
    }
    container.appendChild(node);
  });
}

function renderList(nodeId, values) {
  const node = el(nodeId);
  clearNode(node);
  (values || []).forEach((value) => {
    const li = document.createElement("li");
    li.textContent = value;
    node.appendChild(li);
  });
}

function scoreColor(score) {
  if (score >= 70) return "var(--good)";
  if (score >= 45) return "var(--warn)";
  return "var(--bad)";
}

function renderResult(data) {
  const badge = el("recommendation");
  badge.textContent = data.recommendation;
  badge.className = `badge ${data.recommendation}`;

  el("score-value").textContent = data.score;
  const ring = el("score-ring");
  ring.style.setProperty("--score", data.score);
  ring.style.setProperty("--score-color", scoreColor(data.score));

  const experience = el("experience");
  if (data.experience_match === true) {
    experience.textContent = "✓ Experience requirement met";
    experience.className = "experience ok";
  } else if (data.experience_match === false) {
    experience.textContent = "✗ Experience requirement not met";
    experience.className = "experience no";
  } else {
    experience.textContent = "Experience requirement: unknown (not stated)";
    experience.className = "experience";
  }

  const matched = el("matched");
  clearNode(matched);
  (data.matched_skills || []).forEach((skill) => chip(matched, skill));

  const preferredWrap = el("matched-preferred-wrap");
  const preferred = el("matched-preferred");
  clearNode(preferred);
  if (data.matched_preferred_skills && data.matched_preferred_skills.length) {
    data.matched_preferred_skills.forEach((skill) => chip(preferred, skill));
    preferredWrap.hidden = false;
  } else {
    preferredWrap.hidden = true;
  }

  const saved = el("saved");
  if (data.id != null) {
    saved.textContent = "";
    const link = document.createElement("a");
    link.href = `/api/v1/evaluations/${data.id}`;
    link.textContent = `Saved — evaluation #${data.id}`;
    saved.appendChild(link);
    saved.hidden = false;
  } else {
    saved.hidden = true;
  }

  renderMissing(data);
  renderList("evidence", data.evidence);
  renderGaps(data);
  renderList("topics", data.interview_topics);
  renderList("plan", data.preparation_plan);
  el("reasoning").textContent = data.reasoning || "";

  errorBox.hidden = true;
  result.hidden = false;
  result.scrollIntoView({ behavior: "smooth", block: "start" });
}

analyzeBtn.addEventListener("click", async () => {
  const problem = clientError();
  if (problem) {
    showError(problem);
    return;
  }

  analyzeBtn.disabled = true;
  errorBox.hidden = true;
  result.hidden = true;
  startStatus();

  try {
    const { response, data } = await callApi();
    if (!response.ok) {
      showError(formatApiError(data, response.status));
    } else {
      renderResult(data);
    }
  } catch {
    showError("Could not reach the CareerAgent server. Is it still running?");
  } finally {
    stopStatus();
    analyzeBtn.disabled = false;
  }
});
