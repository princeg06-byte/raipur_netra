/* RaipurNetra AI - Digital Twin: SVG schematic + Leaflet real-map live mirror */
const MapViz = (() => {
  const NS = "http://www.w3.org/2000/svg";
  let svg, gRoads, gDots, gBuses, gJunctions, gEmergency;
  let roads = {}, junctions = {}, buses = [], emergency = null, dots = [];
  let lastT = 0;
  let mode = "svg";          // "svg" | "map"
  let lmap = null, lLayers = {}, lRoads = {}, lJunctions = {}, lBuses = {}, lEm = null, lInit = false, ltile = null;
  const v = n => (getComputedStyle(document.documentElement).getPropertyValue(n) || "").trim();

  function el(tag, attrs, parent) {
    const e = document.createElementNS(NS, tag);
    for (const k in attrs) e.setAttribute(k, attrs[k]);
    if (parent) parent.appendChild(e);
    return e;
  }

  function init(svgEl) {
    svg = svgEl;
    gEmergency = el("g", {}, svg);
    gRoads = el("g", {}, svg);
    gDots = el("g", {}, svg);
    gBuses = el("g", {}, svg);
    gJunctions = el("g", {}, svg);
    requestAnimationFrame(tick);
  }

  function congColor(c) {
    if (c >= 70) return "#f87171";
    if (c >= 50) return "#fb923c";
    if (c >= 30) return "#facc15";
    return "#4ade80";
  }

  function update(state) {
    roads = state.roads; junctions = state.junctions; buses = state.buses;
    emergency = state.emergency;
    gRoads.innerHTML = ""; gJunctions.innerHTML = ""; gEmergency.innerHTML = "";
    syncDots();

    // emergency route underlay
    if (emergency && emergency.active && emergency.route.length > 1) {
      const pts = emergency.route.map(id => junctions[id]).filter(Boolean);
      if (pts.length > 1) {
        el("polyline", {
          points: pts.map(p => `${p.x},${p.y}`).join(" "),
          fill: "none", stroke: "#f87171", "stroke-width": 10, opacity: .3,
          "stroke-linecap": "round", "stroke-dasharray": "14 8"
        }, gEmergency);
        // ambulance marker along progress
        const pos = pointAlongRoute(pts, emergency.progress || 0);
        const g = el("g", { transform: `translate(${pos.x},${pos.y})` }, gEmergency);
        el("circle", { r: 11, fill: "#f87171", opacity: .35, class: "amb-pulse" }, g);
        el("text", { "text-anchor": "middle", y: 4, "font-size": 12 }, g).textContent = "🚑";
      }
    }

    // roads
    for (const rid in roads) {
      const r = roads[rid];
      const a = junctions[r.a], b = junctions[r.b];
      if (!a || !b) continue;
      const closed = r.closed;
      el("line", {
        x1: a.x, y1: a.y, x2: b.x, y2: b.y,
        stroke: closed ? "#475569" : congColor(r.congestion),
        "stroke-width": closed ? 3 : 2 + (r.speed > 0 ? 3 : 3),
        "stroke-dasharray": closed ? "6 6" : "none",
        opacity: closed ? .5 : .85
      }, gRoads);
      if (closed) {
        const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        el("text", { x: mx, y: my - 6, fill: "#f87171", "font-size": 14, "text-anchor": "middle" }, gRoads).textContent = "✕ closed";
      }
      // road name on longer roads
      if (Math.hypot(b.x - a.x, b.y - a.y) > 90) {
        const mx = (a.x + b.x) / 2, my = (a.y + b.y) / 2;
        const t = el("text", { x: mx, y: my - 5, "text-anchor": "middle", class: "road-label" }, gRoads);
        t.textContent = `${r.name} · ${Math.round(r.congestion)}%`;
      }
    }

    // junctions with signal phase bars
    for (const jid in junctions) {
      const j = junctions[jid], s = j.signal;
      const g = el("g", { transform: `translate(${j.x},${j.y})` }, gJunctions);
      el("circle", { r: 15, fill: v("--map-bg") || "#0a1122", stroke: congColor(j.congestion), "stroke-width": 3.5 }, g);
      // NS bar (vertical) + EW bar (horizontal): green if that axis is green
      const nsGreen = s.phase === "ns", ewGreen = s.phase === "ew";
      el("rect", { x: -2, y: -10, width: 4, height: 20, rx: 1.5, fill: nsGreen ? "#22c55e" : "#7f1d1d" }, g);
      el("rect", { x: -10, y: -2, width: 20, height: 4, rx: 1.5, fill: ewGreen ? "#22c55e" : "#7f1d1d" }, g);
      const lbl = el("text", { x: 0, y: 30, "text-anchor": "middle", class: "junction-label" }, g);
      lbl.textContent = j.name.replace(" Chowk", "").replace(" Crossing", "").replace(" Junction", "").replace(" Square", "");
      const val = el("text", { x: 0, y: 42, "text-anchor": "middle", class: "road-label" }, g);
      val.textContent = `${Math.round(j.congestion)}% · ${s.mode === "adaptive" ? "AI" : "FIX"}`;
    }

    // buses
    gBuses.innerHTML = "";
    buses.forEach(b => {
      const g = el("g", { transform: `translate(${b.x},${b.y})` }, gBuses);
      el("rect", { x: -5, y: -5, width: 10, height: 10, rx: 2, fill: "#facc15", stroke: "#0a1122", "stroke-width": 1.5 }, g);
      el("title", {}, g).textContent = `${b.id} · ${b.route_name} · ETA ${b.eta_min}min · ${b.occupancy} pax`;
    });
  }

  function pointAlongRoute(pts, t) {
    let total = 0;
    const segs = [];
    for (let i = 1; i < pts.length; i++) {
      const d = Math.hypot(pts[i].x - pts[i - 1].x, pts[i].y - pts[i - 1].y);
      segs.push(d); total += d;
    }
    let target = t * total;
    for (let i = 0; i < segs.length; i++) {
      if (target <= segs[i]) {
        const f = segs[i] ? target / segs[i] : 0;
        return { x: pts[i].x + (pts[i + 1].x - pts[i].x) * f, y: pts[i].y + (pts[i + 1].y - pts[i].y) * f };
      }
      target -= segs[i];
    }
    return pts[pts.length - 1];
  }

  // animated vehicle dots along roads
  function syncDots() {
    const wanted = [];
    for (const rid in roads) {
      const r = roads[rid];
      if (r.closed) continue;
      const a = junctions[r.a], b = junctions[r.b];
      if (!a || !b) continue;
      const n = Math.max(1, Math.min(7, Math.round(r.congestion / 12)));
      for (let i = 0; i < n; i++) wanted.push({ rid, a, b, i, n, cong: r.congestion, speed: r.speed });
    }
    // rebuild only when the fleet shape changes
    const key = wanted.map(w => `${w.rid}:${w.i}`).join("|");
    if (key !== syncDots._key) {
      gDots.innerHTML = "";
      dots = wanted.map(w => {
        const c = el("circle", { r: 3, fill: v("--map-dot") || "#93c5fd", opacity: .9 }, gDots);
        return { ...w, el: c, phase: Math.random(), dir: w.i % 2 === 0 ? 1 : -1 };
      });
      syncDots._key = key;
    } else {
      dots.forEach((d, idx) => { if (wanted[idx]) { d.cong = wanted[idx].cong; d.speed = wanted[idx].speed; } });
    }
  }

  function tick(ms) {
    const dt = Math.min(0.1, (ms - lastT) / 1000 || 0.016);
    lastT = ms;
    dots.forEach(d => {
      d.phase += d.dir * (d.speed / 3.6) * dt / 40;   // schematic px travel
      if (d.phase > 1) d.phase -= 1;
      if (d.phase < 0) d.phase += 1;
      const x = d.a.x + (d.b.x - d.a.x) * d.phase;
      const y = d.a.y + (d.b.y - d.a.y) * d.phase;
      d.el.setAttribute("cx", x); d.el.setAttribute("cy", y);
      d.el.setAttribute("fill", d.cong >= 70 ? "#fca5a5" : d.cong >= 50 ? "#fdba74" : (v("--map-dot") || "#93c5fd"));
    });
    requestAnimationFrame(tick);
  }

  /* ================= Leaflet real-map mode ================= */
  let lmeta = { url: null, attr: null };

  function initLeaflet(containerId, tileUrl, tileAttr) {
    // store config; actual L.map creation happens on first visible switch
    lmeta = { url: tileUrl, attr: tileAttr, container: containerId };
  }

  function ensureLeaflet() {
    if (lInit || typeof L === "undefined") return;
    // preferCanvas: faster with many vector layers and avoids headless-SVG
    // compositing quirks; falls back gracefully in every browser.
    lmap = L.map(lmeta.container, { center: [21.2480, 81.6480], zoom: 14,
                                    zoomControl: true, attributionControl: true,
                                    preferCanvas: true });
    L.tileLayer(lmeta.url || "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}", {
      attribution: lmeta.attr || "Tiles &copy; Esri", maxZoom: 19
    }).addTo(lmap);
    lLayers.roads = L.layerGroup().addTo(lmap);
    lLayers.junctions = L.layerGroup().addTo(lmap);
    lLayers.buses = L.layerGroup().addTo(lmap);
    lLayers.em = L.layerGroup().addTo(lmap);
    lLayers.parking = L.layerGroup().addTo(lmap);
    // frame all Raipur junctions on first open
    lmap.fitBounds(L.latLngBounds([[21.2130, 81.6060], [21.2920, 81.6960]]),
                   { padding: [20, 20] });
    lInit = true;
    setTimeout(() => lmap.invalidateSize(), 250);
  }

  function setMode(m) {
    mode = m;
    // Rebuild the Leaflet map fresh on every switch to map mode. Creating it
    // inside a hidden/zero-size container leaves stale pixel origins that
    // misplace vector layers; a clean rebuild after the container is visible
    // avoids the whole class of sizing bugs.
    if (m === "map") {
      if (lmap) {
        try { lmap.remove(); } catch (e) { /* already gone */ }
        lmap = null; lInit = false;
        lRoads = {}; lJunctions = {}; lBuses = {};
        lLayers = {};
      }
      setTimeout(() => { ensureLeaflet(); }, 60);  // after display:block applies
    }
  }

  function updateLeaflet(state) {
    if (!lInit || mode !== "map") return;
    // roads
    const seen = new Set();
    for (const rid in state.roads) {
      const r = state.roads[rid];
      const a = state.junctions[r.a], b = state.junctions[r.b];
      if (!a || !b) continue;
      const key = `${r.a}|${r.b}`;
      seen.add(key);
      const color = r.closed ? "#475569" : congColor(r.congestion);
      let line = lRoads[rid];
      if (!line) {
        line = L.polyline([[a.lat, a.lng], [b.lat, b.lng]], { weight: 6, opacity: .85 });
        line.bindTooltip(`${r.name} · ${Math.round(r.congestion)}%`, { sticky: true });
        line.addTo(lLayers.roads);
        lRoads[rid] = line;
      }
      line.setStyle({ color, weight: r.closed ? 3 : 6, dashArray: r.closed ? "6 6" : null });
      line.setTooltipContent(`${r.name} · ${Math.round(r.congestion)}%${r.closed ? " (CLOSED)" : ""}`);
    }
    // junctions
    for (const jid in state.junctions) {
      const j = state.junctions[jid];
      let marker = lJunctions[jid];
      const color = congColor(j.congestion);
      if (!marker) {
        marker = L.circleMarker([j.lat, j.lng], { radius: 10, color: v("--map-node") || "#0a1122", weight: 2, fillOpacity: .95 });
        marker.bindTooltip(j.name, { permanent: true, direction: "bottom",
                                     offset: [0, 8], className: "jlabel", opacity: .95 });
        marker.bindPopup(
          `<b>${j.name}</b><br>Congestion: <b>${j.congestion}%</b><br>` +
          `Signal: ${j.signal.phase.toUpperCase()} green (${j.signal.mode === "adaptive" ? "AI" : "FIXED"})<br>` +
          `Green: ${Math.round(j.signal.green_time)}s · Wait: ${j.signal.avg_wait_adaptive}s<br>` +
          `<i>${j.note}</i>`);
        marker.addTo(lLayers.junctions);
        lJunctions[jid] = marker;
      }
      marker.setStyle({ fillColor: color, color: v("--map-node") || "#0a1122" });
    }
    // buses
    const busIds = new Set();
    state.buses.forEach(b => {
      busIds.add(b.id);
      let m = lBuses[b.id];
      if (!m) {
        m = L.marker([b.lat, b.lng], {
          icon: L.divIcon({ className: "", html: `<div style="width:14px;height:14px;background:#facc15;border:2px solid #0a1122;border-radius:3px"></div>`, iconSize: [14, 14] })
        }).addTo(lLayers.buses);
        m.bindTooltip(`${b.id} · ${b.route_name}`);
        lBuses[b.id] = m;
      }
      m.setLatLng([b.lat, b.lng]);
      m.setTooltipContent(`${b.id} · ${b.route_name} · ETA ${b.eta_min}min · ${b.occupancy} pax`);
    });
    for (const bid in lBuses) {
      if (!busIds.has(bid)) { lLayers.buses.removeLayer(lBuses[bid]); delete lBuses[bid]; }
    }
    // parking
    lLayers.parking.clearLayers();
    for (const pid in state.parking) {
      const p = state.parking[pid];
      const col = p.pct > 90 ? "#f87171" : p.pct > 70 ? "#fb923c" : "#4ade80";
      L.circleMarker([p.lat, p.lng], { radius: 6, color: col, fillColor: col, fillOpacity: .8 })
        .bindTooltip(`${p.name}: ${p.free}/${p.total} free`)
        .addTo(lLayers.parking);
    }
    // emergency route
    lLayers.em.clearLayers(); lEm = null;
    const em = state.emergency;
    if (em && em.active && em.route.length > 1) {
      const pts = em.route.map(id => state.junctions[id]).filter(Boolean).map(j => [j.lat, j.lng]);
      if (pts.length > 1) {
        L.polyline(pts, { color: "#f87171", weight: 8, opacity: .4, dashArray: "10 8" }).addTo(lLayers.em);
        L.marker(pts[Math.min(pts.length - 1, Math.floor((em.progress || 0) * pts.length))], {
          icon: L.divIcon({ html: `<div style="font-size:20px">🚑</div>`, iconSize: [22, 22] })
        }).addTo(lLayers.em);
      }
    }
  }

  function applyTheme(theme) {
    // swap base tiles (dark canvas vs light canvas) when the UI theme changes
    if (lInit && ltile) {
      const url = theme === "dark"
        ? "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Dark_Gray_Base/MapServer/tile/{z}/{y}/{x}"
        : "https://server.arcgisonline.com/ArcGIS/rest/services/Canvas/World_Light_Gray_Base/MapServer/tile/{z}/{y}/{x}";
      ltile.setUrl(url);
    }
  }

  return { init, update, initLeaflet, setMode, updateLeaflet, applyTheme,
           _leafletReady: () => lInit,
           _map: () => lmap,
           _dbg: () => ({ mode, lInit, roads: Object.keys(lRoads).length,
                          junctions: Object.keys(lJunctions).length,
                          buses: Object.keys(lBuses).length,
                          hasState: !!roads && Object.keys(roads).length,
                          mapSize: lmap ? [lmap.getSize().x, lmap.getSize().y] : null,
                          renderers: lmap ? Object.keys(lmap._layers).filter(k => lmap._layers[k] instanceof L.Renderer).length : 0 }) };
})();
