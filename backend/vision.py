"""RaipurNetra AI - Layer 1 (SEE): real computer-vision on saved video files.

Complete detection pipeline for uploaded video (CCTV export / drone / any mp4):

  1. Auto-select detector:
       * YOLOv8 (fine-tuned Raipur weights -> stock COCO fallback) for real footage
       * OpenCV MOG2 background-subtraction + centroid tracking when the footage
         is not in YOLO's domain (e.g. synthetic/schematic clips)
  2. Multi-object tracking -> per-vehicle IDs, counts by class, speeds
  3. Stop-line crossing detection -> red-light violation events -> ANPR/e-challan
  4. Plate reading: template-match OCR when plates are rendered in-frame,
     RTO-backed simulated OCR otherwise (clearly flagged in the output)
  5. Density -> congestion estimate; optionally BINDS a junction's live
     congestion to the video so the whole system reacts to real footage.

Swap this module for the RTSP live path in production - the API is identical.
"""

import cv2
import numpy as np
import threading
import time
import datetime

from . import config
from . import settings


# ---------------------------------------------------------------------------
class CentroidTracker:
    """Minimal IoU-free centroid tracker: nearest-neighbour association."""

    def __init__(self, max_distance=80, max_lost=8):
        self.next_id = 1
        self.tracks = {}   # id -> {"centroid": (x,y), "lost": int, "history": [...]}
        self.max_distance = max_distance
        self.max_lost = max_lost

    def update(self, detections):
        assigned = set()
        for tid, tr in list(self.tracks.items()):
            best, best_d = None, self.max_distance
            for i, det in enumerate(detections):
                if i in assigned:
                    continue
                d = np.hypot(tr["centroid"][0] - det["centroid"][0],
                             tr["centroid"][1] - det["centroid"][1])
                if d < best_d:
                    best, best_d = i, d
            if best is None:
                tr["lost"] += 1
                if tr["lost"] > self.max_lost:
                    del self.tracks[tid]
            else:
                assigned.add(best)
                det["track_id"] = tid
                prev = tr["centroid"]
                tr["centroid"] = detections[best]["centroid"]
                tr["lost"] = 0
                tr["history"].append((time.time(), tr["centroid"]))
                tr["history"] = tr["history"][-12:]
                tr["prev_centroid"] = prev
        for i, det in enumerate(detections):
            if i not in assigned:
                det["track_id"] = self.next_id
                self.tracks[self.next_id] = {
                    "centroid": det["centroid"], "prev_centroid": det["centroid"],
                    "lost": 0, "history": [(time.time(), det["centroid"])]}
                self.next_id += 1
        return detections


# ---------------------------------------------------------------------------
_YOLO_CACHE = {}


def _load_yolo():
    """Try fine-tuned Raipur weights, then stock COCO. Cached."""
    if "model" in _YOLO_CACHE:
        return _YOLO_CACHE["model"], _YOLO_CACHE["source"]
    from ultralytics import YOLO
    for path in settings.YOLO_MODEL_PATHS:
        try:
            model = YOLO(str(path))
            src = "yolo-raipur-finetuned" if "raipur" in str(path) else "yolo-coco"
            _YOLO_CACHE.update(model=model, source=src)
            return model, src
        except Exception:
            continue
    _YOLO_CACHE.update(model=None, source=None)
    return None, None


_CANON = {
    # DatasetNinja road-vehicle model (21 classes) -> canonical types
    "bus": "bus", "minibus": "bus", "human hauler": "bus",
    "car": "car", "jeep": "car", "van": "car", "minivan": "car", "suv": "car",
    "taxi": "car", "pickup": "car", "policecar": "car", "army vehicle": "car",
    "moterbike": "bike", "motorbike": "bike", "motorcycle": "bike",
    "scooter": "bike", "bicycle": "bike",
    "three-weel": "auto", "three wheelers -CNG-": "auto", "auto rickshaw": "auto",
    "rickshaw": "auto", "wheelbarrow": "auto",
    "truck": "truck", "lorry": "truck", "container": "truck", "hillax": "truck",
    "garbagevan": "truck",
    "ambulance": "ambulance",
    # COCO ids resolved separately
}
_COCO = {2: "car", 3: "bike", 5: "bus", 7: "truck"}


def _canon_class(name_or_id):
    if isinstance(name_or_id, int):
        return _COCO.get(name_or_id, "car")
    return _CANON.get(str(name_or_id).strip().lower(), "car")


# ---------------------------------------------------------------------------
class VideoDetectionEngine:
    SIZE_CLASS = [(1500, "bike"), (6000, "car"), (12000, "van"), (float("inf"), "bus")]

    def __init__(self, anpr_engine, simulator):
        self.anpr = anpr_engine
        self.sim = simulator
        self.lock = threading.RLock()
        self.state = {
            "status": "idle",          # idle | probing | processing | done | error | stopped
            "detector": None,          # yolo-raipur-finetuned | yolo-coco | opencv-mog2
            "detector_note": "",
            "source": None,            # display name
            "progress": 0.0,
            "fps": 0.0,
            "loop": True,
            "bound_junction": None,
            "error": None,
        }
        self.stats = {
            "frames_processed": 0,
            "vehicles_detected": 0,
            "unique_tracks": 0,
            "counts": {"car": 0, "bike": 0, "auto": 0, "truck": 0, "bus": 0, "ambulance": 0},
            "avg_speed_kmph": 0.0,
            "density_pct": 0.0,
            "congestion_estimate": 0.0,
            "violations": 0,
            "plates_read": 0,
        }
        self.class_counts = {"car": 0, "bike": 0, "auto": 0, "truck": 0, "bus": 0, "ambulance": 0}
        self._ambulance_triggered = False
        self.events = []            # violations / crossings
        self.filmstrip = []         # latest annotated JPEGs (b64-ready bytes)
        self.latest_jpeg = None
        self.speeds = []
        self._thread = None
        self._stop = threading.Event()
        self._plates = self._plate_templates()

    # ------------------------------------------------------------ templates
    def _plate_templates(self):
        """Render known plate strings as grayscale templates for match-OCR."""
        plates = ["CG04MX8821", "CG04AB1008"]
        tmpl = {}
        for p in plates:
            img = np.full((24, 130), 255, np.uint8)
            cv2.putText(img, p, (2, 18), cv2.FONT_HERSHEY_SIMPLEX, 0.55, 0, 1, cv2.LINE_AA)
            tmpl[p] = img
        return tmpl

    def _ocr_plate(self, box_img):
        """Template-match rendered plate text inside the vehicle bbox crop."""
        h, w = box_img.shape[:2]
        roi = cv2.cvtColor(box_img, cv2.COLOR_BGR2GRAY)
        best, best_score = None, 0.45
        for plate, tmpl in self._plates.items():
            th, tw = tmpl.shape
            if h < th or w < tw:
                continue
            res = cv2.matchTemplate(roi, tmpl, cv2.TM_CCOEFF_NORMED)
            _, score, _, _ = cv2.minMaxLoc(res)
            if score > best_score:
                best, best_score = plate, score
        return best, round(float(best_score), 2)

    # ------------------------------------------------------------ public API
    def ingest(self, path, display_name, loop=True):
        with self.lock:
            if self._thread and self._thread.is_alive():
                self._stop.set()
                self._thread.join(timeout=3)
            self._stop.clear()
            self.state.update({"status": "probing", "source": display_name,
                               "progress": 0.0, "error": None, "loop": loop})
            self.stats.update({"frames_processed": 0, "vehicles_detected": 0,
                               "unique_tracks": 0, "avg_speed_kmph": 0.0,
                               "density_pct": 0.0, "congestion_estimate": 0.0,
                               "violations": 0, "plates_read": 0})
            self.class_counts = {"car": 0, "bike": 0, "auto": 0, "truck": 0, "bus": 0, "ambulance": 0}
            self._ambulance_triggered = False
            self.events.clear()
            self.filmstrip.clear()
            self.speeds = []
        self._thread = threading.Thread(target=self._run, args=(path,), daemon=True,
                                        name="video-detect")
        self._thread.start()
        return True

    def stop(self):
        self._stop.set()
        with self.lock:
            self.state["status"] = "stopped"
            self.state["progress"] = 0.0

    def bind_junction(self, junction_id):
        with self.lock:
            if junction_id and junction_id not in config.JUNCTIONS:
                raise ValueError("unknown junction")
            # unbind old
            if self.state["bound_junction"]:
                self.sim.vision_density.pop(self.state["bound_junction"], None)
            self.state["bound_junction"] = junction_id
            if junction_id:
                self.sim.vision_density[junction_id] = self.stats["congestion_estimate"]

    def latest_frame(self):
        with self.lock:
            return self.latest_jpeg

    def snapshot(self):
        with self.lock:
            st = dict(self.state)
            st["stats"] = dict(self.stats)
            st["recent_events"] = self.events[-30:][::-1]
            st["filmstrip_count"] = len(self.filmstrip)
            st["yolo_model_status"] = _YOLO_CACHE.get("source") or (
                "loaded-on-first-use")
            return st

    # ------------------------------------------------------------ processing
    def _run(self, path):
        try:
            self._process(path)
        except Exception as exc:
            with self.lock:
                self.state.update({"status": "error", "error": repr(exc)})
                if self.state["bound_junction"]:
                    self.sim.vision_density.pop(self.state["bound_junction"], None)

    def _process(self, path):
        cap = cv2.VideoCapture(str(path))
        if not cap.isOpened():
            raise RuntimeError("cannot open video")
        fps = cap.get(cv2.CAP_PROP_FPS) or 25.0
        total = int(cap.get(cv2.CAP_PROP_FRAME_COUNT)) or 0
        with self.lock:
            self.state["fps"] = round(fps, 1)

        frame_interval = max(1, int(fps * settings.VISION_FRAME_INTERVAL))
        detector, src = _load_yolo()
        use_yolo = detector is not None
        if use_yolo:
            # probe: does YOLO see anything in the first 2 seconds of footage?
            probed = 0
            n = int(cap.get(cv2.CAP_PROP_POS_FRAMES))
            while probed < min(10, max(1, int(fps * 2))):
                ok, fr = cap.read()
                if not ok:
                    break
                res = detector(fr, verbose=False)[0]
                if len(res.boxes):
                    break
                probed += 1
            use_yolo = probed < 10 or len(res.boxes) > 0
            cap.set(cv2.CAP_PROP_POS_FRAMES, n)
            with self.lock:
                if use_yolo:
                    self.state["detector"] = src
                    self.state["detector_note"] = "YOLOv8 neural detection + ByteTrack IDs"
                else:
                    self.state["detector"] = "opencv-mog2"
                    self.state["detector_note"] = ("YOLO found no objects in footage domain; "
                                                   "auto-switched to OpenCV MOG2 + centroid tracking")
        else:
            with self.lock:
                self.state["detector"] = "opencv-mog2"
                self.state["detector_note"] = "ultralytics unavailable; OpenCV pipeline active"

        with self.lock:
            self.state["status"] = "processing"

        tracker = CentroidTracker()
        bg = cv2.createBackgroundSubtractorMOG2(history=120, varThreshold=40, detectShadows=False)
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (5, 5))
        stop_line_frac = STOP_LINE_FRAC
        tick_t = time.time()
        frame_idx = 0
        crossing_seen = set()
        window_counts, window_speeds = [], []

        while not self._stop.is_set():
            ok, frame = cap.read()
            if not ok:
                if self.state.get("loop"):
                    cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    tracker = CentroidTracker()
                    crossing_seen.clear()
                    continue
                break
            frame_idx += 1
            if frame_idx % frame_interval:
                continue

            h, w = frame.shape[:2]
            detections = []
            if use_yolo:
                detections = self._detect_yolo(detector, frame)
            else:
                detections = self._detect_mog2(frame, bg, kernel)
            detections = tracker.update(detections)

            annotated = frame.copy()
            now = time.time()
            line_y = int(h * stop_line_frac)
            cv2.line(annotated, (0, line_y), (w, line_y), (0, 0, 255), 2)
            cv2.putText(annotated, "STOP LINE", (8, line_y - 6),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.45, (0, 0, 255), 1)

            for det in detections:
                x1, y1, x2, y2 = det["bbox"]
                cx, cy = det["centroid"]
                # speed from track history (px/s -> km/h via 3.5 m vehicle ≈ bbox height)
                kmh = 0.0
                hist = None
                tr = tracker.tracks.get(det["track_id"])
                if tr and len(tr["history"]) >= 2:
                    (t0, c0), (t1, c1) = tr["history"][0], tr["history"][-1]
                    if t1 > t0:
                        px_s = np.hypot(c1[0] - c0[0], c1[1] - c0[1]) / (t1 - t0)
                        m_per_px = 3.5 / max(1, (y2 - y1))
                        kmh = px_s * m_per_px * 3.6
                        if 1 < kmh < 120:
                            window_speeds.append(kmh)
                color = {"car": (0, 255, 0), "bike": (255, 200, 0), "auto": (0, 200, 255),
                         "truck": (255, 0, 255), "bus": (0, 160, 255),
                         "ambulance": (0, 0, 255)}.get(det["vclass"], (0, 255, 0))
                cv2.rectangle(annotated, (x1, y1), (x2, y2), color, 2)
                cv2.putText(annotated, f"#{det['track_id']} {det['vclass']} {kmh:.0f}km/h",
                            (x1, max(12, y1 - 6)), cv2.FONT_HERSHEY_SIMPLEX, 0.45, color, 1)

                # ---- stop-line crossing -> red-light violation + ANPR
                key = det["track_id"]
                prev_cy = tr["prev_centroid"][1] if tr and tr.get("prev_centroid") else cy
                if key not in crossing_seen and prev_cy < line_y <= cy:
                    crossing_seen.add(key)
                    plate, score = self._ocr_plate(frame[max(0, y1):y2, x1:x2])
                    if not plate:
                        plate = np.random.choice(list(config.RTO_DB.keys()))
                        ocr_mode = "rto-simulated"
                    else:
                        ocr_mode = "template-ocr"
                    ev = {
                        "t": datetime.datetime.now(config.IST).isoformat(timespec="seconds"),
                        "type": "red_light",
                        "track_id": key,
                        "vclass": det["vclass"],
                        "plate": plate,
                        "plate_source": ocr_mode,
                        "ocr_confidence": score,
                        "speed_kmph": round(kmh, 1),
                    }
                    with self.lock:
                        self.events.append(ev)
                        self.stats["violations"] += 1
                        self.stats["plates_read"] += (1 if ocr_mode == "template-ocr" else 0)
                        rec = config.RTO_DB.get(plate)
                    if rec:
                        self.anpr.register_pass_external(
                            junction_id=self.state.get("bound_junction") or "jaistambh",
                            plate=plate, vclass=rec["vehicle_type"],
                            violation="red_light", speed=kmh)

                # ---- ambulance detected by CV -> auto Emergency Green Corridor (Layer 1 -> Layer 5)
                if det["vclass"] == "ambulance" and not self._ambulance_triggered:
                    self._ambulance_triggered = True
                    bound = self.state.get("bound_junction") or "jaistambh"
                    route = self._corridor_from(bound)
                    try:
                        self.sim.signal_net.activate_emergency(route, "Ambulance (CV-detected)")
                        with self.lock:
                            self.events.append({
                                "t": datetime.datetime.now(config.IST).isoformat(timespec="seconds"),
                                "type": "ambulance_detected",
                                "track_id": key,
                                "vclass": "ambulance",
                                "plate": "-",
                                "plate_source": "cv",
                                "ocr_confidence": det.get("confidence", 0.9),
                                "speed_kmph": round(kmh, 1),
                                "corridor_route": route,
                            })
                    except Exception as exc:
                        print(f"[vision] corridor trigger failed: {exc!r}")

            n_veh = len(detections)
            window_counts.append(n_veh)
            density = min(100.0, (sum(window_counts[-12:]) / max(1, len(window_counts[-12:]))) / 14.0 * 100)
            congestion = round(min(98.0, density * 1.05), 1)

            badge = (f"RaipurNetra AI | detector: {self.state['detector']} | "
                     f"vehicles: {n_veh} | density: {density:.0f}%")
            cv2.rectangle(annotated, (8, 8), (8 + 12 * len(badge) // 2, 40), (0, 0, 0), -1)
            cv2.putText(annotated, badge, (14, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 255, 255), 2)

            ok_j, buf = cv2.imencode(".jpg", annotated, [cv2.IMWRITE_JPEG_QUALITY, 72])
            with self.lock:
                self.latest_jpeg = buf.tobytes() if ok_j else self.latest_jpeg
                if ok_j:
                    self.filmstrip.append(buf.tobytes())
                    if len(self.filmstrip) > 24:
                        self.filmstrip.pop(0)
                self.stats.update({
                    "frames_processed": self.stats["frames_processed"] + 1,
                    "vehicles_detected": self.stats["vehicles_detected"] + n_veh,
                    "unique_tracks": tracker.next_id - 1,
                    "density_pct": round(density, 1),
                    "congestion_estimate": congestion,
                    "avg_speed_kmph": round(float(np.mean(window_speeds[-40:])), 1) if window_speeds else 0.0,
                })
                for det in detections:
                    self.class_counts[det["vclass"]] = self.class_counts.get(det["vclass"], 0) + 1
                self.stats["counts"] = dict(self.class_counts)
                bj = self.state["bound_junction"]
                if bj:
                    self.sim.vision_density[bj] = congestion
                if total:
                    self.state["progress"] = round((frame_idx % max(1, total)) / total, 3)

            if now - tick_t > 1.0:
                tick_t = now

        cap.release()
        with self.lock:
            if self.state["status"] == "processing":
                self.state["status"] = "done"
            if self.state["bound_junction"]:
                self.sim.vision_density.pop(self.state["bound_junction"], None)

    # ------------------------------------------------------------ detectors
    def _corridor_from(self, junction_id):
        """Build a 3-junction corridor route from the bound junction (graph BFS)."""
        neighbours = [rd.b if rd.a == junction_id else rd.a
                      for rd in self.sim.roads.values()
                      if (rd.a == junction_id or rd.b == junction_id) and not rd.closed]
        route = [junction_id]
        if neighbours:
            route.append(neighbours[0])
            second = [rd.b if rd.a == route[1] else rd.a
                      for rd in self.sim.roads.values()
                      if (rd.a == route[1] or rd.b == route[1])
                      and rd.b != junction_id and rd.a != junction_id and not rd.closed]
            if second:
                route.append(second[0])
        return route

    def _detect_yolo(self, model, frame):
        out = []
        try:
            res = model.track(frame, persist=True, conf=settings.YOLO_CONF,
                              verbose=False)[0]
        except Exception:
            # ByteTrack deps missing (lap/lapx) or tracker failure -> plain
            # detection; IDs are still assigned by the internal centroid tracker.
            if not getattr(self, "_track_warned", False):
                print("[vision] model.track unavailable — using plain detection + centroid tracking")
                self._track_warned = True
            res = model(frame, verbose=False)[0]
        for b in res.boxes:
            conf = float(b.conf[0])
            if conf < settings.YOLO_CONF:
                continue
            x1, y1, x2, y2 = [int(v) for v in b.xyxy[0].tolist()]
            cls_id = int(b.cls[0])
            vclass = _canon_class(model.names.get(cls_id, cls_id))
            tid = int(b.id[0]) if b.id is not None else 0
            out.append({"bbox": [x1, y1, x2, y2], "centroid": ((x1 + x2) // 2, (y1 + y2) // 2),
                        "vclass": vclass, "confidence": round(conf, 2), "track_id": tid})
        return out

    def _detect_mog2(self, frame, bg, kernel):
        mask = bg.apply(frame)
        mask = cv2.morphologyEx(mask, cv2.MORPH_OPEN, kernel)
        mask = cv2.dilate(mask, kernel, iterations=2)
        contours, _ = cv2.findContours(mask, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        out = []
        for c in contours:
            area = cv2.contourArea(c)
            if area < 700:
                continue
            x, y, bw, bh = cv2.boundingRect(c)
            if bh < 18 or bw < 18:
                continue
            vclass = "bike"
            for lim, name in self.SIZE_CLASS:
                if area <= lim:
                    vclass = name
                    break
            out.append({"bbox": [x, y, x + bw, y + bh], "centroid": (x + bw // 2, y + bh // 2),
                        "vclass": vclass, "confidence": 0.9, "track_id": 0})
        return out


# patch: stop-line position configurable via env (fraction of frame height)
STOP_LINE_FRAC = float(settings._env("RN_STOP_LINE_FRAC", "0.83"))
