const API_TEXT_STREAM = "/api/v1/evaluations/stream";
const API_UPLOAD_STREAM = "/api/v1/evaluations/upload/stream";
const API_JOB_FETCH = "/api/v1/jobs/fetch";
const API_EVALUATIONS = "/api/v1/evaluations";
const MIN_LENGTH = 20;

// Canonical stage name -> label shown in the progress list (order matters).
const STAGES = [
  ["resume_parse", "Reading resume file"],
  ["profile_extraction", "Analyzing resume"],
  ["requirements_extraction", "Extracting requirements"],
  ["deterministic_matching", "Matching skills"],
  ["recommendation", "Applying recommendation rules"],
  ["plan_and_explanation", "Preparing recommendation"],
  ["persistence", "Saving evaluation"],
];

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

// Confirmation state: each input must be explicitly confirmed before it can
// be used by Analyze / Rank jobs. Editing an input invalidates its snapshot.
const confirmed = { resume: null, job: null, batch: null };

const CONFIRM = {
  resume: { btn: el("confirm-resume"), note: el("resume-confirmed"), label: "Confirm resume" },
  job: { btn: el("confirm-job"), note: el("job-confirmed"), label: "Confirm job" },
  batch: { btn: el("confirm-batch"), note: el("batch-confirmed"), label: "Confirm batch" },
};

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
  invalidateConfirm("resume");
}

tabPaste.addEventListener("click", () => switchTab(false));
tabUpload.addEventListener("click", () => switchTab(true));

resumeFile.addEventListener("change", () => {
  fileName.textContent = resumeFile.files.length
    ? `Selected: ${resumeFile.files[0].name}`
    : "No file selected";
  invalidateConfirm("resume");
});

el("load-example").addEventListener("click", () => {
  switchTab(false);
  resumeText.value = EXAMPLE_RESUME;
  jobDescription.value = EXAMPLE_JOB;
  confirmResume();
  confirmJob();
});

async function loadJobFromUrl(url) {
  jobSource.hidden = true;
  jobSource.textContent = "Loading job…";
  jobSource.hidden = false;
  let ok = false;
  try {
    const response = await fetch(API_JOB_FETCH, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ url }),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      showError(formatApiError(data, response.status));
      return false;
    }

    ok = true;
    const parts = [data.title, data.company].filter(Boolean);
    jobDescription.value = [...parts, data.description].filter(Boolean).join("\n\n");
    invalidateConfirm("job");

    jobSource.textContent = "";
    const link = document.createElement("a");
    link.href = data.source_url || url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    link.textContent = `Loaded: ${data.title || "Untitled job"}${data.company ? " · " + data.company : ""}`;
    jobSource.appendChild(link);
  } catch {
    showError("Could not reach the CareerAgent server. Is it still running?");
    return false;
  } finally {
    jobSource.hidden = !(ok && jobDescription.value);
    return ok && jobDescription.value.length > 0;
  }
}

loadJobBtn.addEventListener("click", async () => {
  const url = jobUrl.value.trim();
  if (!/^https?:\/\/.+/.test(url)) {
    showError("Enter a full job URL, e.g. https://company.com/jobs/123 (http or https).");
    return;
  }

  loadJobBtn.disabled = true;
  errorBox.hidden = true;
  result.hidden = true;
  try {
    await loadJobFromUrl(url);
  } finally {
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
  analyzeBtn.classList.add("running");
  updateStatusText("Starting…");
  resetStages();
  initStageLines();
  timer = setInterval(() => {
    updateStatusText(`Working… ${Math.round((Date.now() - started) / 1000)}s`);
  }, 1000);
}

function updateStatusText(text) {
  statusText.textContent = text;
}

function resetStages() {
  const list = el("stage-list");
  clearNode(list);
  currentStageNode = null;
}

let currentStageNode = null;

function initStageLines() {
  const list = el("stage-list");
  STAGES.forEach(([stage, label]) => {
    const li = document.createElement("li");
    li.className = "stage pending";
    li.dataset.stage = stage;
    const dot = document.createElement("span");
    dot.className = "dot";
    const text = document.createElement("span");
    text.textContent = label;
    li.append(dot, text);
    list.appendChild(li);
  });
}

function setStage(stage) {
  const list = el("stage-list");
  let li = list.querySelector(`[data-stage="${stage}"]`);
  if (!li) {
    const entry = STAGES.find(([name]) => name === stage);
    li = document.createElement("li");
    li.className = "stage pending";
    li.dataset.stage = stage;
    const dot = document.createElement("span");
    dot.className = "dot";
    const text = document.createElement("span");
    text.textContent = entry ? entry[1] : stage;
    li.append(dot, text);
    list.appendChild(li);
  }
  if (currentStageNode && currentStageNode !== li) {
    currentStageNode.classList.remove("active");
    currentStageNode.classList.add("done");
  }
  li.classList.remove("pending", "done");
  li.classList.add("active");
  currentStageNode = li;
  const label = li.querySelector("span:last-child");
  updateStatusText(label ? label.textContent + "…" : "Working…");
}

function stopStatus() {
  clearInterval(timer);
  timer = null;
  analyzeBtn.classList.remove("running");
  const list = el("stage-list");
  if (currentStageNode) {
    currentStageNode.classList.remove("active");
    currentStageNode.classList.add("done");
  }
}

function resumeSummary(entry) {
  if (entry.mode === "upload") return entry.name;
  const first = (entry.text.split("\n") || []).find((line) => line.trim());
  return first ? `"${first.trim().slice(0, 60)}"` : `${entry.text.length} characters`;
}

function markConfirmed(key, note) {
  const entry = CONFIRM[key];
  entry.btn.textContent = "Confirmed";
  entry.btn.classList.add("confirmed");
  entry.note.textContent = `✓ ${note}`;
  entry.note.hidden = false;
  updateActions();
}

function invalidateConfirm(key) {
  confirmed[key] = null;
  const entry = CONFIRM[key];
  entry.btn.textContent = entry.label;
  entry.btn.classList.remove("confirmed");
  entry.note.hidden = true;
  updateActions();
}

function confirmResume() {
  if (uploadMode) {
    if (!resumeFile.files.length) {
      showError("Choose a resume file, or switch to “Paste text”, then confirm.");
      return false;
    }
    confirmed.resume = { mode: "upload", file: resumeFile.files[0], name: resumeFile.files[0].name };
  } else {
    const text = resumeText.value.trim();
    if (text.length < MIN_LENGTH) {
      showError("Your resume looks too short — paste at least a few lines (20+ characters), then confirm.");
      return false;
    }
    confirmed.resume = { mode: "paste", text };
  }
  markConfirmed("resume", `Resume confirmed: ${resumeSummary(confirmed.resume)}`);
  return true;
}

function confirmJob() {
  const text = jobDescription.value.trim();
  if (text.length < MIN_LENGTH) {
    showError("Paste the job description first (20+ characters), then confirm.");
    return false;
  }
  confirmed.job = text;
  const first = (text.split("\n") || []).find((line) => line.trim());
  markConfirmed("job", first ? `Job confirmed: "${first.trim().slice(0, 60)}"` : "Job description confirmed");
  return true;
}

function confirmBatch() {
  const urls = jobUrlsMulti.value
    .split("\n")
    .map((line) => line.trim())
    .filter(Boolean)
    .slice(0, 10);
  if (!urls.length) {
    showError("Paste at least one job URL (one per line), then confirm.");
    return false;
  }
  confirmed.batch = urls;
  markConfirmed("batch", `${urls.length} job URL${urls.length === 1 ? "" : "s"} confirmed`);
  return true;
}

function updateActions() {
  const resumeOk = Boolean(confirmed.resume);
  const jobOk = Boolean(confirmed.job);
  const batchOk = Boolean(confirmed.resume && confirmed.resume.mode === "paste" && confirmed.batch);
  analyzeBtn.disabled = !(resumeOk && jobOk);
  rankJobsBtn.disabled = !batchOk;
  const hint = el("analyze-hint");
  if (resumeOk && jobOk) {
    hint.textContent = "Takes ~20–60 seconds. You can watch each step as the agent works.";
  } else if (!resumeOk) {
    hint.textContent = "Confirm your resume first, then confirm the job description to enable Analyze.";
  } else {
    hint.textContent = "Confirm the job description to enable Analyze.";
  }
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

async function consumeStream(response) {
  const decoder = new TextDecoder();
  const reader = response.body.getReader();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let separator;
    while ((separator = buffer.indexOf("\n\n")) !== -1) {
      const raw = buffer.slice(0, separator);
      buffer = buffer.slice(separator + 2);
      const parsed = parseEvent(raw);
      if (!parsed) continue;
      if (parsed.type === "stage") {
        setStage(JSON.parse(parsed.data));
      } else if (parsed.type === "result") {
        renderResult(JSON.parse(parsed.data));
        return { ok: true };
      } else if (parsed.type === "error") {
        const payload = JSON.parse(parsed.data);
        showError(formatApiError(payload, payload.status_code));
        return { ok: false };
      }
    }
  }
  showError("The analysis ended without a result. Please try again.");
  return { ok: false };
}

function parseEvent(raw) {
  let type = null;
  let data = null;
  for (const line of raw.split("\n")) {
    if (line.startsWith("event:")) type = line.slice(6).trim();
    else if (line.startsWith("data:")) data = line.slice(5).trim();
  }
  if (type && data !== null) return { type, data };
  return null;
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

function historyRow(item) {
  const row = document.createElement("li");
  row.className = "history-row";
  const main = document.createElement("div");
  main.className = "history-main";
  const title = document.createElement("span");
  title.className = "history-title";
  title.textContent = item.job_title || `Evaluation #${item.id}`;
  const when = document.createElement("span");
  when.className = "history-when";
  when.textContent = item.created_at ? timeAgo(item.created_at) : "";
  main.append(title, when);
  const score = document.createElement("span");
  score.className = "history-score";
  score.textContent = `${item.score}%`;
  score.style.color = scoreColor(item.score);
  const badge = document.createElement("span");
  badge.className = `badge ${item.recommendation}`;
  badge.textContent = item.recommendation;
  row.append(main, score, badge);
  row.addEventListener("click", () => openHistory(item));
  return row;
}

function timeAgo(iso) {
  const seconds = Math.round((Date.now() - new Date(iso).getTime()) / 1000);
  if (seconds < 60) return "just now";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `${minutes}m ago`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `${hours}h ago`;
  return `${Math.round(hours / 24)}d ago`;
}

async function loadHistory() {
  const list = el("history-list");
  const empty = el("history-empty");
  const error = el("history-error");
  try {
    const response = await fetch(`${API_EVALUATIONS}?limit=10`);
    if (!response.ok) throw new Error(`history request failed: ${response.status}`);
    const items = await response.json();
    clearNode(list);
    empty.hidden = items.length !== 0;
    error.hidden = true;
    items.forEach((item) => list.appendChild(historyRow(item)));
  } catch {
    empty.hidden = true;
    error.hidden = false;
  }
}

async function openHistory(item) {
  try {
    const response = await fetch(`${API_EVALUATIONS}/${item.id}`);
    if (!response.ok) throw new Error(`history fetch failed: ${response.status}`);
    const data = await response.json();
    errorBox.hidden = true;
    renderResult(data);
    await loadHistory();
  } catch {
    showError("Could not load that evaluation from the history.");
  }
}

analyzeBtn.addEventListener("click", async () => {
  if (!confirmed.resume) {
    showError("Confirm your resume first (paste text or choose a file), then analyze.");
    return;
  }
  if (!confirmed.job) {
    showError("Confirm the job description first, then analyze.");
    return;
  }

  analyzeBtn.disabled = true;
  errorBox.hidden = true;
  result.hidden = true;
  startStatus();

  try {
    let response;
    if (confirmed.resume.mode === "upload") {
      const form = new FormData();
      form.append("resume", confirmed.resume.file);
      form.append("job_description", confirmed.job);
      response = await fetch(API_UPLOAD_STREAM, { method: "POST", body: form });
    } else {
      response = await fetch(API_TEXT_STREAM, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          resume_text: confirmed.resume.text,
          job_description: confirmed.job,
        }),
      });
    }
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      showError(formatApiError(data, response.status));
      return;
    }
    const outcome = await consumeStream(response);
    if (outcome.ok) await loadHistory();
  } catch {
    showError("Could not reach the CareerAgent server. Is it still running?");
  } finally {
    stopStatus();
    statusBox.hidden = true;
    updateActions();
  }
});

loadHistory();

const API_BATCH_RANK = "/api/v1/batch/quick-ranking";
const jobUrlsMulti = el("job-urls-multi");
const rankJobsBtn = el("rank-jobs");
const batchResult = el("batch-result");
const batchNote = el("batch-note");
const batchError = el("batch-error");

function batchRow(item, index) {
  const li = document.createElement("li");
  li.className = "batch-row";

  const verdict = document.createElement("span");
  verdict.className = `badge ${item.recommendation.toLowerCase()}`;
  verdict.textContent = item.recommendation;

  const title = document.createElement("div");
  title.className = "batch-title";
  title.textContent = `${index}. ${item.title || "Untitled job"}`;
  if (item.company) title.textContent += ` · ${item.company}`;

  const meta = document.createElement("span");
  meta.className = "batch-meta";
  if (item.error) {
    meta.textContent = `Error: ${item.error}`;
  } else {
    const total = (item.matched_skills || []).length + (item.missing_skills || []).length;
    meta.textContent = total
      ? `${(item.matched_skills || []).length} of ${total} of your skills are mentioned`
      : "No skills to compare";
  }

  const score = document.createElement("span");
  score.className = "batch-score";
  score.textContent = item.error ? "—" : `${item.score}%`;

  li.append(verdict, title, meta, score);

  if (!item.error) {
    li.classList.add("clickable");
    li.title = "Analyze this job in depth";
    li.addEventListener("click", async () => {
      jobUrl.value = item.url;
      result.hidden = true;
      jobDescription.value = "";
      const loaded = await loadJobFromUrl(item.url);
      if (loaded && confirmJob()) analyzeBtn.click();
    });
  }
  return li;
}

rankJobsBtn.addEventListener("click", async () => {
  batchError.hidden = true;

  if (!confirmed.resume || confirmed.resume.mode !== "paste") {
    batchError.textContent = "Confirm your resume in the 'Paste text' tab before ranking jobs.";
    batchError.hidden = false;
    return;
  }
  if (!confirmed.batch) {
    batchError.textContent = "Confirm the job URLs first, then rank.";
    batchError.hidden = false;
    return;
  }

  rankJobsBtn.disabled = true;
  batchResult.hidden = true;
  batchNote.hidden = false;
  batchNote.textContent = "Ranking… one quick model call, a few seconds.";
  try {
    const response = await fetch(API_BATCH_RANK, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ resume_text: confirmed.resume.text, job_urls: confirmed.batch }),
    });
    const data = await response.json().catch(() => null);
    if (!response.ok) {
      showError(formatApiError(data, response.status));
      batchNote.hidden = true;
      return;
    }
    batchNote.textContent = data.note || "";
    batchResult.hidden = false;
    batchResult.innerHTML = "";
    data.jobs.forEach((item, index) => batchResult.appendChild(batchRow(item, index + 1)));
  } catch {
    batchNote.hidden = true;
    batchError.textContent = "Could not reach the CareerAgent server. Is it still running?";
    batchError.hidden = false;
  } finally {
    updateActions();
  }
});

resumeText.addEventListener("input", () => invalidateConfirm("resume"));
jobDescription.addEventListener("input", () => invalidateConfirm("job"));
jobUrlsMulti.addEventListener("input", () => invalidateConfirm("batch"));

CONFIRM.resume.btn.addEventListener("click", confirmResume);
CONFIRM.job.btn.addEventListener("click", confirmJob);
CONFIRM.batch.btn.addEventListener("click", confirmBatch);

updateActions();
