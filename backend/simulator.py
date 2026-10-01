"""RaipurNetra AI - Live city traffic simulation engine.

Simulates Raipur's road network in real time: per-road congestion driven by
time-of-day demand curves, weather, events and signal efficiency; live bus
movement on real routes; parking occupancy; and minute-resolution history
for the prediction models and dashboard charts.

In production this module is replaced by the real data path
(CCTV -> YOLOv8 -> per-lane density). The API contract stays identical.
"""

import math
import random
import threading
import time
import datetime

from . import config
from .signals import SignalNetwork


def now_ist():
    return datetime.datetime.now(config.IST)


def minute_of_day(dt=None):
    dt = dt or now_ist()
    return dt.hour * 60 + dt.minute


# ---------------------------------------------------------------------------
# Demand profile: Raipur-style double peak (morning office/school, evening
# market + return-home), lighter weekend. Values are relative multipliers.
# ---------------------------------------------------------------------------
_WEEKDAY_PROFILE = {
    0: 0.15, 1: 0.10, 2: 0.08, 3: 0.06, 4: 0.08, 5: 0.15, 6: 0.35, 7: 0.65,
    8: 0.95, 9: 1.10, 10: 0.95, 11: 0.85, 12: 0.80, 13: 0.75, 14: 0.75,
    15: 0.85, 16: 0.95, 17: 1.15, 18: 1.25, 19: 1.20, 20: 1.05, 21: 0.85,
    22: 0.55, 23: 0.30,
}
_WEEKEND_PROFILE = {
    0: 0.25, 1: 0.18, 2: 0.12, 3: 0.08, 4: 0.08, 5: 0.12, 6: 0.25, 7: 0.40,
    8: 0.55, 9: 0.70, 10: 0.85, 11: 0.95, 12: 1.00, 13: 0.95, 14: 0.85,
    15: 0.90, 16: 1.00, 17: 1.10, 18: 1.15, 19: 1.10, 20: 0.95, 21: 0.75,
    22: 0.50, 23: 0.35,
}
# Junction-specific modifiers (market/school/industry patterns)
_JUNCTION_PROFILE_BIAS = {
    "pandri":     {"morning": 1.15, "evening": 1.25},   # market + bus terminal
    "jaistambh":  {"morning": 1.20, "evening": 1.15},   # city center
    "shankar":    {"morning": 1.30, "evening": 0.95},   # schools/colleges
    "fafadih":    {"morning": 1.10, "evening": 1.05},   # industrial
    "marine":     {"morning": 0.90, "evening": 1.25},   # evening walkers/food
    "telibandha": {"morning": 1.05, "evening": 1.20},   # commercial
}


def demand_factor(junction_id, dt=None):
    dt = dt or now_ist()
    wknd = dt.weekday() >= 5
    prof = _WEEKEND_PROFILE if wknd else _WEEKDAY_PROFILE
    f = prof[dt.hour]
    bias = _JUNCTION_PROFILE_BIAS.get(junction_id, {})
    if 7 <= dt.hour < 12:
        f *= bias.get("morning", 1.0)
    elif 16 <= dt.hour < 21:
        f *= bias.get("evening", 1.0)
    return f


# ---------------------------------------------------------------------------
class RoadState:
    __slots__ = ("rid", "a", "b", "name", "capacity", "lanes", "congestion",
                 "vehicles", "speed", "inflow_rate", "closed", "closed_redist")

    def __init__(self, rid, a, b, name, capacity, lanes):
        self.rid, self.a, self.b, self.name = rid, a, b, name
        self.capacity, self.lanes = capacity, lanes
        self.congestion = 0.2
        self.vehicles = 0.0
        self.speed = 40.0
        self.inflow_rate = 0.0
        self.closed = False
        self.closed_redist = 0.0


class BusState:
    def __init__(self, bus):
        self.id = bus["id"]
        self.route = bus["route"]
        self.schedule_min = bus["schedule_min"]
        self.path = config.BUS_ROUTES[bus["route"]]["path"]
        self.seg = random.randrange(len(self.path))
        self.progress = random.random()
        self.occupancy = random.randint(10, 45)
        self.delay_min = round(random.uniform(-2, 9), 1)
        self.dwell = 0.0

    @property
    def from_j(self):
        return self.path[self.seg % len(self.path)]

    @property
    def to_j(self):
        return self.path[(self.seg + 1) % len(self.path)]


class CitySimulator:
    TICK_SECONDS = 1.0

    def __init__(self):
        self.lock = threading.RLock()
        self.rng = random.Random(7)
        self.roads = {rid: RoadState(rid, *spec) for rid, spec in config.ROADS.items()}
        self.signal_net = SignalNetwork()
        for jid, jd in config.JUNCTIONS.items():
            self.signal_net.register(jid, config.PHASE_ROADS[jid])
        self.buses = [BusState(b) for b in config.BUSES]
        self.parking = {pid: {"occupied": int(lot["total"] * random.uniform(0.2, 0.6)),
                              "total": lot["total"]}
                        for pid, lot in config.PARKING_LOTS.items()}
        self.weather = "clear"          # clear | rain
        self.event_active = False       # toggleable what-if
        self.active_event = None        # from calendar (auto if today)
        self.closed_roads = set()
        self.signal_overrides = {}      # jid -> {"mode": ...} what-if
        self.vision_density = {}        # jid -> congestion measured from live video (vision.py)
        self.history = []               # minute-resolution snapshots
        self.tick_count = 0
        self.vehicles_today = 0
        self.start_wall = time.time()
        self.sim_time = now_ist()
        self._anpr_hook = None          # set by main: fn(junction_id, vehicles_per_min)
        self._seed_history()
        self._thread = None
        self._stop = threading.Event()

    # ------------------------------------------------------------------ setup
    def _seed_history(self):
        """Pre-seed 48h of minute history so charts + predictor have data.

        Two full daily cycles matter: the prediction models must see both the
        morning AND evening peaks in their training window, otherwise trees
        cannot interpolate the current time-of-day (measured MAE 2.7 vs 17+)."""
        hours = 48
        t0 = now_ist() - datetime.timedelta(hours=hours)
        for m in range(hours * 60):
            dt = t0 + datetime.timedelta(minutes=m)
            row = {"t": dt.isoformat(timespec="minutes"),
                   "city": 0.0, "junctions": {}}
            for jid in config.JUNCTIONS:
                d = demand_factor(jid, dt)
                rain = 1.12 if (m % 240) > 190 else 1.0   # intermittent showers
                c = min(0.97, max(0.06, 0.52 * d * rain + self.rng.gauss(0, 0.045)))
                row["junctions"][jid] = round(c * 100, 1)
            row["city"] = round(sum(row["junctions"].values()) / len(row["junctions"]), 1)
            row["weather"] = "rain" if rain > 1 else "clear"
            self.history.append(row)

    def set_anpr_hook(self, fn):
        self._anpr_hook = fn

    # ------------------------------------------------------------------ loop
    def start(self):
        self._thread = threading.Thread(target=self._run, daemon=True, name="sim-tick")
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _run(self):
        while not self._stop.is_set():
            t0 = time.time()
            try:
                self.tick()
            except Exception as exc:  # keep the demo alive no matter what
                print(f"[simulator] tick error: {exc!r}")
            time.sleep(max(0.05, self.TICK_SECONDS - (time.time() - t0)))

    # ------------------------------------------------------------------ tick
    def tick(self):
        with self.lock:
            self.tick_count += 1
            self.sim_time = now_ist()
            self._check_event_calendar()
            wf = 1.28 if self.weather == "rain" else 1.0
            ef = self._event_factor()

            # ---- 1. per-road congestion dynamics
            for road in self.roads.values():
                base = (demand_factor(road.a, self.sim_time) + demand_factor(road.b, self.sim_time)) / 2
                inflow = base * wf * ef * road.capacity * 0.28 * road.lanes / 60.0  # veh/s
                if road.closed:
                    road.inflow_rate = 0.0
                    road.congestion = max(0.02, road.congestion - 0.02)
                    road.vehicles = road.congestion * road.capacity * road.lanes / 8.0
                    road.speed = 45.0
                    continue
                # closure redistribution: neighbours absorb the closed road's load
                inflow *= (1.0 + road.closed_redist)
                green_share = self._green_share_for_road(road)
                sat = road.capacity * road.lanes / 60.0 * green_share
                c_target = inflow / max(sat, 1.0) * wf
                c_target = min(0.98, max(0.05, c_target))
                relax = 0.06
                road.congestion += (c_target - road.congestion) * relax + self.rng.gauss(0, 0.008)
                road.congestion = min(0.99, max(0.03, road.congestion))
                road.inflow_rate = inflow
                road.vehicles = road.congestion * road.capacity * road.lanes / 8.0
                freeflow = 45.0 if road.lanes > 1 else 38.0
                road.speed = freeflow * (1.0 - 0.82 * road.congestion) * (0.75 if self.weather == "rain" else 1.0)
                road.speed = max(6.0, road.speed)

            # ---- 2. vision-measured congestion binding (real video overrides sim)
            for bj, dens in self.vision_density.items():
                for r in self._junction_incoming(bj):
                    self.roads[r].congestion += (min(0.99, dens / 100.0) - self.roads[r].congestion) * 0.5

            # ---- 2b. signals + junction queues
            road_by_name_axis = {}
            for jid, axes in config.PHASE_ROADS.items():
                queues, arrivals = {"ns": 0.0, "ew": 0.0}, {"ns": 0.0, "ew": 0.0}
                for ax, rids in axes.items():
                    for rid in rids:
                        road = self.roads[rid]
                        q = road.congestion * 22.0 * (1.0 + (0.4 if self.signal_net.signals[jid].mode == "fixed" else 0.0))
                        queues[ax] += q
                        arrivals[ax] += road.inflow_rate / 8.0
                road_by_name_axis[jid] = (queues, arrivals)

            bus_at = {}
            for bus in self.buses:
                if bus.progress > 0.78:
                    bus_at.setdefault(bus.to_j, bus.id)

            for jid, sig in self.signal_net.signals.items():
                queues, arrivals = road_by_name_axis[jid]
                em_axis = self._emergency_axis(jid)
                mode_override = self.signal_overrides.get(jid, {}).get("mode")
                if mode_override:
                    sig.mode = mode_override
                sig.update(self.TICK_SECONDS, queues, arrivals, bus_at.get(jid), em_axis)

            # green wave detection on corridors
            if self.tick_count % 30 == 0:
                for rid, (a, b, *_ ) in config.ROADS.items():
                    sa, sb = self.signal_net.signals.get(a), self.signal_net.signals.get(b)
                    if sa and sb and sa.phase == sb.phase and not self.roads[rid].closed:
                        sa.green_waves = getattr(sa, "green_waves", 0)

            # ---- 3. buses
            self._advance_buses()

            # ---- 4. parking drift
            if self.tick_count % 5 == 0:
                self._update_parking()

            # ---- 5. ANPR hook (vehicle passes -> plates/violations)
            if self._anpr_hook and self.tick_count % 3 == 0:
                for jid, jd in config.JUNCTIONS.items():
                    throughput = sum(self.roads[r].inflow_rate for r in self._junction_incoming(jid)) * 3
                    if throughput > 0.2:
                        self._anpr_hook(jid, throughput)

            # ---- 6. emergency corridor progress
            if self.signal_net.emergency["active"]:
                self.signal_net.advance_emergency(self.TICK_SECONDS, completed=False)

            # ---- 7. vehicles-detected KPI
            self.vehicles_today += sum(r.inflow_rate for r in self.roads.values()) * self.TICK_SECONDS * 2.6

            # ---- 8. history every simulated minute
            if self._minutes_since_last_history() >= 1:
                self._append_history()

    # ---------------------------------------------------------------- helpers
    def _junction_incoming(self, jid):
        return [rid for rid, rd in self.roads.items() if rd.a == jid or rd.b == jid]

    def _green_share_for_road(self, road):
        """Average green fraction across both endpoint signals for this road."""
        shares = []
        for jid in (road.a, road.b):
            sig = self.signal_net.signals.get(jid)
            if not sig:
                continue
            axes = config.PHASE_ROADS[jid]
            ax = "ns" if road.rid in axes["ns"] else ("ew" if road.rid in axes["ew"] else None)
            if ax is None:
                shares.append(0.5)
                continue
            green = 1.0 if sig.phase == ax else 0.0
            share = (sig.green_time / (sig.green_time + 30.0))
            shares.append(green * 0.4 + share * 0.6)
        return sum(shares) / max(1, len(shares)) if shares else 0.5

    def _emergency_axis(self, jid):
        em = self.signal_net.emergency
        if not em["active"] or jid not in em["route"]:
            return None
        idx = em["route"].index(jid)
        neighbours = []
        if idx > 0:
            neighbours.append(em["route"][idx - 1])
        if idx + 1 < len(em["route"]):
            neighbours.append(em["route"][idx + 1])
        axes = config.PHASE_ROADS[jid]
        for ax, rids in axes.items():
            for rid in rids:
                rd = self.roads[rid]
                if rd.a in neighbours or rd.b in neighbours:
                    return ax
        return None

    def _advance_buses(self):
        for bus in self.buses:
            if bus.dwell > 0:
                bus.dwell -= self.TICK_SECONDS
                continue
            # loop routes can wrap onto the same junction — skip that degenerate segment
            if bus.from_j == bus.to_j:
                bus.seg = (bus.seg + 1) % len(bus.path)
                continue
            rid = self._road_between(bus.from_j, bus.to_j)
            road = self.roads.get(rid)
            speed = road.speed if road else 30.0
            seg_len = self._segment_len(bus.from_j, bus.to_j)
            seg_meters = max(1.0, seg_len * 10.0)  # schematic units -> ~10 m per unit
            sched_speed = 22.0           # km/h scheduled pace
            bus.progress += (speed / 3.6) * self.TICK_SECONDS / seg_meters
            if bus.progress >= 1.0:
                bus.progress = 0.0
                bus.seg = (bus.seg + 1) % len(bus.path)
                bus.dwell = self.rng.uniform(8, 20)
                bus.occupancy = max(0, min(60, bus.occupancy + self.rng.randint(-6, 7)))
            # delay accumulates when moving slower than schedule
            bus.delay_min += self.TICK_SECONDS / 60.0 * (sched_speed - speed) / 9.0
            bus.delay_min = max(-3.0, min(25.0, bus.delay_min))

    def _road_between(self, a, b):
        for rid, rd in self.roads.items():
            if (rd.a == a and rd.b == b) or (rd.a == b and rd.b == a):
                return rid
        return None

    def _segment_len(self, a, b):
        ja, jb = config.JUNCTIONS[a], config.JUNCTIONS[b]
        return math.hypot(ja["x"] - jb["x"], ja["y"] - jb["y"]) * 1.2

    def _update_parking(self):
        t = minute_of_day(self.sim_time) / 60.0
        for pid, lot in self.parking.items():
            target = 0.35 + 0.5 * demand_factor(pid if pid in config.JUNCTIONS else "jaistambh", self.sim_time)
            if pid == "magneto" and 17 <= t < 21:
                target = min(0.97, target + 0.2)
            occ = lot["occupied"] + self.rng.randint(-2, 3)
            drift = (target * lot["total"] - occ) * 0.08
            lot["occupied"] = max(0, min(lot["total"], int(occ + drift)))

    def _check_event_calendar(self):
        today = self.sim_time.date().isoformat()
        if not self.event_active:
            self.active_event = next((e for e in config.EVENTS if e["date"] == today), None)

    def _event_factor(self):
        f = 1.0
        if self.event_active:
            f *= 1.35
        if self.active_event:
            f *= self.active_event["impact"] * 0.9
        return f

    def _minutes_since_last_history(self):
        if not self.history:
            return 999
        last = datetime.datetime.fromisoformat(self.history[-1]["t"])
        return (self.sim_time - last).total_seconds() / 60.0

    def _append_history(self):
        congs = [r.congestion * 100 for r in self.roads.values()]
        row = {"t": self.sim_time.isoformat(timespec="minutes"),
               "city": round(sum(congs) / len(congs), 1),
               "junctions": {
                   jid: round(sum(self.roads[r].congestion for r in self._junction_incoming(jid))
                              / max(1, len(self._junction_incoming(jid))) * 100, 1)
                   for jid in config.JUNCTIONS
               },
               "weather": self.weather}
        self.history.append(row)
        if len(self.history) > 49 * 60:
            self.history.pop(0)

    # ------------------------------------------------------------------ what-if
    def set_road_closed(self, rid, closed):
        with self.lock:
            if closed and rid in self.roads:
                self.closed_roads.add(rid)
                self.roads[rid].closed = True
                # redistribute to sibling roads at both endpoints
                for jid in (self.roads[rid].a, self.roads[rid].b):
                    sibs = [r for r in self._junction_incoming(jid) if r != rid and r not in self.closed_roads]
                    for s in sibs:
                        self.roads[s].closed_redist += 0.5 / max(1, len(sibs))
            elif rid in self.roads:
                self.closed_roads.discard(rid)
                self.roads[rid].closed = False
                for r in self.roads.values():
                    r.closed_redist = 0.0
                # recompute redistribution for remaining closures
                for cr in self.closed_roads:
                    for jid in (self.roads[cr].a, self.roads[cr].b):
                        sibs = [r for r in self._junction_incoming(jid) if r != cr and r not in self.closed_roads]
                        for s in sibs:
                            self.roads[s].closed_redist += 0.5 / max(1, len(sibs))

    def set_weather(self, w):
        with self.lock:
            self.weather = w

    def set_event(self, active):
        with self.lock:
            self.event_active = active

    def set_signal_override(self, jid, mode):
        with self.lock:
            if mode in (None, "default"):
                self.signal_overrides.pop(jid, None)
                sig = self.signal_net.signals.get(jid)
                if sig:
                    sig.mode = "adaptive"  # revert to AI control when override clears
            else:
                self.signal_overrides[jid] = {"mode": mode}

    # ------------------------------------------------------------------ snapshot
    def snapshot(self):
        with self.lock:
            roads = {rid: {"name": r.name, "a": r.a, "b": r.b,
                           "congestion": round(r.congestion * 100, 1),
                           "vehicles": round(r.vehicles, 1),
                           "speed": round(r.speed, 1),
                           "closed": r.closed}
                     for rid, r in self.roads.items()}
            junctions = {}
            for jid, jd in config.JUNCTIONS.items():
                sig = self.signal_net.signals[jid]
                incoming = self._junction_incoming(jid)
                cong = sum(self.roads[r].congestion for r in incoming) / max(1, len(incoming)) * 100
                junctions[jid] = {
                    "id": jid, "name": jd["name"], "x": jd["x"], "y": jd["y"],
                    "lat": jd["lat"], "lng": jd["lng"],
                    "note": jd["note"], "priority": jd["priority"],
                    "congestion": round(cong, 1),
                    "signal": sig.snapshot({ax: sum(self.roads[r].congestion * 22 for r in rids)
                                            for ax, rids in config.PHASE_ROADS[jid].items()}),
                    "camera": f"CAM-{jid[:3].upper()}-{jd['priority']:02d}",
                }
            buses = []
            for b in self.buses:
                road = self.roads.get(self._road_between(b.from_j, b.to_j))
                ja, jb = config.JUNCTIONS[b.from_j], config.JUNCTIONS[b.to_j]
                x = ja["x"] + (jb["x"] - ja["x"]) * b.progress
                y = ja["y"] + (jb["y"] - ja["y"]) * b.progress
                lat = ja["lat"] + (jb["lat"] - ja["lat"]) * b.progress
                lng = ja["lng"] + (jb["lng"] - ja["lng"]) * b.progress
                next_stop = config.JUNCTIONS[b.to_j]["name"]
                seg_len = self._segment_len(b.from_j, b.to_j)
                # schematic segment ~ seg_len*10 m; km = seg_len/100
                speed_kmh = road.speed if road else 25.0
                eta = ((1 - b.progress) * seg_len / 100.0) / max(speed_kmh, 8.0) * 60.0
                buses.append({"id": b.id, "route": b.route,
                              "route_name": config.BUS_ROUTES[b.route]["name"],
                              "from": b.from_j, "to": b.to_j, "x": round(x), "y": round(y),
                              "lat": round(lat, 6), "lng": round(lng, 6),
                              "next_stop": next_stop, "eta_min": max(1, round(eta)),
                              "delay_min": round(b.delay_min, 1),
                              "occupancy": b.occupancy, "speed": round(speed_kmh, 1)})
            parking = {pid: {"name": config.PARKING_LOTS[pid]["name"],
                             "occupied": lot["occupied"], "total": lot["total"],
                             "free": lot["total"] - lot["occupied"],
                             "pct": round(lot["occupied"] / lot["total"] * 100, 1),
                             "x": config.PARKING_LOTS[pid]["x"], "y": config.PARKING_LOTS[pid]["y"],
                             "lat": config.PARKING_LOTS[pid]["lat"], "lng": config.PARKING_LOTS[pid]["lng"]}
                       for pid, lot in self.parking.items()}
            city_cong = round(sum(r["congestion"] for r in roads.values()) / len(roads), 1)
            waits = [(s.wait_ema["ns"] + s.wait_ema["ew"]) / 2 for s in self.signal_net.signals.values()]
            fixed_waits = [(s.fixed_wait_ema["ns"] + s.fixed_wait_ema["ew"]) / 2 for s in self.signal_net.signals.values()]
            kpis = {
                "city_congestion": city_cong,
                "vehicles_today": int(self.vehicles_today),
                "avg_wait_adaptive": round(sum(waits) / len(waits), 1),
                "avg_wait_fixed": round(sum(fixed_waits) / len(fixed_waits), 1),
                "wait_reduction_pct": round((1 - (sum(waits) / max(1e-6, sum(fixed_waits)))) * 100, 1),
                "buses_active": len(self.buses),
                "weather": self.weather,
                "event": self.active_event["name"] if self.active_event else ("What-if event mode" if self.event_active else None),
                "closed_roads": [self.roads[r].name for r in self.closed_roads],
                "cameras_online": len(config.JUNCTIONS),
                "time": self.sim_time.isoformat(timespec="seconds"),
            }
            return {"roads": roads, "junctions": junctions, "buses": buses,
                    "parking": parking, "kpis": kpis,
                    "emergency": self.signal_net.snapshot()}

    def history_tail(self, minutes=180):
        with self.lock:
            return self.history[-minutes:]


# singleton
simulator = CitySimulator()
