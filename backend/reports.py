"""RaipurNetra AI - analytics aggregation + auto report generation (bonus feature)."""

import datetime
import os

from . import config


def build_analytics(sim, anpr_engine, predictor, bus_punctuality=None):
    snap = sim.snapshot()
    an = anpr_engine.snapshot()
    preds = predictor.predict_all()["predictions"]
    hist = sim.history_tail(minutes=180)

    waits = [j["signal"]["avg_wait_adaptive"] for j in snap["junctions"].values()]
    fixed_waits = [j["signal"]["avg_wait_fixed"] for j in snap["junctions"].values()]

    if bus_punctuality is None:
        delays = [abs(b["delay_min"]) for b in snap["buses"]]
        bus_punctuality = round(100 - min(60, sum(delays) / max(1, len(delays)) * 8), 1)

    impact = [
        {"metric": "Avg. Wait at Signal", "current": f"{sum(fixed_waits)/max(1,len(fixed_waits)):.0f} sec (fixed)",
         "after": f"{sum(waits)/max(1,len(waits)):.0f} sec (adaptive)", "improvement": f"{snap['kpis']['wait_reduction_pct']:.0f}% reduction"},
        {"metric": "Emergency Response", "current": "25-30 min", "after": "15-20 min", "improvement": "40% faster"},
        {"metric": "Violation Detection", "current": "5-10% (manual)", "after": "85%+ (automated)", "improvement": "85% detection rate"},
        {"metric": "Congestion Prediction", "current": "None (reactive only)", "after": "30-min advance warning", "improvement": "80% accuracy"},
        {"metric": "Parking Search Time", "current": "15-20 min", "after": "5-8 min", "improvement": "60% reduction"},
        {"metric": "Bus Schedule Adherence", "current": "40-50%", "after": "70-80%", "improvement": "50% improvement"},
        {"metric": "Fuel Waste (idling)", "current": "High (fixed signals)", "after": "Reduced (adaptive)", "improvement": "20% savings"},
        {"metric": "Road Accidents", "current": "Current rate", "after": "Reduced (warnings + enforcement)", "improvement": "25% reduction"},
    ]

    return {
        "kpis": snap["kpis"],
        "congestion_series": [{"t": h["t"], "city": h["city"]} for h in hist],
        "junction_congestion_now": {jid: j["congestion"] for jid, j in snap["junctions"].items()},
        "prediction_risk_counts": {
            "high": sum(1 for p in preds.values() if p["risk"] == "high"),
            "medium": sum(1 for p in preds.values() if p["risk"] == "medium"),
            "low": sum(1 for p in preds.values() if p["risk"] == "low"),
        },
        "violations": {
            "counters": an["counters"],
            "revenue": an["revenue"],
            "heatmap_total": an["heatmap_total"],
            "hotspot": config.JUNCTIONS[an["hotspot"]]["name"] if an["hotspot"] else None,
            "by_type": {},
        },
        "bus": {"active": len(snap["buses"]), "punctuality_pct": bus_punctuality},
        "parking": snap["parking"],
        "impact_table": impact,
        "cost_model": {
            "one_time_total": 425000, "monthly_operating": 13000,
            "monthly_revenue_projected": an["revenue_monthly_projected"],
            "roi": "Entire Rs. 4.25 lakh investment recovered within the FIRST WEEK of operation",
        },
    }


def generate_daily_report(sim, anpr_engine, predictor, out_dir="reports"):
    """Auto-generates the daily PDF-style HTML report for police administration."""
    os.makedirs(out_dir, exist_ok=True)
    a = build_analytics(sim, anpr_engine, predictor)
    now = datetime.datetime.now(config.IST)
    rows = "".join(
        f"<tr><td>{r['metric']}</td><td>{r['current']}</td><td>{r['after']}</td>"
        f"<td class='imp'>{r['improvement']}</td></tr>"
        for r in a["impact_table"])
    hotspot_rows = "".join(
        f"<tr><td>{config.JUNCTIONS[jid]['name']}</td><td>{total}</td></tr>"
        for jid, total in sorted(a["violations"]["heatmap_total"].items(), key=lambda kv: -kv[1])[:6])
    html = f"""<!DOCTYPE html><html><head><meta charset="utf-8">
<title>RaipurNetra AI - Daily Report</title><style>
body{{font-family:Segoe UI,Arial;background:#0f172a;color:#e2e8f0;margin:40px}}
h1{{color:#38bdf8}} table{{border-collapse:collapse;width:100%;margin:18px 0}}
td,th{{border:1px solid #334155;padding:8px 12px;text-align:left}}
th{{background:#1e293b}} .imp{{color:#4ade80;font-weight:600}}
.badge{{background:#1d4ed8;padding:2px 10px;border-radius:12px;font-size:12px}}
</style></head><body>
<h1>RaipurNetra AI — Daily Traffic Report</h1>
<p><span class="badge">{now.strftime('%d %b %Y, %I:%M %p')} IST</span>
<span class="badge">Raipur Police Commissionerate</span></p>
<h2>City KPIs</h2><ul>
<li>City congestion: <b>{a['kpis']['city_congestion']:.0f}%</b> (weather: {a['kpis']['weather']})</li>
<li>Avg signal wait: <b>{a['kpis']['avg_wait_adaptive']:.0f}s</b> adaptive vs {a['kpis']['avg_wait_fixed']:.0f}s fixed ({a['kpis']['wait_reduction_pct']:.0f}% saved)</li>
<li>Vehicles analysed today: <b>{a['kpis']['vehicles_today']:,}</b> across {a['kpis']['cameras_online']} cameras</li>
<li>Buses active: {a['bus']['active']} | punctuality {a['bus']['punctuality_pct']:.0f}%</li>
</ul>
<h2>Enforcement</h2><ul>
<li>Violations detected: <b>{a['violations']['counters']['violations']}</b> — e-challans issued: <b>{a['violations']['counters']['challans']}</b></li>
<li>Revenue generated: <b>Rs. {a['violations']['revenue']['generated']:,}</b> (collected: Rs. {a['violations']['revenue']['collected']:,})</li>
<li>Hotspot: <b>{a['violations']['hotspot'] or '-'}</b></li>
</ul>
<h3>Top violation junctions</h3><table><tr><th>Junction</th><th>Violations</th></tr>{hotspot_rows}</table>
<h2>Impact Summary (proposal targets)</h2><table><tr><th>Metric</th><th>Current</th><th>After RaipurNetra AI</th><th>Improvement</th></tr>{rows}</table>
<p>Generated automatically by RaipurNetra AI Intelligence Layer. <i>Raipur Traffic Hackathon 2026 — Team: {', '.join(config.TEAM)}</i></p>
</body></html>"""
    fname = f"daily_report_{now.strftime('%Y%m%d_%H%M')}.html"
    path = os.path.join(out_dir, fname)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return {"path": path, "file": fname}
