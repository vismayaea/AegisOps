const state = {
  incident: null,
  selectedScenario: "api_latency_spike",
};

const lifecycleLabels = [
  ["incident_detected", "Incident detected"],
  ["evidence_collected", "Evidence collected"],
  ["investigation_performed", "Logs analyzed"],
  ["rca_produced", "Metrics correlated and root cause identified"],
  ["risk_evaluated", "Risk assessed"],
  ["remediation_selected", "Remediation planned"],
  ["approval_decision", "Human approval recorded"],
  ["remediation_executed", "Controlled action executed"],
  ["recovery_checked", "Recovery verified"],
  ["incident_resolved", "Incident resolved"],
];

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) throw new Error(await response.text());
  return response.json();
}

function pct(value) {
  return `${(value * 100).toFixed(1)}%`;
}

function metricCard(title, snapshot) {
  if (!snapshot) {
    return `<div class="metric-card"><h3>${title}</h3><div class="metric-row"><span>Status</span><strong>Pending</strong></div></div>`;
  }
  return `<div class="metric-card">
    <h3>${title}</h3>
    <div class="metric-row"><span>Latency</span><strong>${snapshot.latency_ms} ms</strong></div>
    <div class="metric-row"><span>Error rate</span><strong>${pct(snapshot.error_rate)}</strong></div>
    <div class="metric-row"><span>Throughput</span><strong>${snapshot.throughput_rpm} rpm</strong></div>
    <div class="metric-row"><span>DB health</span><strong>${pct(snapshot.database_health)}</strong></div>
    <div class="metric-row"><span>Redis health</span><strong>${pct(snapshot.redis_health)}</strong></div>
    <div class="metric-row"><span>Worker lag</span><strong>${snapshot.worker_lag_ms} ms</strong></div>
  </div>`;
}

function renderIncident() {
  const incident = state.incident;
  const traceTypes = new Set((incident?.trace || []).map((item) => item.event_type));
  document.querySelector("#scenarioName").textContent = incident ? incident.scenario.replaceAll("_", " ") : "healthy baseline";
  document.querySelector("#activeIncidents").textContent = incident && incident.status !== "resolved" ? "1" : "0";
  document.querySelector("#metrics").innerHTML = [
    metricCard("Before", incident?.before),
    metricCard("During", incident?.during),
    metricCard("After", incident?.after),
  ].join("");
  document.querySelector("#lifecycleSteps").innerHTML = lifecycleLabels
    .map(([type, label]) => `<li class="${traceTypes.has(type) ? "done" : ""}">${label}</li>`)
    .join("");
  document.querySelector("#evidence").innerHTML = (incident?.evidence || [])
    .map((item) => `<div class="evidence-item"><strong>${item.source}: ${item.id}</strong><small>${item.summary}</small></div>`)
    .join("") || `<div class="evidence-item"><strong>No incident evidence</strong><small>Inject a scenario to generate logs, metrics, and dependency evidence.</small></div>`;
  const rca = incident?.investigation;
  document.querySelector("#confidence").textContent = rca ? `${Math.round(rca.confidence * 100)}% confidence` : "--";
  document.querySelector("#rca").innerHTML = rca
    ? `<div><span>Likely root cause</span><br><strong>${rca.likely_root_cause}</strong></div><div><span>Affected service</span><br><strong>${rca.affected_service}</strong></div><div><span>Evidence</span><br><strong>${rca.supporting_evidence.join(", ")}</strong></div>`
    : `<div><span>Likely root cause</span><br><strong>Waiting for incident</strong></div>`;
  const risk = incident?.risk;
  document.querySelector("#riskScore").textContent = risk ? `${risk.score}/100` : "--";
  document.querySelector("#riskLevel").textContent = risk ? `${risk.level}${risk.approval_required ? " / approval required" : ""}` : "--";
  document.querySelector("#riskFactors").innerHTML = risk
    ? Object.entries(risk.factors).map(([key, value]) => `<div class="factor-row"><span>${key.replaceAll("_", " ")}</span><strong>${value}</strong></div>`).join("")
    : `<div class="factor-row"><span>Status</span><strong>Pending</strong></div>`;
  const action = incident?.selected_action;
  document.querySelector("#remediation").innerHTML = action
    ? `<div><span>Action</span><br><strong>${action.id}</strong></div><div><span>Description</span><br><strong>${action.description}</strong></div><div><span>Status</span><br><strong>${incident.execution?.status || "selected"}</strong></div>`
    : `<div><span>Action</span><br><strong>No registered action selected</strong></div>`;
  const recovery = incident?.recovery;
  document.querySelector("#recoveryState").textContent = recovery ? (recovery.recovered ? "resolved" : "failed") : "pending";
  document.querySelector("#recovery").innerHTML = recovery
    ? Object.entries(recovery.criteria).map(([key, value]) => `<div class="factor-row"><span>${key.replaceAll("_", " ")}</span><strong class="${value ? "ok" : "bad"}">${value ? "pass" : "fail"}</strong></div>`).join("")
    : `<div class="factor-row"><span>Status</span><strong>Pending verification</strong></div>`;
  document.querySelector("#trace").innerHTML = (incident?.trace || [])
    .map((event) => `<div class="trace-item"><strong>${event.event_type}</strong><small>${event.message}</small></div>`)
    .join("") || `<div class="trace-item"><strong>No trace events yet</strong><small>The decision trace starts when a scenario is injected.</small></div>`;
  document.querySelector("#approve").disabled = !incident || incident.approval_granted || incident.status === "resolved";
  document.querySelector("#execute").disabled = !incident || incident.status === "resolved";
}

async function loadInitial() {
  const [system, scenarios] = await Promise.all([api("/api/state"), api("/api/scenarios")]);
  document.querySelector("#systemStatus").textContent = system.system_status;
  document.querySelector("#aiStatus").textContent = system.ai_status;
  document.querySelector("#llmStatus").textContent = system.llm_status;
  document.querySelector("#targetSystem").textContent = system.target_system;
  document.querySelector("#scenarioButtons").innerHTML = scenarios
    .map((scenario) => `<button data-scenario="${scenario.id}">${scenario.title}<br><small>${scenario.target_service}</small></button>`)
    .join("");
  document.querySelectorAll("[data-scenario]").forEach((button) => {
    button.addEventListener("click", async () => {
      state.selectedScenario = button.dataset.scenario;
      document.querySelectorAll("[data-scenario]").forEach((item) => item.classList.toggle("active", item === button));
      state.incident = await api("/api/incidents", { method: "POST", body: JSON.stringify({ scenario: state.selectedScenario }) });
      document.querySelector("#systemStatus").textContent = "degraded";
      renderIncident();
    });
  });
  document.querySelector(`[data-scenario="${state.selectedScenario}"]`)?.classList.add("active");
  renderIncident();
}

document.querySelector("#runLifecycle").addEventListener("click", async () => {
  state.incident = await api("/api/lifecycle", { method: "POST", body: JSON.stringify({ scenario: state.selectedScenario }) });
  document.querySelector("#systemStatus").textContent = "healthy";
  renderIncident();
});

document.querySelector("#approve").addEventListener("click", async () => {
  if (!state.incident) return;
  state.incident = await api(`/api/incidents/${state.incident.id}/approve`, { method: "POST" });
  renderIncident();
});

document.querySelector("#execute").addEventListener("click", async () => {
  if (!state.incident) return;
  state.incident = await api(`/api/incidents/${state.incident.id}/execute`, { method: "POST" });
  document.querySelector("#systemStatus").textContent = state.incident.status === "resolved" ? "healthy" : "degraded";
  renderIncident();
});

document.querySelector("#reset").addEventListener("click", async () => {
  await api("/api/reset", { method: "POST" });
  state.incident = null;
  document.querySelector("#systemStatus").textContent = "healthy";
  renderIncident();
});

loadInitial();
