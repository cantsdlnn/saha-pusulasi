let dashboard = null;
let suggestions = [];
const jobs = document.querySelector("#jobs");
const suggestionBox = document.querySelector("#suggestions");
const technicianBox = document.querySelector("#technicians");
const auditBox = document.querySelector("#audit");
const statusBox = document.querySelector("#status");
function esc(value) {
  return String(value).replace(
    /[&<>'"]/g,
    (character) =>
      ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", "'": "&#39;", '"': "&quot;" })[
        character
      ] || character,
  );
}
function urgency(value) {
  return { high: "YÜKSEK", medium: "ORTA", low: "DÜŞÜK" }[value] || value;
}
function minutes(value) {
  return `${Math.floor(value / 60)}s ${value % 60}dk`;
}
async function load() {
  const response = await fetch("/api/dashboard");
  dashboard = await response.json();
  render();
}
function render() {
  const open = dashboard.jobs.filter((job) => job.status === "open");
  const overdue = open.filter(
    (job) => new Date(job.sla_due) < new Date(dashboard.generated_at),
  );
  document.querySelector("#metrics").innerHTML =
    `<article><span>AÇIK İŞ</span><b>${open.length}</b></article><article><span>SLA GECİKEN</span><b>${overdue.length}</b></article><article><span>AKTİF TEKNİSYEN</span><b>${dashboard.technicians.length}</b></article><article><span>ONAYLI ATAMA</span><b>${dashboard.jobs.filter((job) => job.status === "assigned").length}</b></article>`;
  jobs.innerHTML = dashboard.jobs
    .map(
      (job) =>
        `<article class="job ${job.status}"><div class="score"><b>${job.priority.score}</b><span>PUAN</span></div><div><span class="urgency ${job.urgency}">${urgency(job.urgency)}</span><h3>${esc(job.title)}</h3><p>${esc(job.customer)} · ${esc(job.required_skill)} · ${job.duration_minutes} dk</p><small>${job.priority.reasons.map(esc).join(" · ")}</small></div><div class="state"><b>${job.status === "open" ? "AÇIK" : "ATANDI"}</b><time>${new Date(job.sla_due).toLocaleString("tr-TR", { dateStyle: "short", timeStyle: "short" })}</time><span>v${job.version}</span></div></article>`,
    )
    .join("");
  suggestionBox.innerHTML = suggestions.length
    ? suggestions
        .map((item) => {
          const job = dashboard.jobs.find(
            (candidate) => candidate.id === item.job_id,
          );
          return `<article class="suggestion"><strong>${esc(job?.title || item.job_id)}</strong><span>→ ${esc(item.technician_name)} · ${item.distance_km} km</span><p>${item.reasons.map(esc).join(" · ")}</p><button data-job="${item.job_id}" data-tech="${item.technician_id}" data-version="${job?.version}">Atamayı onayla</button></article>`;
        })
        .join("")
    : '<div class="empty">“Plan üret” ile önerileri hesaplayın.</div>';
  technicianBox.innerHTML = dashboard.technicians
    .map(
      (tech) =>
        `<article><div><strong>${esc(tech.name)}</strong><span>${tech.skills.map(esc).join(" · ")}</span></div><div><b>${minutes(tech.capacity_minutes - tech.committed_minutes)}</b><small>kalan</small></div></article>`,
    )
    .join("");
  auditBox.innerHTML = dashboard.audit.length
    ? dashboard.audit
        .map(
          (event) =>
            `<article><b>#${event.id} · İş ${event.job_id}</b><span>${esc(event.actor)} · ${new Date(event.created_at).toLocaleString("tr-TR")}</span><code>${event.action === "assigned" ? "atama onaylandı" : esc(event.action)}</code></article>`,
        )
        .join("")
    : '<div class="empty">Henüz onaylanmış atama yok.</div>';
  document
    .querySelectorAll("[data-job]")
    .forEach((button) =>
      button.addEventListener("click", () => assign(button)),
    );
}
document.querySelector("#plan").addEventListener("click", async () => {
  statusBox.textContent = "SLA, beceri, kapasite ve mesafe hesaplanıyor…";
  const response = await fetch("/api/plan", { method: "POST" });
  const data = await response.json();
  suggestions = data.suggestions;
  statusBox.textContent = `${suggestions.length} açıklanabilir öneri üretildi; henüz hiçbir atama yapılmadı.`;
  render();
});
async function assign(button) {
  button.disabled = true;
  statusBox.textContent = "Atama sürümü doğrulanıyor…";
  const response = await fetch(`/api/jobs/${button.dataset.job}/assign`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      technician_id: Number(button.dataset.tech),
      expected_version: Number(button.dataset.version),
      actor: "demo planlayıcı",
    }),
  });
  if (!response.ok) {
    const data = await response.json();
    statusBox.textContent = data.detail || "Atama yapılamadı.";
    button.disabled = false;
    return;
  }
  dashboard = await response.json();
  suggestions = suggestions.filter(
    (item) => String(item.job_id) !== button.dataset.job,
  );
  statusBox.textContent = "Atama onaylandı ve denetim izine yazıldı.";
  render();
}
load().catch(() => {
  statusBox.textContent = "Veriler yüklenemedi.";
});
