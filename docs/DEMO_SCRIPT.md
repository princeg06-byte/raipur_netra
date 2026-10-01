# RaipurNetra AI — Live Demo Script (Judge Walkthrough)

**One-line pitch:** *"Raipur already has 500+ CCTV cameras. We add the AI brain — zero new hardware, ₹4.25 lakh total, self-funding from week 1."*

**Start:** double-click `run.bat` → open http://localhost:8000

---

## 0. Command Center (30 sec)
- Live KPIs: city congestion, avg signal wait **with "-X% vs fixed timer"** (the core adaptive-signals claim), vehicles analysed today, violations/challans, revenue, buses tracked.
- Congestion chart: **solid = live city mirror, dashed = AI forecast +30 min**.
- Predictive alerts panel: preemptive actions the system would trigger.

## 1. Digital Twin (1 min) — Layer 3 (MIRROR)
- Live map of 12 real Raipur junctions: roads colored by congestion, vehicles animating, buses moving, signal phases (green bar = active green axis, "AI" vs "FIX" mode).
- **What-If demo:** select *MG Road* → **Close** → **Measure impact vs baseline** → AI shows +X% forecast on alternatives (Ring Road East / Jail Road). *"This is how we test a rally closure before it happens."*
- Toggle **Rain** → city-wide congestion rises, forecasts update.

## 2. Signals (1 min) — Layer 5 (ACT) — Requirement 1 & 5
- Green time = f(vehicle_count, queue_length, waiting_time, adjacent_junction_state).
- Switch *Pandri Chowk* to **Fixed** → wait goes up, "Saved %" drops. Switch back to **Adaptive** → recovers. *"That's the 25-35% wait reduction, live."*
- Bus priority: buses approaching a junction get +12s green automatically.

## 3. ANPR & e-Challan (1.5 min) — Layer 1 (SEE) — Requirement 2
- Live detection feed: plates (CG-04-XX-XXXX), vehicle class, speed, confidence.
- Heatmap: violation hotspots by junction. Click **Simulate violation burst** for effect.
- Auto e-challan table: owner (RTO lookup), fine, sent/paid status. Revenue projection ≈ ₹15-25 lakh/month.
- **Plate lookup:** type `CG-04-GR-6327` → owner record + challan history (the exact post-OCR pipeline a real camera feeds).

## 4. Prediction (1 min) — Layer 2 (THINK) — Requirement 8
- Per-junction 30-min forecast with risk levels + preemptive action list.
- Model card: GradientBoosting ensemble (LSTM+XGBoost architecture), hit-rate and MAE, retrained on live data — click **Retrain**.

## 5. Transport (45 sec) — Requirement 4 (+3, 6 partially)
- 8 GPS-tracked buses on 3 real corridors, live ETA, delay badges, occupancy.
- *"Route filters mirror the citizen bot experience — 'Bus 7 kab aayegi?'"*

## 6. Parking (30 sec) — Requirement 7
- 5 real locations (Magneto Mall, City Center, Pandri Market, Ambedkar Hospital, Railway Station) with live CV-occupancy bars.

## 7. Ride Match (30 sec) — Requirement 6
- Register a commuter → instant matches with route-overlap score. WhatsApp-native in production.

## 8. TrafficGPT (1.5 min) — the wow moment (Requirements 3, 8)
Ask in the chat, in Hindi or English:
- `Jaistambh Chowk traffic kaisa hai?` → live status + 30-min trend + advice
- `Fastest route from Jaistambh to Telibandha` → congestion-weighted Dijkstra with alternate
- `Bus 7 kab aayegi?` → live GPS ETA
- `Magneto Mall parking?` → live slots
- `Aaj ke challan stats` → enforcement summary
- `जयस्तम्भ चौक ट्रैफिक कैसा है?` → full Hindi reply

## 9. Emergency Green Corridor (30 sec) — Bonus
- Click **🚑 Emergency Corridor** → red banner, all signals along Jaistambh → Telibandha → Marine Drive forced green on the twin. *"8-12 minutes saved per emergency. This saves lives."*

## 10. Analytics (30 sec)
- Before/after impact table (matches proposal), revenue model (₹4.25L cost vs ₹17.5L/month), **Generate Daily Report** → printable report for police administration.

---

## Closing line
*"Everything you just saw runs on the cameras Raipur already owns. Phase 1 goes live at 5 junctions — Jaistambh, Telibandha, Fafadih, Pandri, Marine Drive — in 2 months, and pays for itself in the first week."*

## Architecture Q&A quick answers
- **Data path:** CCTV (RTSP) → YOLOv8 (this prototype simulates the feed; the CV pipeline is pluggable via `backend/anpr.py:process_plate_text`) → density → FastAPI → dashboard/bot.
- **Offline resilience:** edge devices make local decisions (signals work without internet).
- **Why GBM not LSTM in the demo:** same feature philosophy, trains in seconds on CPU for the live demo; production plan uses the LSTM+XGBoost ensemble on GPU server.
- **Security/privacy:** plates only, no face recognition; data stays with Police Commissionerate.
