"""RaipurNetra AI - FastAPI application.

Serves the command-center dashboard (frontend/) and the full REST API:
live state, predictions, ANPR/e-challans, buses, parking, ride matching,
TrafficGPT bot, emergency corridor, what-if simulation and reports.
"""

import threading
import time
import os
import logging
import datetime

from fastapi import FastAPI, HTTPException, UploadFile, File, Form, Request, Response
from fastapi.responses import FileResponse, PlainTextResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import config
from . import settings
from .simulator import simulator
from .anpr import anpr
from . import predictor as predictor_module
from .bot import TrafficGPT
from .ridematch import ride_matcher
from . import reports
from .vision import VideoDetectionEngine
from .whatsapp import attach as whatsapp_attach

logging.basicConfig(level=getattr(logging, settings.LOG_LEVEL, logging.INFO),
                    format="%(asctime)s %(name)s %(levelname)s %(message)s")
log = logging.getLogger("raipurnetra")

app = FastAPI(title="RaipurNetra AI", version="2.0.0",
              description="AI-Powered Intelligent Traffic Management System for Raipur Police Commissionerate")

# ---------------------------------------------------------------------------
# Wiring
# ---------------------------------------------------------------------------
simulator.set_anpr_hook(anpr.on_vehicles)
predictor = predictor_module.CongestionPredictor(simulator)  # trains in background at startup
bot = TrafficGPT(simulator, predictor, anpr)
video_engine = VideoDetectionEngine(anpr, simulator)
whatsapp = whatsapp_attach(bot)

_start_wall = time.time()


def _retrain_loop():
    while True:
        time.sleep(settings.PREDICT_RETRAIN_INTERVAL_MIN * 60)
        try:
            predictor.train()
            log.info("predictor retrained on live data")
        except Exception as exc:
            log.warning(f"retrain failed: {exc!r}")


@app.on_event("startup")
def startup():
    simulator.start()
    threading.Thread(target=_initial_train, daemon=True, name="initial-train").start()
    threading.Thread(target=_retrain_loop, daemon=True, name="retrain").start()
    log.info("RaipurNetra AI started — dashboard at http://localhost:%s", settings.PORT)


def _initial_train():
    try:
        predictor.train()
        log.info("predictor trained on %s history samples", predictor.training_samples)
    except Exception as exc:
        log.warning(f"initial training failed: {exc!r}")


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------
class BotMessage(BaseModel):
    message: str
    user: str = "citizen"


class WhatIf(BaseModel):
    action: str                      # close_road | open_road | weather | event | signal_mode | reset
    road: str | None = None
    value: str | None = None
    junction: str | None = None


class EmergencyRequest(BaseModel):
    activate: bool
    route: list[str] = ["jaistambh", "telibandha", "marine"]
    vehicle: str = "Ambulance CG-04-EM-101"


class SignalMode(BaseModel):
    mode: str                        # fixed | adaptive


class RideRegistration(BaseModel):
    name: str = "WhatsApp user"
    contact: str = "wa-user"
    origin: str = "jaistambh"
    destination: str = "telibandha"
    time_pref: str = "09:00"
    gender_pref: str = "any"


class PlateLookup(BaseModel):
    plate: str
    junction: str = "jaistambh"


# ---------------------------------------------------------------------------
# API routes
# ---------------------------------------------------------------------------
@app.get("/api/meta")
def meta():
    return {"team": config.TEAM, "event": config.EVENT_META,
            "junctions": {jid: {"name": jd["name"], "note": jd["note"],
                                "lat": jd["lat"], "lng": jd["lng"]}
                          for jid, jd in config.JUNCTIONS.items()},
            "roads": {rid: {"name": rd[2]} for rid, rd in config.ROADS.items()},
            "routes": config.BUS_ROUTES,
            "tile_url": settings.TILE_URL,
            "tile_attr": settings.TILE_ATTR}


@app.get("/api/state")
def state():
    return simulator.snapshot()


@app.get("/api/history")
def history(minutes: int = 180):
    return {"series": simulator.history_tail(minutes=minutes)}


@app.get("/api/predictions")
def predictions():
    return predictor.predict_all()


@app.post("/api/predictions/retrain")
def retrain():
    ok = predictor.train()
    return {"retrained": ok, "metrics": predictor.metrics, "trained_at": predictor.trained_at}


@app.post("/api/whatif")
def whatif(req: WhatIf):
    if req.action == "close_road" and req.road:
        if req.road not in simulator.roads:
            raise HTTPException(404, "unknown road")
        simulator.set_road_closed(req.road, True)
    elif req.action == "open_road" and req.road:
        simulator.set_road_closed(req.road, False)
    elif req.action == "weather":
        simulator.set_weather(req.value or "clear")
    elif req.action == "event":
        simulator.set_event((req.value or "on") == "on")
    elif req.action == "signal_mode" and req.junction:
        simulator.set_signal_override(req.junction, req.value)
    elif req.action == "reset":
        for rid in list(simulator.closed_roads):
            simulator.set_road_closed(rid, False)
        simulator.set_weather("clear")
        simulator.set_event(False)
        for jid in list(simulator.signal_overrides):
            simulator.set_signal_override(jid, None)
    else:
        raise HTTPException(400, "invalid action")
    return {"ok": True, "state": simulator.snapshot()["kpis"]}


@app.get("/api/whatif/impact")
def whatif_impact():
    """Prediction delta vs clear baseline (no closures, clear weather, no event)."""
    return predictor.whatif_impact(None)


@app.get("/api/violations")
def violations(limit: int = 80):
    return anpr.snapshot(limit=limit)


@app.post("/api/violations/burst")
def violations_burst(junction: str | None = None, n: int = 10):
    return {"generated": anpr.simulate_burst(n=n, junction_id=junction)}


@app.post("/api/anpr/lookup")
def anpr_lookup(req: PlateLookup):
    return anpr.process_plate_text(req.plate, req.junction)


@app.get("/api/buses")
def buses():
    return {"buses": simulator.snapshot()["buses"], "routes": config.BUS_ROUTES}


@app.get("/api/parking")
def parking():
    return {"lots": simulator.snapshot()["parking"]}


@app.get("/api/rides")
def rides():
    return ride_matcher.snapshot()


@app.post("/api/rides/register")
def rides_register(req: RideRegistration):
    rec = ride_matcher.register(req.name, req.contact, req.origin, req.destination,
                                req.time_pref, req.gender_pref)
    return {"registered": rec, "matches": ride_matcher.matches_for(rec["id"])}


@app.get("/api/rides/matches/{commuter_id}")
def rides_matches(commuter_id: str):
    return {"matches": ride_matcher.matches_for(commuter_id)}


@app.post("/api/bot")
def bot_endpoint(req: BotMessage):
    return bot.handle(req.message, req.user)


@app.get("/api/emergency")
def emergency_status():
    return simulator.signal_net.snapshot()


@app.post("/api/emergency")
def emergency_trigger(req: EmergencyRequest):
    if req.activate:
        route = [j for j in req.route if j in config.JUNCTIONS]
        if len(route) < 2:
            raise HTTPException(400, "route needs >= 2 valid junctions")
        simulator.signal_net.activate_emergency(route, req.vehicle)
        return {"activated": True, "route": route, "corridor": "GREEN WAVE ACTIVE"}
    saved = simulator.signal_net.deactivate_emergency()
    return {"activated": False, "time_saved_est_min": saved}


@app.get("/api/signals")
def signals():
    snap = simulator.snapshot()
    return {"signals": {jid: j["signal"] for jid, j in snap["junctions"].items()}}


@app.post("/api/signals/{junction_id}/mode")
def signal_mode(junction_id: str, req: SignalMode):
    if junction_id not in config.JUNCTIONS:
        raise HTTPException(404, "unknown junction")
    if req.mode not in ("fixed", "adaptive"):
        raise HTTPException(400, "mode must be fixed|adaptive")
    simulator.set_signal_override(junction_id, None if req.mode == "adaptive" else req.mode)
    return {"ok": True, "junction": junction_id, "mode": req.mode}


@app.get("/api/analytics")
def analytics():
    return reports.build_analytics(simulator, anpr, predictor)


@app.post("/api/report/daily")
def daily_report():
    return reports.generate_daily_report(simulator, anpr, predictor)


@app.get("/api/report/view")
def report_view(file: str):
    """Serve a generated report file (whitelisted name pattern only)."""
    import re as _re
    if not _re.match(r"^daily_report_\d{8}_\d{4}\.html$", file):
        raise HTTPException(400, "invalid report name")
    path = os.path.join("reports", file)
    if not os.path.isfile(path):
        raise HTTPException(404, "report not found")
    return FileResponse(path, media_type="text/html")


@app.get("/api/health")
def health():
    return {"status": "ok", "uptime_s": round(time.time() - _start_wall),
            "model": predictor.trained_at, "time": datetime.datetime.now(config.IST).isoformat(timespec="seconds")}


# ---------------------------------------------------------------------------
# Vision: saved-video detection (Layer 1 - SEE)
# ---------------------------------------------------------------------------
class VisionBind(BaseModel):
    junction: str | None = None


@app.post("/api/vision/upload")
async def vision_upload(file: UploadFile = File(...), loop: str = Form("true")):
    if not file.filename.lower().endswith((".mp4", ".avi", ".mov", ".mkv", ".webm")):
        raise HTTPException(400, "video file required (mp4/avi/mov/mkv/webm)")
    data = await file.read()
    if len(data) > settings.VISION_MAX_UPLOAD_MB * 1024 * 1024:
        raise HTTPException(413, f"file exceeds {settings.VISION_MAX_UPLOAD_MB} MB limit")
    path = settings.UPLOADS_DIR / f"upload_{int(time.time())}_{file.filename}"
    path.write_bytes(data)
    video_engine.ingest(path, file.filename, loop=(loop == "true"))
    return {"ingested": True, "file": file.filename, "size_mb": round(len(data) / 1e6, 1)}


@app.post("/api/vision/sample")
def vision_sample():
    sample = settings.DATA_DIR / "sample_traffic_clip.mp4"
    if not sample.exists():
        raise HTTPException(404, "sample clip not found in data/")
    video_engine.ingest(sample, "sample_traffic_clip.mp4", loop=True)
    return {"ingested": True, "file": sample.name}


@app.get("/api/vision/status")
def vision_status():
    return video_engine.snapshot()


@app.get("/api/vision/frame")
def vision_frame():
    jpeg = video_engine.latest_frame()
    if not jpeg:
        return Response(status_code=204)
    return Response(content=jpeg, media_type="image/jpeg")


@app.post("/api/vision/bind")
def vision_bind(req: VisionBind):
    try:
        video_engine.bind_junction(req.junction)
    except ValueError:
        raise HTTPException(404, "unknown junction")
    return {"ok": True, "bound_junction": req.junction}


@app.post("/api/vision/stop")
def vision_stop():
    video_engine.stop()
    return {"ok": True}


# ---------------------------------------------------------------------------
# WhatsApp Cloud API gateway (Layer 4 - TELL)
# ---------------------------------------------------------------------------
@app.get("/api/whatsapp/webhook")
def wa_verify(request: Request):
    mode = request.query_params.get("hub.mode")
    token = request.query_params.get("hub.verify_token")
    challenge = request.query_params.get("hub.challenge", "")
    result = whatsapp.verify(mode, token, challenge)
    if result:
        return PlainTextResponse(str(result))
    raise HTTPException(403, "verification failed")


@app.post("/api/whatsapp/webhook")
async def wa_receive(request: Request):
    payload = await request.json()
    replies = whatsapp.receive(payload)
    return {"received": len(replies), "replies": [{"to": t, "text": r} for t, _, r in replies]}


class WASimulate(BaseModel):
    sender: str = "9198xxxxxxxx"
    text: str


@app.post("/api/whatsapp/simulate")
def wa_simulate(req: WASimulate):
    reply = whatsapp.simulate(req.sender, req.text)
    return {"reply": reply}


@app.get("/api/whatsapp/status")
def wa_status():
    return whatsapp.snapshot()


# ---------------------------------------------------------------------------
# Frontend (mounted last so /api takes precedence)
# ---------------------------------------------------------------------------
frontend_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "frontend")
if os.path.isdir(frontend_dir):
    app.mount("/", StaticFiles(directory=frontend_dir, html=True), name="frontend")
