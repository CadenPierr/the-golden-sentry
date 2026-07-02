/* The Golden Sentry — dashboard client.
   Polls /api/status, renders the watch brief, region cards, chart, and
   anomaly log. No framework: the whole UI is ~150 lines of vanilla JS. */

const POLL_SECONDS = 60;
let chart = null;
let selectedRegion = null;

async function fetchJSON(url, opts) {
  const res = await fetch(url, opts);
  if (!res.ok) throw new Error(`${url} -> ${res.status}`);
  return res.json();
}

function fmtMW(v) {
  return v == null ? "—" : `${Math.round(v).toLocaleString()} MW`;
}

function fmtPct(v) {
  return v == null ? "—" : `${(v * 100).toFixed(1)}%`;
}

function levelColor(level) {
  return { NORMAL: "#3fb950", ELEVATED: "#d4a017", HIGH: "#f0883e", CRITICAL: "#f85149" }[level] || "#7a8699";
}

function renderBrief(data) {
  const brief = data.brief;
  const badge = document.getElementById("watch-level");
  badge.textContent = brief.watch_level;
  badge.className = `level-badge level-${brief.watch_level}`;
  document.getElementById("brief-headline").textContent = brief.headline;
  document.getElementById("brief-body").textContent = brief.brief;
  document.getElementById("brief-source").textContent =
    brief.source === "claude" ? "brief by claude watch officer" : "rule-based brief (no api key)";

  const mode = document.getElementById("mode-badge");
  mode.textContent = data.mode === "live" ? "LIVE — EIA DATA" : "DEMO — SYNTHETIC DATA";
  mode.className = `badge ${data.mode}`;
  document.getElementById("updated-at").textContent =
    `updated ${new Date(data.generated_at).toLocaleTimeString()}`;
}

function renderRegions(regions) {
  const grid = document.getElementById("region-grid");
  grid.innerHTML = "";
  for (const r of regions) {
    const card = document.createElement("div");
    card.className = "region-card" + (r.code === selectedRegion ? " selected" : "");
    const dev = r.forecast_dev == null ? "" :
      `${r.forecast_dev >= 0 ? "+" : ""}${fmtPct(r.forecast_dev)} vs forecast`;
    card.innerHTML = `
      <div class="rc-top">
        <span class="rc-op">${r.operator}</span>
        <span class="rc-name">${r.name}</span>
      </div>
      <div class="rc-demand">${fmtMW(r.demand_mw)}</div>
      <div class="rc-dev">${dev}</div>
      <div class="stress-bar">
        <div class="stress-fill" style="width:${r.stress}%;background:${levelColor(r.level)}"></div>
      </div>
      <div class="rc-stress-label">
        <span>stress ${r.stress.toFixed(0)}/100</span>
        <span style="color:${levelColor(r.level)}">${r.level}</span>
      </div>`;
    card.addEventListener("click", () => selectRegion(r.code));
    grid.appendChild(card);
  }
}

function renderAnomalies(anomalies) {
  const tbody = document.querySelector("#anomaly-table tbody");
  const empty = document.getElementById("no-anomalies");
  tbody.innerHTML = "";
  empty.hidden = anomalies.length > 0;
  document.getElementById("anomaly-table").hidden = anomalies.length === 0;
  for (const a of anomalies.slice(0, 25)) {
    const tr = document.createElement("tr");
    tr.innerHTML = `
      <td>${a.ts.slice(11, 16)} &middot; ${a.ts.slice(5, 10)}</td>
      <td>${a.region}</td>
      <td>${a.kind.replace("_", " ")}</td>
      <td class="sev-${a.severity}">${a.severity.toUpperCase()}</td>
      <td>${a.detail}</td>`;
    tbody.appendChild(tr);
  }
}

async function selectRegion(code) {
  selectedRegion = code;
  document.getElementById("region-select").value = code;
  document.querySelectorAll(".region-card").forEach(c => c.classList.remove("selected"));
  const series = await fetchJSON(`/api/regions/${code}/series`);
  renderChart(series);
}

function renderChart(series) {
  const labels = series.timestamps.map(t => t.slice(11, 16));
  const ctx = document.getElementById("demand-chart");
  const config = {
    type: "line",
    data: {
      labels,
      datasets: [
        {
          label: "Actual demand (MW)",
          data: series.demand_mw,
          borderColor: "#d4a017",
          backgroundColor: "rgba(212,160,23,0.08)",
          fill: true, pointRadius: 0, borderWidth: 2, tension: 0.3,
        },
        {
          label: "Day-ahead forecast (MW)",
          data: series.forecast_mw,
          borderColor: "#4d80c9",
          borderDash: [6, 4], pointRadius: 0, borderWidth: 1.5, tension: 0.3,
        },
      ],
    },
    options: {
      animation: false,
      plugins: { legend: { labels: { color: "#7a8699" } } },
      scales: {
        x: { ticks: { color: "#7a8699", maxTicksLimit: 12 }, grid: { color: "rgba(31,39,53,.5)" } },
        y: { ticks: { color: "#7a8699" }, grid: { color: "rgba(31,39,53,.5)" } },
      },
    },
  };
  if (chart) { chart.data = config.data; chart.update(); }
  else { chart = new Chart(ctx, config); }
}

async function refresh() {
  try {
    const data = await fetchJSON("/api/status");
    renderBrief(data);
    renderRegions(data.regions);
    renderAnomalies(data.anomalies);

    const select = document.getElementById("region-select");
    if (!select.options.length) {
      for (const r of data.regions) {
        const opt = document.createElement("option");
        opt.value = r.code;
        opt.textContent = `${r.operator} (${r.name})`;
        select.appendChild(opt);
      }
      select.addEventListener("change", e => selectRegion(e.target.value));
      await selectRegion(data.regions[0].code);
    }
  } catch (err) {
    console.error("status fetch failed:", err);
  }
}

document.getElementById("refresh-btn").addEventListener("click", async () => {
  await fetchJSON("/api/refresh", { method: "POST" });
  await refresh();
});

refresh();
setInterval(refresh, POLL_SECONDS * 1000);
