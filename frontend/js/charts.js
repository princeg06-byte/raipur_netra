/* RaipurNetra AI - canvas line charts: auto-scaled, DPR-aware, offline-safe */
const Charts = (() => {
  function niceStep(range, ticks) {
    const raw = range / ticks;
    const mag = Math.pow(10, Math.floor(Math.log10(raw)));
    for (const m of [1, 2, 2.5, 5, 10]) {
      if (raw <= m * mag) return m * mag;
    }
    return 10 * mag;
  }

  function line(canvas, series, opts = {}) {
    if (!canvas) return;
    const cssv = getComputedStyle(document.documentElement);
    const vc = (n, f) => (cssv.getPropertyValue(n) || "").trim() || f;
    const BG = opts.bg || vc("--chart-bg", "#0d1830");
    const GRID = vc("--chart-grid", "#22334f");
    const LABEL = vc("--chart-label", "#7d92b5");
    let ctx = null;
    try { ctx = canvas.getContext("2d"); } catch (e) { ctx = null; }
    if (!ctx) return;

    // element CSS size drives the bitmap (never a stale attribute size)
    const cssW = Math.max(200, canvas.clientWidth || canvas.width || 640);
    const cssH = Math.max(140, canvas.clientHeight || canvas.height || 240);
    const dpr = window.devicePixelRatio || 1;
    canvas.width = Math.round(cssW * dpr);
    canvas.height = Math.round(cssH * dpr);
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

    // opaque background — never renders blank/white in any browser
    ctx.fillStyle = BG;
    ctx.fillRect(0, 0, cssW, cssH);

    const all = series.flatMap(s => s.data.map(p => p.v)).filter(v => isFinite(v));
    const pad = { l: 44, r: 14, t: 30, b: 26 };
    const W = cssW, H = cssH;

    if (!all.length) {
      ctx.fillStyle = LABEL;
      ctx.font = "13px Segoe UI";
      ctx.textAlign = "center";
      ctx.fillText("waiting for data…", W / 2, H / 2);
      ctx.textAlign = "left";
      return;
    }

    // auto-scale y to the data (with headroom), falling back to sane floors
    let min = opts.min !== undefined ? opts.min : Math.min(...all);
    let max = opts.max !== undefined ? opts.max : Math.max(...all);
    if (opts.autoScale !== false) {
      const span = Math.max(8, max - min);
      min = Math.max(opts.floor !== undefined ? opts.floor : 0, min - span * 0.15);
      max = max + span * 0.18;
    }
    if (max - min < 6) max = min + 6;
    const n = Math.max(...series.map(s => s.data.length));
    const X = i => pad.l + (W - pad.l - pad.r) * (n <= 1 ? 0 : i / (n - 1));
    const Y = v => pad.t + (H - pad.t - pad.b) * (1 - (v - min) / (max - min));

    // gridlines + readable tick labels
    const step = niceStep(max - min, 5);
    ctx.font = "11px Segoe UI";
    ctx.lineWidth = 1;
    for (let v = Math.ceil(min / step) * step; v <= max + 1e-9; v += step) {
      const y = Y(v);
      ctx.strokeStyle = GRID;
      ctx.beginPath(); ctx.moveTo(pad.l, y); ctx.lineTo(W - pad.r, y); ctx.stroke();
      ctx.fillStyle = LABEL;
      ctx.fillText(String(Math.round(v)), 6, y + 3.5);
    }
    ctx.textAlign = "left";

    // time labels along x
    const s0 = series.find(s => s.data.length);
    if (s0 && opts.timeLabels !== false) {
      const picks = [0, Math.floor(n / 2), n - 1];
      picks.forEach(i => {
        const p = s0.data[i];
        if (p && p.t) {
          const t = p.t.length >= 16 ? p.t.slice(11, 16) : p.t;
          ctx.fillStyle = LABEL;
          ctx.textAlign = i === 0 ? "left" : i === n - 1 ? "right" : "center";
          ctx.fillText(t, Math.min(W - 26, Math.max(pad.l, X(i))), H - 8);
        }
      });
      ctx.textAlign = "left";
    }

    // lines (+ optional fill)
    series.forEach(s => {
      if (!s.data.length) return;
      ctx.strokeStyle = s.color || "#38bdf8";
      const dash = Array.isArray(s.dash) ? s.dash
        : (typeof s.dash === "string" && s.dash ? s.dash.split(/\s+/).map(Number) : []);
      ctx.setLineDash(dash);
      ctx.lineWidth = s.width || 2.2;
      ctx.beginPath();
      s.data.forEach((p, i) => {
        const x = X(i), y = Y(p.v);
        i ? ctx.lineTo(x, y) : ctx.moveTo(x, y);
      });
      ctx.stroke();
      ctx.setLineDash([]);
      if (s.fill) {
        ctx.globalAlpha = .14;
        ctx.lineTo(X(s.data.length - 1), Y(min)); ctx.lineTo(X(0), Y(min)); ctx.closePath();
        ctx.fillStyle = s.color || "#38bdf8"; ctx.fill();
        ctx.globalAlpha = 1;
      }
      // endpoint marker + value tag
      const last = s.data[s.data.length - 1];
      if (last && s.marker !== false && s.data.length > 1) {
        const x = X(s.data.length - 1), y = Y(last.v);
        ctx.fillStyle = s.color || "#38bdf8";
        ctx.beginPath(); ctx.arc(x, y, 3.5, 0, Math.PI * 2); ctx.fill();
        const label = (last.t === null || last.v === undefined) ? "" : Math.round(last.v) + "%";
        if (label) {
          ctx.font = "bold 11px Segoe UI";
          const tw = ctx.measureText(label).width;
          const lx = Math.min(W - tw - 8, x + 8);
          ctx.fillStyle = "rgba(10,17,34,.85)";
          ctx.fillRect(lx - 4, y - 17, tw + 8, 15);
          ctx.fillStyle = s.color || "#38bdf8";
          ctx.fillText(label, lx, y - 6);
          ctx.font = "11px Segoe UI";
        }
      }
    });

    // legend
    if (series.length > 1 && opts.legend !== false) {
      ctx.font = "11px Segoe UI";
      let lx = pad.l + 4;
      series.forEach(s => {
        ctx.fillStyle = s.color || "#38bdf8";
        ctx.fillRect(lx, 8, 12, 4);
        ctx.fillStyle = vc('--text', '#b9c8e0');
        ctx.fillText(s.label || "", lx + 17, 13);
        lx += 26 + (s.label ? s.label.length * 6.2 : 0) + 14;
      });
    }
  }
  return { line };
})();
