/* RaipurNetra AI - Command Center dashboard logic */
const $ = id => document.getElementById(id);
const $q = sel => document.querySelector(sel);
const fmt = n => (n ?? 0).toLocaleString("en-IN");
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;", "'": "&#39;" }[c]));
const pill = (text, cls) => `<span class="pill ${cls}">${esc(text)}</span>`;
const riskPill = r => pill(r, r === "high" ? "red" : r === "medium" ? "orange" : "green");
const congPill = c => pill(Math.round(c) + "%", c >= 70 ? "red" : c >= 50 ? "orange" : c >= 30 ? "yellow" : "green");

let STATE = null, PRED = null, activeTab = "command", routeFilter = "all";

async function api(path, opts) {
  const r = await fetch(path, opts);
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json();
}

/* ============================ theme switching ============================ */
function applyTheme(name) {
  document.documentElement.dataset.theme = name;
  localStorage.setItem("rn-theme", name);
  document.querySelectorAll(".theme-btn").forEach(b => b.classList.toggle("active", b.dataset.theme === name));
  if (window.MapViz) {
    MapViz.applyTheme(name);
    if (STATE) MapViz.update(STATE);           // re-tint schematic immediately
  }
  if (window._HIST && window._HIST.length) drawCityChart();
}

function initTheme() {
  applyTheme(localStorage.getItem("rn-theme") || "dark");
  document.querySelectorAll(".theme-btn").forEach(b => {
    b.onclick = () => applyTheme(b.dataset.theme);
  });
}

/* ============================ polling ============================ */
async function pollState() {
  try {
    STATE = await api("/api/state");
    renderHeader();
    renderKPIs();
    MapViz.update(STATE);
    MapViz.updateLeaflet(STATE);
    renderEmergencyBanner();
    if (activeTab === "signals") renderSignals();
    if (activeTab === "transport") renderTransport();
    if (activeTab === "parking") renderParking();
  } catch (e) { console.warn("state poll failed", e); }
}

async function pollPredictions() {
  try {
    PRED = await api("/api/predictions");
    renderAlerts();
    if (activeTab === "prediction") renderPredictions();
    if (activeTab === "command") drawCityChart();
  } catch (e) { console.warn("pred poll failed", e); }
}

async function pollHistory() {
  if (activeTab === "command") {
    try { window._HIST = (await api("/api/history?minutes=120")).series; drawCityChart(); } catch (e) {}
  }
}

/* ============================ header ============================ */
function renderHeader() {
  const k = STATE.kpis;
  $("badge-weather").textContent = (k.weather === "rain" ? "🌧️ Rain" : "☀️ Clear") + (k.closed_roads.length ? ` · ${k.closed_roads.length} road closed` : "");
  const ev = $("badge-event");
  if (k.event) { ev.textContent = "🎪 " + k.event; ev.classList.remove("hidden"); } else ev.classList.add("hidden");
  $("badge-cams").textContent = `${k.cameras_online} cams · ${fmt(k.vehicles_today)} veh today`;
}

setInterval(() => {
  const t = STATE?.kpis?.time;
  $("badge-clock").textContent = t ? t.slice(11, 19) + " IST" : "--:--:--";
}, 1000);

/* ============================ KPIs ============================ */
function kpiCard(l, v, sub, bad) {
  return `<div class="kpi"><div class="v">${v}</div><div class="l">${esc(l)}</div><div class="d ${bad ? "bad" : ""}">${esc(sub || "")}</div></div>`;
}

function renderKPIs() {
  const k = STATE.kpis;
  const a = window._ANPRSNAP;
  const risk = PRED ? Object.values(PRED.predictions).filter(p => p.risk !== "low").length : null;
  $("kpi-grid").innerHTML =
    kpiCard("City Congestion", Math.round(k.city_congestion) + "%", "live CCTV mirror", k.city_congestion > 60) +
    kpiCard("Avg Signal Wait", Math.round(k.avg_wait_adaptive) + "s", `-${Math.round(k.wait_reduction_pct)}% vs fixed timer`) +
    kpiCard("Vehicles Today", fmt(k.vehicles_today), "YOLOv8 detections") +
    kpiCard("Violations / Challans", `${a ? a.counters.violations : "-"} / ${a ? a.counters.challans : "-"}`, "auto e-challan engine") +
    kpiCard("Challan Revenue", "Rs. " + fmt(a ? a.revenue.generated : 0), "this session") +
    kpiCard("Buses Tracked", k.buses_active, "live GPS") +
    kpiCard("Predictions @ Risk", risk === null ? "-" : risk, "30-min horizon", risk > 0);
}

/* ============================ city chart ============================ */
function drawCityChart() {
  const hist = window._HIST || [];
  const series = [{ label: "Live congestion", color: "#38bdf8", data: hist.map(h => ({ t: h.t, v: h.city })), fill: true }];
  if (PRED) {
    const mean = Object.values(PRED.predictions).reduce((s, p) => s + p.predicted_30min, 0) / Math.max(1, Object.keys(PRED.predictions).length);
    const last = hist[hist.length - 1];
    if (last) series.push({
      label: "AI forecast +30min", color: "#f87171", dash: "6 5", width: 2.4,
      data: [{ t: last.t, v: last.city }, { t: last.t, v: mean }]
    });
  }
  Charts.line($("city-chart"), series, { autoScale: true, floor: 0 });
}

/* ============================ alerts ============================ */
function renderAlerts() {
  const feed = $("alert-feed");
  const alerts = PRED?.alerts || [];
  if (!alerts.length) {
    feed.innerHTML = `<p class="muted small">✅ No congestion risks predicted in the next 30 minutes. All junctions within safe limits.</p>`;
  } else {
    feed.innerHTML = alerts.map(p => `
      <div class="alert-item">
        <b>⚠ ${esc(p.name)}</b> — predicted ${Math.round(p.predicted_30min)}% in 30 min (now ${Math.round(p.current)}%) ${riskPill(p.risk)}
        <div class="actions">${(p.actions || []).map(esc).join("<br>• ")}</div>
      </div>`).join("");
  }
  api("/api/violations?limit=1").then(a => {
    if (a.hotspot) $("hotspot-card").innerHTML =
      `<b style="color:var(--orange)">${esc(STATE.junctions[a.hotspot]?.name || a.hotspot)}</b> leads violations with
       <b>${a.heatmap_total[a.hotspot]}</b> detected this session.
       <div class="muted small">Recommendation: increase patrol + review camera angle. Weekly report auto-flags chronic hotspots.</div>`;
  }).catch(() => {});
}

/* ============================ digital twin ============================ */
function initTwin() {
  MapViz.init($("city-map"));
  const roadSel = $("wi-road"), jSel = $("wi-junction");
  api("/api/meta").then(meta => {
    roadSel.innerHTML = Object.entries(meta.roads).map(([id, r]) => `<option value="${id}">${esc(r.name)}</option>`).join("");
    jSel.innerHTML = Object.entries(meta.junctions).map(([id, j]) => `<option value="${id}">${esc(j.name)}</option>`).join("");
    // Leaflet real-map (lazy: only when first switched to)
    MapViz.initLeaflet("city-leaflet", meta.tile_url, meta.tile_attr);
  }).catch(() => {
    MapViz.initLeaflet("city-leaflet", null, null);
  });
  $("btn-view-svg").onclick = () => setMapView("svg");
  $("btn-view-map").onclick = () => setMapView("map");
  $("btn-close-road").onclick = () => applyWhatIf({ action: "close_road", road: roadSel.value });
  $("btn-open-road").onclick = () => applyWhatIf({ action: "open_road", road: roadSel.value });
  $("btn-rain").onclick = () => applyWhatIf({ action: "weather", value: (STATE?.kpis.weather === "rain") ? "clear" : "rain" });
  $("btn-event").onclick = () => applyWhatIf({ action: "event", value: (STATE?.kpis.event && STATE.kpis.event.includes("What-if")) ? "off" : "on" });
  $("btn-signal-mode").onclick = () => applyWhatIf({ action: "signal_mode", junction: jSel.value, value: $("wi-mode").value || null });
  $("btn-whatif-reset").onclick = () => { applyWhatIf({ action: "reset" }); $("whatif-impact").textContent = "Scenario reset. City back to live operations."; };
  $("btn-whatif-impact").onclick = measureImpact;
}

function setMapView(mode) {
  MapViz.setMode(mode);
  const svg = $("city-map"), leaf = $("city-leaflet");
  if (mode === "map") {
    svg.classList.add("hidden"); leaf.classList.remove("hidden");
    $("btn-view-map").classList.add("active"); $("btn-view-svg").classList.remove("active");
  } else {
    svg.classList.remove("hidden"); leaf.classList.add("hidden");
    $("btn-view-svg").classList.add("active"); $("btn-view-map").classList.remove("active");
  }
}

async function applyWhatIf(body) {
  try {
    await api("/api/whatif", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    await pollState();
  } catch (e) { console.warn(e); }
}

async function measureImpact() {
  try {
    const imp = await api("/api/whatif/impact");
    const rows = Object.entries(imp.delta).sort((a, b) => b[1] - a[1]).slice(0, 6)
      .map(([jid, d]) => {
        const name = STATE.junctions[jid]?.name || jid;
        const cls = d > 3 ? "red" : d < -3 ? "green" : "gray";
        return `<div class="heat-row"><span>${esc(name)}</span><span class="bar"><i style="width:${Math.min(100, Math.abs(d) * 5)}%;background:${d > 3 ? "var(--red)" : d < -3 ? "var(--green)" : "#64748b"}"></i></span><b class="pill ${cls}">${d > 0 ? "+" : ""}${d}%</b></div>`;
      }).join("");
    $("whatif-impact").innerHTML =
      `<p>Worst hit: <b>${esc(imp.worst_hit.name)}</b> (${imp.worst_hit.delta > 0 ? "+" : ""}${imp.worst_hit.delta}% forecast change)</p>${rows}`;
  } catch (e) { console.warn(e); }
}

/* ============================ signals ============================ */
function renderSignals() {
  const tb = $q("#signals-table tbody");
  tb.innerHTML = Object.values(STATE.junctions).map(j => {
    const s = j.signal;
    return `<tr>
      <td><b>${esc(j.name)}</b><br><span class="muted small">${esc(j.camera)}</span></td>
      <td>${pill(s.mode === "adaptive" ? "AI Adaptive" : "Fixed", s.mode === "adaptive" ? "blue" : "gray")}</td>
      <td>${pill(s.phase.toUpperCase() + " GREEN", "green")}</td>
      <td>${Math.round(s.green_time)}s</td>
      <td>${s.queues.ns.toFixed(0)}</td><td>${s.queues.ew.toFixed(0)}</td>
      <td>${s.avg_wait_adaptive.toFixed(0)}s</td>
      <td>${s.avg_wait_fixed.toFixed(0)}s</td>
      <td>${pill(s.wait_saved_pct.toFixed(0) + "% saved", s.wait_saved_pct > 15 ? "green" : s.wait_saved_pct > 5 ? "yellow" : "gray")}</td>
      <td><select data-jid="${j.id}" class="mode-sel">
        <option value="adaptive" ${s.mode === "adaptive" ? "selected" : ""}>Adaptive</option>
        <option value="fixed" ${s.mode === "fixed" ? "selected" : ""}>Fixed</option>
      </select></td>
    </tr>`;
  }).join("");
  tb.querySelectorAll(".mode-sel").forEach(sel => {
    sel.onchange = async () => {
      await api(`/api/signals/${sel.dataset.jid}/mode`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ mode: sel.value })
      });
      pollState();
    };
  });
}

/* ============================ ANPR ============================ */
async function refreshAnpr() {
  try {
    const a = await api("/api/violations?limit=80");
    window._ANPRSNAP = a;
    $("anpr-kpis").innerHTML = `
      <div class="kpi"><div class="v">${fmt(a.counters.detections)}</div><div class="l">Vehicles Scanned</div></div>
      <div class="kpi"><div class="v">${fmt(a.counters.violations)}</div><div class="l">Violations Detected</div><div class="d">85%+ vs 5-10% manual</div></div>
      <div class="kpi"><div class="v">${fmt(a.counters.challans)}</div><div class="l">e-Challans Sent</div><div class="d">${a.counters.paid} paid</div></div>
      <div class="kpi"><div class="v">Rs. ${fmt(a.revenue.generated)}</div><div class="l">Revenue Generated</div></div>
      <div class="kpi"><div class="v">Rs. ${fmt(a.revenue_monthly_projected)}</div><div class="l">Monthly Projection</div><div class="d">at 100 violations/day</div></div>
      <div class="kpi"><div class="v">${a.hotspot ? esc(STATE?.junctions[a.hotspot]?.name.split(" ")[0] || "-") : "-"}</div><div class="l">Violation Hotspot</div></div>`;
    // heatmap
    const maxV = Math.max(1, ...Object.values(a.heatmap_total));
    $("heatmap").innerHTML = Object.entries(a.heatmap_total).sort((x, y) => y[1] - x[1]).map(([jid, total]) => {
      const hm = a.heatmap[jid];
      const seg = Object.entries(hm).map(([v, c]) => c ? `<i style="width:${c / maxV * 100}%;background:${{ red_light: "#f87171", no_helmet: "#facc15", wrong_way: "#fb923c", overspeed: "#f472b6" }[v]}"></i>` : "").join("");
      return `<div class="heat-row"><span>${esc(STATE?.junctions[jid]?.name || jid)}</span><span class="bar">${seg}</span><b>${total}</b></div>`;
    }).join("");
    // detections
    $q("#detections-table tbody").innerHTML = a.detections.slice(0, 40).map(d => `
      <tr><td class="muted">${d.t.slice(11, 19)}</td><td>${esc(d.camera)}</td>
      <td><b>${esc(d.plate)}</b></td><td>${esc(d.vehicle_type)}</td>
      <td>${d.violation ? pill(d.violation.replace("_", " "), "red") : pill("clean", "green")}</td>
      <td>${d.speed_kmph} km/h</td><td>${Math.round(d.confidence * 100)}%</td></tr>`).join("");
    // challans
    $q("#challans-table tbody").innerHTML = a.challans.slice(0, 25).map(c => `
      <tr><td class="muted">${esc(c.id)}</td><td><b>${esc(c.plate)}</b></td><td>${esc(c.owner)}</td>
      <td>${pill(c.violation_label, "orange")} <span class="muted small">@${esc(c.junction_name)}</span></td>
      <td>Rs. ${fmt(c.fine)}</td><td>${pill(c.status, c.status === "paid" ? "green" : "blue")}</td></tr>`).join("");
  } catch (e) { console.warn(e); }
}

/* ============================ prediction ============================ */
function renderPredictions() {
  if (!PRED) return;
  const m30 = Object.entries(PRED.metrics || {}).filter(([k]) => k.endsWith("@30"));
  const avgMae = m30.reduce((s, [, x]) => s + x.mae, 0) / Math.max(1, m30.length);
  const avgHit = m30.reduce((s, [, x]) => s + x.hit_rate, 0) / Math.max(1, m30.length);
  const avgR2 = m30.reduce((s, [, x]) => s + (x.r2 || 0), 0) / Math.max(1, m30.length);
  // top features across junctions (30-min horizon)
  const feats = {};
  Object.entries(PRED.importances || {}).filter(([k]) => k.endsWith("@30")).forEach(([, imp]) => {
    for (const [f, v] of Object.entries(imp)) feats[f] = (feats[f] || 0) + v;
  });
  const topFeats = Object.entries(feats).sort((a, b) => b[1] - a[1]).slice(0, 5);
  const maxFeat = topFeats.length ? topFeats[0][1] : 1;
  $("model-card").innerHTML = `
    <h3>Prediction Engine — ${esc(PRED.model)} <button class="btn small" id="btn-retrain" style="float:right">↻ Retrain on live data</button></h3>
    <div class="kpi-grid" style="margin-bottom:8px">
      <div class="kpi"><div class="v">${Math.round(avgHit)}%</div><div class="l">Congestion Hit-Rate</div><div class="d">80%+ target</div></div>
      <div class="kpi"><div class="v">${avgMae.toFixed(1)}</div><div class="l">MAE (index pts)</div></div>
      <div class="kpi"><div class="v">${avgR2.toFixed(2)}</div><div class="l">R² (validation)</div></div>
      <div class="kpi"><div class="v">${(PRED.horizons_min || [30]).join(" + ")} min</div><div class="l">Prediction Horizons</div></div>
      <div class="kpi"><div class="v">${esc(PRED.trained_at?.slice(11, 19) || "-")}</div><div class="l">Last Trained (IST)</div><div class="d">models persisted to disk</div></div>
    </div>
    <div class="muted small">Top predictive features (mean importance, 30-min horizon): ${topFeats.map(([f]) => esc(f)).join(", ")}</div>
    ${topFeats.map(([f, v]) => `<div class="heat-row"><span class="small">${esc(f)}</span><span class="bar"><i style="width:${(v / maxFeat) * 100}%;background:var(--accent)"></i></span></div>`).join("")}`;
  $("btn-retrain").onclick = async () => {
    await api("/api/predictions/retrain", { method: "POST" });
    pollPredictions();
  };
  $("prediction-grid").innerHTML = Object.values(PRED.predictions).map(p => {
    return `<div class="pred-card">
      <h4>${esc(p.name)} ${riskPill(p.risk)}</h4>
      <div class="pred-vals"><span>Now: <b>${Math.round(p.current)}%</b></span>
      <span>+30m: <b style="color:${p.delta > 0 ? "var(--red)" : "var(--green)"}">${Math.round(p.predicted_30min)}%</b></span>
      <span class="muted">+60m: ${Math.round(p.predicted_60min)}%</span></div>
      <div class="bar"><i style="width:${p.predicted_30min}%;background:${p.risk === "high" ? "var(--red)" : p.risk === "medium" ? "var(--orange)" : "var(--green)"}"></i></div>
      ${p.actions ? `<div class="pred-actions"><b>Preemptive actions:</b><ul>${p.actions.map(a => `<li>${esc(a)}</li>`).join("")}</ul></div>` : ""}
    </div>`;
  }).join("");
}

/* ============================ transport ============================ */
function renderTransport() {
  const buses = (STATE?.buses || []).filter(b => routeFilter === "all" || b.route === routeFilter);
  $q("#bus-table tbody").innerHTML = buses.map(b => `
    <tr><td><b>${esc(b.id)}</b></td>
    <td>${pill(b.route + " · " + b.route_name, "blue")}</td>
    <td class="muted">${esc(STATE.junctions[b.from]?.name || b.from)} → ${esc(b.next_stop)}</td>
    <td><b>${esc(b.next_stop)}</b></td>
    <td>${b.eta_min} min</td>
    <td>${pill(Math.abs(b.delay_min) < 3 ? "on time" : (b.delay_min > 0 ? `+${b.delay_min} min late` : `${Math.abs(b.delay_min)} min early`), Math.abs(b.delay_min) < 3 ? "green" : b.delay_min > 5 ? "red" : "yellow")}</td>
    <td><div class="bar" style="width:90px"><i style="width:${b.occupancy / 60 * 100}%;background:var(--yellow)"></i></div><span class="muted small">${b.occupancy} pax</span></td>
    <td>${b.speed} km/h</td></tr>`).join("");
}

/* ============================ parking ============================ */
function renderParking() {
  $("parking-grid").innerHTML = Object.values(STATE.parking).map(p => {
    const pct = p.pct, col = pct > 90 ? "var(--red)" : pct > 70 ? "var(--orange)" : "var(--green)";
    return `<div class="pred-card">
      <h4>${esc(p.name)}</h4>
      <div class="pred-vals"><span><b style="font-size:18px;color:${col}">${p.free}</b> free</span><span class="muted">of ${p.total}</span></div>
      <div class="bar"><i style="width:${pct}%;background:${col}"></i></div>
      <p class="muted small" style="margin-top:6px">${pill(Math.round(pct) + "% occupied", pct > 90 ? "red" : pct > 70 ? "orange" : "green")} · CV occupancy via ${pct > 0 ? "existing CCTV" : "-"}</p>
    </div>`;
  }).join("");
}

/* ============================ rides ============================ */
async function initRides() {
  // populate from /api/meta — independent of the first /api/state poll
  try {
    const meta = await api("/api/meta");
    const opts = Object.entries(meta.junctions).map(([id, j]) => `<option value="${id}">${esc(j.name)}</option>`).join("");
    $("ride-origin").innerHTML = opts;
    $("ride-dest").innerHTML = opts;
    $("ride-dest").selectedIndex = Math.min(3, Math.max(0, $("ride-dest").options.length - 1));
  } catch (e) { console.warn("ride select init failed", e); }
  $("btn-ride-register").onclick = async () => {
    const body = {
      name: $("ride-name").value || "Demo user", contact: $("ride-contact").value || "wa-demo",
      origin: $("ride-origin").value, destination: $("ride-dest").value,
      time_pref: $("ride-time").value || "09:00", gender_pref: $("ride-gender").value
    };
    const r = await api("/api/rides/register", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });
    $("ride-match-result").innerHTML = (r.matches || []).length
      ? `<h3 style="margin-top:12px">Your matches</h3>` + r.matches.map(m => `
          <div class="alert-item" style="border-color:var(--green)"><b>${esc(m.match.name)}</b> · ${esc(m.match.origin_name)} → ${esc(m.match.destination_name)} @ ${esc(m.match.time)}
          <div class="actions">Score <b>${m.score}</b> · est. vehicle share ${esc(m.est_share)} · contact: ${esc(m.match.contact)}</div></div>`).join("")
      : `<p class="muted small" style="margin-top:10px">Registered (ID ${esc(r.registered.id)}). No match yet — we'll ping you on WhatsApp.</p>`;
    refreshRides();
  };
  refreshRides();
}

async function refreshRides() {
  try {
    const r = await api("/api/rides");
    $q("#rides-table tbody").innerHTML = r.commuters.slice().reverse().map(c => `
      <tr><td class="muted">${esc(c.id)}</td><td>${esc(c.name)}</td><td>${esc(c.origin_name)}</td><td>${esc(c.destination_name)}</td><td>${esc(c.time)}</td></tr>`).join("");
  } catch (e) {}
}

/* ============================ analytics ============================ */
async function refreshAnalytics() {
  try {
    const a = await api("/api/analytics");
    window._ANPRSNAP = window._ANPRSNAP || null;
    $("analytics-kpis").innerHTML = `
      <div class="kpi"><div class="v">${Math.round(a.kpis.city_congestion)}%</div><div class="l">City Congestion</div></div>
      <div class="kpi"><div class="v">${Math.round(a.kpis.avg_wait_adaptive)}s</div><div class="l">Avg Wait (Adaptive)</div><div class="d">fixed baseline ${Math.round(a.kpis.avg_wait_fixed)}s</div></div>
      <div class="kpi"><div class="v">${fmt(a.violations.counters.violations)}</div><div class="l">Violations Today</div></div>
      <div class="kpi"><div class="v">Rs. ${fmt(a.violations.revenue.generated)}</div><div class="l">Challan Revenue</div></div>
      <div class="kpi"><div class="v">${a.bus.punctuality_pct}%</div><div class="l">Bus Punctuality</div><div class="d">40-50% before</div></div>
      <div class="kpi"><div class="v">${a.prediction_risk_counts.high + a.prediction_risk_counts.medium}</div><div class="l">Junctions @ Risk +30m</div></div>`;
    $q("#impact-table tbody").innerHTML = a.impact_table.map(r => `
      <tr><td><b>${esc(r.metric)}</b></td><td class="muted">${esc(r.current)}</td><td>${esc(r.after)}</td>
      <td>${pill(r.improvement, "green")}</td></tr>`).join("");
    $("revenue-card").innerHTML = `
      <div class="heat-row"><span>e-Challan fines (session)</span><b>Rs. ${fmt(a.violations.revenue.generated)}</b></div>
      <div class="heat-row"><span>Collected</span><b>Rs. ${fmt(a.violations.revenue.collected)}</b></div>
      <div class="heat-row"><span>Monthly projection</span><b>Rs. ${fmt(a.cost_model.monthly_revenue_projected)}</b></div>
      <p class="muted small" style="margin-top:8px">Self-sustaining from automated enforcement — e-challans + smart parking + ride premium, with no taxpayer funding required.</p>`;
  } catch (e) { console.warn(e); }
}

/* ============================ emergency ============================ */
function renderEmergencyBanner() {
  const em = STATE?.emergency;
  const banner = $("emergency-banner");
  if (em?.active) {
    banner.classList.remove("hidden");
    $("em-text").textContent = `${em.vehicle} · route: ${em.route.map(r => STATE.junctions[r]?.name || r).join(" → ")} · all signals forced GREEN`;
  } else banner.classList.add("hidden");
}

function initEmergency() {
  $("btn-emergency-panel").onclick = async () => {
    const em = STATE?.emergency;
    if (em?.active) return;
    await api("/api/emergency", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ activate: true, route: ["jaistambh", "telibandha", "marine"] })
    });
    pollState();
  };
  $("btn-emergency-stop").onclick = async () => {
    await api("/api/emergency", {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ activate: false })
    });
    pollState();
  };
}

/* ============================ tabs & boot ============================ */
function switchTab(name) {
  activeTab = name;
  document.querySelectorAll("nav#tabs button").forEach(b => b.classList.toggle("active", b.dataset.tab === name));
  document.querySelectorAll(".tab").forEach(s => s.classList.toggle("active", s.id === `tab-${name}`));
  if (name === "anpr") refreshAnpr();
  if (name === "prediction") renderPredictions();
  if (name === "analytics") refreshAnalytics();
  if (name === "rides") refreshRides();
  if (name === "vision") Vision.startPolling(); else Vision.stopPolling();
  if (name === "command") { pollHistory(); pollPredictions(); }
}

function boot() {
  initTheme();
  document.querySelectorAll("nav#tabs button").forEach(b => b.onclick = () => switchTab(b.dataset.tab));
  $("btn-burst").onclick = async () => { await api(`/api/violations/burst?n=10${STATE ? "" : ""}`, { method: "POST" }); refreshAnpr(); };
  $("btn-lookup").onclick = async () => {
    const plate = $("plate-input").value.trim();
    if (!plate) return;
    const r = await api("/api/anpr/lookup", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ plate }) });
    $("plate-result").innerHTML = r.valid_format
      ? `<div class="alert-item" style="margin-top:10px;border-color:var(--green)"><b>${esc(r.plate)}</b> — ${esc(r.owner_record.owner)} · ${esc(r.owner_record.model)} (${esc(r.owner_record.vehicle_type)})<br>
         <span class="muted small">RTO ${esc(r.owner_record.rto)} · pending challans: ${r.owner_record.challans_pending} · session history: ${r.challan_history.length}</span></div>`
      : `<p class="small" style="color:var(--red);margin-top:8px">Invalid plate format. Expected CG-04-XX-XXXX (OCR would reject).</p>`;
  };
  $("btn-report").onclick = async () => {
    const r = await api("/api/report/daily", { method: "POST" });
    $("report-result").innerHTML = `✅ Generated <b>${esc(r.file)}</b> — <a style="color:var(--accent)" href="/api/report/view?file=${encodeURIComponent(r.file)}" target="_blank">open report</a>`;
  };
  document.querySelectorAll("#route-filter button").forEach(b => {
    b.onclick = () => {
      routeFilter = b.dataset.route;
      document.querySelectorAll("#route-filter button").forEach(x => x.classList.toggle("active", x === b));
      renderTransport();
    };
  });
  initTwin(); initRides(); initEmergency(); Bot.init(); Vision.init();
  fetch("/api/whatsapp/status").then(r => r.json()).then(s => {
    const el = $("wa-config-state");
    if (el) el.innerHTML = s.configured
      ? `✅ <b>LIVE:</b> Graph API configured (${esc(s.phone_number_id)})`
      : "Simulator mode — set <b>WHATSAPP_TOKEN</b> + <b>WHATSAPP_PHONE_NUMBER_ID</b> in .env to go live.";
  }).catch(() => {});
  pollState(); pollPredictions(); pollHistory(); refreshAnpr();
  setInterval(pollState, 2000);
  setInterval(pollPredictions, 6000);
  setInterval(pollHistory, 30000);
  setInterval(() => { if (activeTab === "anpr") refreshAnpr(); }, 4000);
  setInterval(() => { if (activeTab === "analytics") refreshAnalytics(); }, 12000);
}

document.addEventListener("DOMContentLoaded", boot);
