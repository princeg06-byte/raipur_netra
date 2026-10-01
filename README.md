# RaipurNetra AI — "The Intelligent Eye of Raipur"

AI-Powered Intelligent Traffic Management System for the **Raipur Police Commissionerate**
Built for **Raipur Traffic Hackathon 2026** — Theme: *Infusion of AI/IoT in Traffic Management*

RaipurNetra AI turns Raipur's existing 500+ CCTV cameras into an intelligent traffic network by
adding an AI brain layer on top — **zero new camera or sensor hardware**.

> **Industry-ready working prototype** — real YOLOv8 computer vision on uploaded video,
> ML congestion prediction with persisted models, a live Leaflet digital twin of real
> Raipur coordinates, a WhatsApp Cloud API gateway, adaptive signals, e-challans and
> TrafficGPT (Hindi/English). Deployable via Docker/VM — see `docs/DEPLOYMENT.md`.

---

## Quick Start

```bash
pip install -r requirements.txt
run.bat                # double-click on Windows
# or: python -m uvicorn backend.main:app --host 0.0.0.0 --port 8000
```

Open **http://localhost:8000**. Docker: `docker compose up --build`.

---

## What's New in v2

| Capability | Where |
|---|---|
| 🗺️ **Real-map digital twin** — Leaflet + CARTO dark tiles, real Raipur GPS coordinates, live congestion polylines, junction popups, moving buses, parking pins, emergency route | Digital Twin → "Real Map" toggle |
| 🎥 **Saved-video detection** — upload any traffic video; auto-selects the fine-tuned Raipur YOLOv8 → COCO → OpenCV MOG2 tracking pipeline; counts, classifies, tracks speeds, detects stop-line crossings, reads rendered plates; **binds a junction to real footage** | "Video Detection" tab |
| 🧠 **Upgraded predictor** — lag features, upstream-network congestion, calendar-known future demand, weather/event/closure inputs; 30+60-min horizons; MAE/RMSE/R²/hit-rate validation; models persisted (joblib) + retrain API + training history | "Prediction" tab |
| 💬 **WhatsApp integration** — Meta Cloud API webhook (verify + receive + Graph-API send), outbox fallback, and a WhatsApp-Web-style simulator page exercising the identical production pipeline | "TrafficGPT" tab → simulator |
| 🚀 **Deployability** — Dockerfile + compose, .env config surface (`backend/settings.py`), systemd+nginx guide, scaling notes, extensibility guide | `docs/` |

---

## The 5-Layer Architecture

```
┌────────────────────────────────────────────────────────────────┐
│  LAYER 5 · ACT      Adaptive Signals · Bus Priority ·           │
│                     Emergency Green Corridor   (signals.py)     │
├────────────────────────────────────────────────────────────────┤
│  LAYER 4 · TELL     WhatsApp Bot (Hindi) · Bus Tracker ·        │
│                     Parking · Ride Matching    (bot.py, whatsapp.py) │
├────────────────────────────────────────────────────────────────┤
│  LAYER 3 · MIRROR   Digital Twin (SVG + Leaflet real map) ·     │
│                     What-If Simulation         (frontend)       │
├────────────────────────────────────────────────────────────────┤
│  LAYER 2 · THINK    TrafficGPT · GBM Congestion Predictor ·     │
│                     Auto Reports               (predictor.py)   │
├────────────────────────────────────────────────────────────────┤
│  LAYER 1 · SEE      YOLOv8 CV on video/RTSP · ANPR · Violation  │
│                     Detection · Density Count  (vision.py, anpr.py) │
└────────────────────────────────────────────────────────────────┘
```

**Data flow:** CCTV (RTSP) → YOLOv8 detection → per-lane density → Intelligence (predict +
TrafficGPT) → Digital Twin mirror → Actions (adaptive signals, e-challans, WhatsApp alerts).

---

## Feature → Requirement Coverage (all 8 + 2 bonus)

| # | Hackathon Requirement | Where in this prototype |
|---|----------------------|------------------------|
| 1 | AI-Based Adaptive Traffic Signals | **Signals tab** — green-time optimization per lane density, green waves, fixed-vs-adaptive comparison |
| 2 | ANPR + automatic violation detection | **ANPR tab** + **Video Detection** — plate recognition, red-light/no-helmet/wrong-way/speed violations, auto e-challan with evidence |
| 3 | Pre-trip & en-route information | **TrafficGPT bot** (WhatsApp + dashboard) + live congestion map + alternate route suggestions |
| 4 | Real-time public transport info | **Transport tab** — live GPS bus tracking, ETAs, schedule adherence |
| 5 | Public transport signal priority | **Signals engine** — green extension when a bus approaches a junction |
| 6 | Trip/Ride matching & reservation | **Ride Match tab** — commuter registration + route-overlap matching |
| 7 | Smart Parking using ITS | **Parking tab** + Leaflet pins — CV-style occupancy at 5 real locations |
| 8 | AI/ITS congestion management | **Prediction tab** — 30/60-min ML prediction + preemptive actions |
| + | Emergency Green Corridor | One click turns signals green along ambulance route (banner + twin + map) |
| + | Violation heatmap & analytics | **Analytics tab** — hotspots, revenue, daily auto-report |

---

## What's Inside

```
raipur_netra/
├── run.bat                  # one-click demo launcher (Windows)
├── requirements.txt         # pinned dependencies
├── Dockerfile, docker-compose.yml
├── .env.example             # runtime configuration surface
├── backend/
│   ├── main.py              # FastAPI — REST API + dashboard hosting
│   ├── settings.py          # env-driven runtime settings
│   ├── config.py            # Raipur junctions (GPS), roads, buses, parking, RTO
│   ├── simulator.py         # live city engine (demand curves, weather, events)
│   ├── signals.py           # adaptive signal controller + emergency corridor
│   ├── anpr.py              # ANPR + violations + e-challan + RTO lookup
│   ├── vision.py            # REAL CV: YOLOv8/MOG2 video pipeline + tracking
│   ├── predictor.py         # GBM congestion prediction (persisted models)
│   ├── bot.py               # TrafficGPT — Hindi/English natural language
│   ├── whatsapp.py          # Meta WhatsApp Cloud API gateway
│   ├── ridematch.py         # ride-matching algorithm
│   └── reports.py           # analytics + daily report generation
├── frontend/
│   ├── index.html           # command-center dashboard (11 modules)
│   ├── whatsapp_sim.html    # WhatsApp-Web-style gateway simulator
│   ├── vendor/leaflet/      # vendored Leaflet 1.9.4 (offline-safe)
│   └── js/                  # app · map (SVG+Leaflet) · vision · bot · charts
├── models/
│   └── yolo_raipur_best.pt  # fine-tuned Raipur vehicle-detection weights
├── data/
│   └── sample_traffic_clip.mp4
└── docs/
    ├── DEMO_SCRIPT.md       # judge-facing walkthrough
    ├── DEPLOYMENT.md        # Docker / VPS / PaaS + WhatsApp go-live
    └── EXTENDING.md         # how to modify & scale every layer
```

## WhatsApp Integration (production path)

The bot is exposed at `GET/POST /api/whatsapp/webhook` (Meta Cloud API format).
Point your Meta App's webhook at it, set `WHATSAPP_TOKEN` + `WHATSAPP_PHONE_NUMBER_ID`
in `.env`, and TrafficGPT answers real WhatsApp messages — the bundled simulator page
exercises this identical pipeline without needing a number. Full checklist:
`docs/DEPLOYMENT.md → WhatsApp go-live checklist`.

## Model Training (custom-trained on road-vehicle dataset)

The detection model is **trained in this repository** on the DatasetNinja
*Road Vehicle Detection* dataset — 3,004 annotated images, **24,348 bounding boxes**,
**21 Indian-road classes** (auto rickshaw, three wheelers CNG, human hauler, rickshaw,
ambulance, policecar, scooter…):

```bash
# 1. convert Supervisely annotations -> YOLO format (one-time)
python scripts/convert_dataset_to_yolo.py        # -> models/dataset/{train,valid}

# 2. fine-tune YOLOv8n (COCO-pretrained, frozen backbone, CPU-friendly)
python scripts/train_vehicle_model.py            # 2-epoch cap by default; raise for more mAP
```

Results, metrics and the class→category mapping (ambulance → auto-corridor trigger)
live in `backend/vision.py`. The trained weights deploy to `models/yolo_raipur_best.pt`
and are picked up automatically by the Video Detection tab.

## Technology Stack (all open-source)

Ultralytics YOLOv8 (fine-tuned) · OpenCV (MOG2 tracking) · GradientBoosting (sklearn)
· FastAPI · Leaflet 1.9 · vanilla JS (no build step, no CDN — fully offline-capable demo)
· Docker

## Raipur-Specific Deployment Plan

| Phase | Junctions | Features |
|-------|-----------|----------|
| 1 — Quick Win | Jaistambh, Telibandha, Fafadih, Pandri, Marine Drive | CCTV AI + ANPR + WhatsApp bot + dashboard |
| 2 — Expansion | 20 junctions | Edge AI signals, bus tracking, smart parking, ride matching |
| 3 — Full Intel | 50 junctions | Digital twin, TrafficGPT, auto reports, full analytics |

**Cost:** ₹4.25 lakh one-time + ₹13k/month · **Revenue:** ₹17.5 lakh/month (self-sustaining, ROI in week 1)
