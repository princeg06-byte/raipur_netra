# Extending RaipurNetra AI

The codebase is deliberately modular: every layer of the 5-layer architecture is one
Python module with a clean seam. Common changes and where to make them:

## Add / edit a junction or road
* `backend/config.py` → `JUNCTIONS` (add lat/lng for the map) and `ROADS` (connectivity).
* Register its signal axes in `PHASE_ROADS`. Nothing else needs touching — map, twin,
  routing, simulator and bot pick it up automatically.

## Swap simulation for real CCTV (RTSP)
* Live feed path lives in `backend/vision.py` (`VideoDetectionEngine`). Implement an
  `RtspSource` that calls `cap = cv2.VideoCapture("rtsp://...")` instead of a file and
  runs the same detection loop; push results with
  `simulator.vision_density[jid] = congestion` — the exact hook used by video binding.
* The REST contract (`/api/state`, …) stays identical, so the frontend needs no changes.

## Upgrade the prediction model
* `backend/predictor.py` → replace `GradientBoostingRegressor` with XGBoost/LSTM
  (the interface is `fit/predict` per junction+horizon; features are already
  engineered: lags, upstream congestion, calendar, weather, events).
* Models persist via joblib to `models/congestion/`; delete them to force a fresh train.

## Add TrafficGPT intents
* `backend/bot.py` → add a `_h_<intent>` method and register it in `handle()`.
  Handlers return `{reply, suggestions, ...}` and may attach rich data for the UI.

## Add a new REST endpoint
* `backend/main.py` → plain FastAPI route. Everything is wired around singletons
  (`simulator`, `anpr`, `predictor`, `video_engine`, `whatsapp`) — import and use them.

## Scale-out path (multi-worker / multi-city)
1. Extract `simulator` state into Redis (junction congestion + signal phases are the
   only mutable state; history is append-only).
2. Move video processing into a worker queue (Celery/RQ) writing congestion to Redis.
3. The FastAPI tier becomes stateless → scale workers horizontally behind nginx.

## Frontend
* No build step by design (industry-agnostic, works offline). Modules: `js/app.js`
  (dashboard), `js/map.js` (SVG twin + Leaflet), `js/vision.js` (CV tab), `js/bot.js`
  (chat), `js/charts.js` (canvas charts). Styling tokens live at the top of
  `css/style.css` (`:root` variables).
* To rebrand: change `--accent` / title / footer. To re-tile the map: set `RN_TILE_URL`.

## Config surface (no-code changes)
Everything in `backend/settings.py` is env-overridable — ports, YOLO confidence,
frame interval, retrain cadence, tile server, WhatsApp tokens. See `.env.example`.
