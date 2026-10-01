/* RaipurNetra AI - Video Detection tab (real CV pipeline UI) */
const Vision = (() => {
  let timer = null, junctions = [];

  async function api(path, opts) { const r = await fetch(path, opts); if (!r.ok) throw new Error(await r.text()); return r.json(); }

  function pill(text, cls) { return `<span class="pill ${cls}">${text}</span>`; }

  async function refresh() {
    try {
      const s = await api("/api/vision/status");
      const st = s.stats;
      // frame
      if (["processing", "probing"].includes(s.status)) {
        const img = document.getElementById("vision-frame");
        img.src = "/api/vision/frame?t=" + Date.now();
        img.style.display = "inline-block";
        document.getElementById("vision-placeholder").style.display = "none";
      }
      document.getElementById("vision-live").style.opacity =
        s.status === "processing" ? "1" : ".25";
      // stats
      const det = s.detector || "—";
      const detPill = det.includes("yolo") ? pill("YOLOv8", "blue") : pill("OpenCV MOG2", "yellow");
      document.getElementById("vision-stats").innerHTML = `
        <div class="heat-row"><span>Status</span><b>${pill(s.status.toUpperCase(), s.status === "processing" ? "green" : s.status === "error" ? "red" : "gray")} ${detPill}</b></div>
        <div class="heat-row"><span>Source</span><b>${(s.source || "—").slice(0, 28)}</b></div>
        <div class="heat-row"><span>Progress</span><b>${Math.round((s.progress || 0) * 100)}%${s.loop ? " (looping)" : ""}</b></div>
        <div class="heat-row"><span>Frames analysed</span><b>${st.frames_processed}</b></div>
        <div class="heat-row"><span>Vehicles detected</span><b>${st.vehicles_detected}</b></div>
        <div class="heat-row"><span>Unique tracks</span><b>${st.unique_tracks}</b></div>
        <div class="heat-row"><span>Avg speed</span><b>${st.avg_speed_kmph} km/h</b></div>
        <div class="heat-row"><span>Density / Congestion</span><b>${st.density_pct}% / <b style="color:var(--orange)">${st.congestion_estimate}%</b></b></div>
        <div class="heat-row"><span>Violations (stop-line)</span><b>${st.violations}</b></div>
        <div class="heat-row"><span>Plates OCR'd</span><b>${st.plates_read}</b></div>
        <div class="muted small" style="margin-top:8px">Class mix: ${Object.entries(st.counts).filter(([, v]) => v > 0).map(([k, v]) => `${k}: ${v}`).join(" · ") || "—"}</div>
        ${s.detector_note ? `<div class="muted small" style="margin-top:6px">ℹ️ ${s.detector_note}</div>` : ""}
        ${s.error ? `<div class="small" style="color:var(--red)">Error: ${s.error}</div>` : ""}`;
      // events
      document.querySelector("#vision-events tbody").innerHTML = s.recent_events.map(e => `
        <tr><td class="muted">${e.t.slice(11, 19)}</td><td>#${e.track_id}</td>
        <td>${e.vclass}</td><td><b>${e.plate}</b></td>
        <td>${pill(e.plate_source === "template-ocr" ? `OCR ${e.ocr_confidence}` : "RTO-sim", e.plate_source === "template-ocr" ? "green" : "gray")}</td>
        <td>${e.speed_kmph} km/h</td></tr>`).join("") ||
        `<tr><td colspan="6" class="muted">No violations yet in this pass.</td></tr>`;
    } catch (e) { console.warn("vision refresh failed", e); }
  }

  function startPolling() {
    if (timer) clearInterval(timer);
    refresh();
    timer = setInterval(refresh, 1500);
  }

  function stopPolling() { if (timer) { clearInterval(timer); timer = null; } }

  async function bind(junction) {
    await api("/api/vision/bind", { method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ junction: junction || null }) });
    await refresh();
  }

  function init() {
    document.getElementById("btn-vision-sample").onclick = async () => {
      await api("/api/vision/sample", { method: "POST" });
      startPolling();
    };
    document.getElementById("btn-vision-stop").onclick = async () => { await api("/api/vision/stop", { method: "POST" }); refresh(); };
    document.getElementById("btn-vision-upload").onclick = async () => {
      const f = document.getElementById("vision-file").files[0];
      if (!f) return alert("Choose a video file first (mp4/avi/mov/mkv/webm).");
      const fd = new FormData();
      fd.append("file", f); fd.append("loop", "true");
      const btn = document.getElementById("btn-vision-upload");
      btn.disabled = true; btn.textContent = "Uploading…";
      try {
        await api("/api/vision/upload", { method: "POST", body: fd });
        startPolling();
      } catch (e) { alert("Upload failed: " + e.message); }
      btn.disabled = false; btn.textContent = "Process Video";
    };
    document.getElementById("btn-vision-bind").onclick = () => bind(document.getElementById("vision-junction").value || null);
    document.getElementById("btn-vision-unbind").onclick = () => { bind(null); document.getElementById("vision-bind-state").textContent = "Unbound — simulation feed restored."; };
    document.getElementById("btn-vision-bind").addEventListener("click", () => {
      setTimeout(() => document.getElementById("vision-bind-state").textContent =
        "Bound to " + document.getElementById("vision-junction").value + " — live video congestion feeding signals + prediction.", 400);
    });
    fetch("/api/meta").then(r => r.json()).then(meta => {
      junctions = Object.entries(meta.junctions);
      document.getElementById("vision-junction").innerHTML =
        junctions.map(([id, j]) => `<option value="${id}">${j.name}</option>`).join("");
    });
  }

  return { init, startPolling, stopPolling, refresh };
})();
