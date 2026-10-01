"""RaipurNetra AI - Raipur-specific configuration.

Real junctions, roads, bus routes, parking lots and RTO data used by the
simulation engine, prediction models and TrafficGPT bot.
"""

import random
import datetime

# ---------------------------------------------------------------------------
# Junctions (schematic x,y for SVG twin + real lat/lng for Leaflet map)
# ---------------------------------------------------------------------------
JUNCTIONS = {
    "jaistambh":  {"name": "Jaistambh Chowk",       "x": 500, "y": 350, "lat": 21.2514, "lng": 81.6296, "note": "Highest traffic density - city center", "phase1": 47000, "priority": 1},
    "pandri":     {"name": "Pandri Chowk",          "x": 460, "y": 170, "lat": 21.2470, "lng": 81.6420, "note": "Bus terminal + market area",            "phase1": 42000, "priority": 1},
    "pachpedi":   {"name": "Pachpedi Naka",         "x": 610, "y": 245, "lat": 21.2358, "lng": 81.6322, "note": "GE Road corridor gateway",              "phase1": 38000, "priority": 2},
    "mowa":       {"name": "Mowa Chowk",            "x": 690, "y": 130, "lat": 21.2650, "lng": 81.6580, "note": "Gateway to Naya Raipur",                "phase1": 30000, "priority": 2},
    "bhatagaon":  {"name": "Bhatagaon Chowk",       "x": 320, "y": 120, "lat": 21.2780, "lng": 81.6290, "note": "North residential corridor",            "phase1": 26000, "priority": 3},
    "shankar":    {"name": "Shankar Nagar Chowk",   "x": 255, "y": 265, "lat": 21.2600, "lng": 81.6200, "note": "Education hub",                         "phase1": 28000, "priority": 2},
    "telibandha": {"name": "Telibandha Square",     "x": 735, "y": 335, "lat": 21.2407, "lng": 81.6601, "note": "Commercial hub",                        "phase1": 36000, "priority": 1},
    "marine":     {"name": "Marine Drive Crossing", "x": 845, "y": 425, "lat": 21.2380, "lng": 81.6650, "note": "VIP route along Telibandha lake",       "phase1": 24000, "priority": 1},
    "vip":        {"name": "VIP Road Junction",     "x": 705, "y": 525, "lat": 21.2300, "lng": 81.6720, "note": "Atal Nagar / Naya Raipur link",         "phase1": 32000, "priority": 2},
    "fafadih":    {"name": "Fafadih Chowk",         "x": 350, "y": 480, "lat": 21.2360, "lng": 81.6200, "note": "Accident-prone, industrial access",     "phase1": 34000, "priority": 1},
    "amlidih":    {"name": "Amlidih Chowk",         "x": 545, "y": 600, "lat": 21.2260, "lng": 81.6450, "note": "South residential + retail",            "phase1": 27000, "priority": 3},
    "devnagar":   {"name": "Devendra Nagar",        "x": 375, "y": 620, "lat": 21.2290, "lng": 81.6250, "note": "South-west residential",                "phase1": 22000, "priority": 3},
}

# ---------------------------------------------------------------------------
# Roads: id -> (from_junction, to_junction, display_name, capacity veh/hr/lane-dir, lanes)
# ---------------------------------------------------------------------------
ROADS = {
    "mg_road":        ("jaistambh", "telibandha", "MG Road",                1600, 2),
    "jail_road":      ("jaistambh", "fafadih",    "Jail Road",              1400, 2),
    "ge_road_s":      ("jaistambh", "pachpedi",   "GE Road (South)",        1800, 3),
    "ge_road_n":      ("pachpedi",  "mowa",       "GE Road (North)",        1600, 2),
    "pandri_road":    ("jaistambh", "pandri",     "Pandri Road",            1500, 2),
    "bhatagaon_road": ("pandri",    "bhatagaon",  "Bhatagaon Road",         1200, 2),
    "kachna_road":    ("pandri",    "pachpedi",   "Kachna Road",            1000, 1),
    "shankar_road":   ("jaistambh", "shankar",    "Shankar Nagar Road",     1300, 2),
    "ring_west":      ("shankar",   "fafadih",    "Ring Road 1 (West)",     1500, 2),
    "ring_south":     ("fafadih",   "amlidih",    "Ring Road 1 (South)",    1400, 2),
    "amlidih_link":   ("amlidih",   "vip",        "Amlidih Link Road",      1200, 2),
    "marine_road":    ("telibandha","marine",     "Marine Drive Road",      1400, 2),
    "vip_road":       ("telibandha","vip",        "VIP Road",               1600, 3),
    "ring_southeast": ("marine",    "vip",        "Ring Road 1 (SE)",       1400, 2),
    "ring_east":      ("pachpedi",  "telibandha", "Ring Road 1 (East)",     1300, 2),
    "devnagar_road":  ("fafadih",   "devnagar",   "Devendra Nagar Road",    1000, 1),
    "gudhiyari_road": ("devnagar",  "amlidih",    "Gudhiyari Road",         1000, 1),
}

# Adjacency for routing (undirected, road weights + closure aware)
JUNCTION_ROADS = {}
for rid, (a, b, name, cap, lanes) in ROADS.items():
    JUNCTION_ROADS.setdefault(a, []).append(rid)
    JUNCTION_ROADS.setdefault(b, []).append(rid)

# Phase axis for each junction (which roads belong to the N-S / E-W green phase)
PHASE_ROADS = {
    "jaistambh":  {"ns": ["pandri_road"],                       "ew": ["mg_road", "ge_road_s"]},
    "pandri":     {"ns": ["pandri_road"],                       "ew": ["bhatagaon_road", "kachna_road"]},
    "pachpedi":   {"ns": ["ge_road_s"],                         "ew": ["ring_east", "kachna_road"]},
    "mowa":       {"ns": ["ge_road_n"],                         "ew": []},
    "bhatagaon":  {"ns": ["bhatagaon_road"],                    "ew": []},
    "shankar":    {"ns": ["shankar_road"],                      "ew": ["ring_west"]},
    "telibandha": {"ns": ["mg_road"],                           "ew": ["marine_road", "vip_road"]},
    "marine":     {"ns": ["marine_road"],                       "ew": ["ring_southeast"]},
    "vip":        {"ns": ["vip_road"],                          "ew": ["ring_southeast", "amlidih_link"]},
    "fafadih":    {"ns": ["jail_road"],                         "ew": ["ring_west", "ring_south"]},
    "amlidih":    {"ns": ["ring_south"],                        "ew": ["amlidih_link"]},
    "devnagar":   {"ns": ["devnagar_road"],                     "ew": ["gudhiyari_road"]},
}

# ---------------------------------------------------------------------------
# City buses (Raipur City Bus / Atal Nagar routes)
# ---------------------------------------------------------------------------
BUS_ROUTES = {
    "R1": {"name": "GE Road Corridor",  "path": ["pandri", "jaistambh", "pachpedi", "mowa"]},
    "R2": {"name": "City Loop",         "path": ["jaistambh", "telibandha", "marine", "vip", "amlidih", "fafadih", "jaistambh"]},
    "R3": {"name": "North-South Link",  "path": ["bhatagaon", "pandri", "jaistambh", "fafadih", "devnagar"]},
}

BUSES = [
    {"id": "CG-04-B-2101", "route": "R1", "schedule_min": 12},
    {"id": "CG-04-B-2102", "route": "R1", "schedule_min": 12},
    {"id": "CG-04-B-2103", "route": "R1", "schedule_min": 12},
    {"id": "CG-04-B-2201", "route": "R2", "schedule_min": 15},
    {"id": "CG-04-B-2202", "route": "R2", "schedule_min": 15},
    {"id": "CG-04-B-2203", "route": "R2", "schedule_min": 15},
    {"id": "CG-04-B-2301", "route": "R3", "schedule_min": 18},
    {"id": "CG-04-B-2302", "route": "R3", "schedule_min": 18},
]

# ---------------------------------------------------------------------------
# Smart parking locations (CV-based occupancy on existing CCTV)
# ---------------------------------------------------------------------------
PARKING_LOTS = {
    "magneto":    {"name": "Magneto Mall",            "total": 220, "x": 640, "y": 300, "lat": 21.2523, "lng": 81.6795},
    "citycenter": {"name": "City Center Mall",        "total": 150, "x": 560, "y": 380, "lat": 21.2440, "lng": 81.6560},
    "pandri":     {"name": "Pandri Market",           "total": 120, "x": 445, "y": 140, "lat": 21.2478, "lng": 81.6410},
    "ambedkar":   {"name": "Ambedkar Hospital",       "total": 90,  "x": 420, "y": 300, "lat": 21.2440, "lng": 81.6280},
    "railway":    {"name": "Raipur Railway Station",  "total": 160, "x": 330, "y": 340, "lat": 21.2497, "lng": 81.6286},
}

# ---------------------------------------------------------------------------
# Events calendar (drives prediction + event-aware alerts)
# ---------------------------------------------------------------------------
EVENTS = [
    {"date": "2026-09-28", "name": "Bastar Dussehra processions",  "impact": 1.35, "area": "jaistambh"},
    {"date": "2026-10-02", "name": "Gandhi Jayanti rallies",       "impact": 1.30, "area": "jaistambh"},
    {"date": "2026-10-15", "name": "Cricket match - Shaheed Veer Narayan Singh Stadium", "impact": 1.40, "area": "pachpedi"},
    {"date": "2026-11-08", "name": "Rajim Kumbh Kalpa",            "impact": 1.25, "area": "vip"},
]

# ---------------------------------------------------------------------------
# RTO vehicle owner database (simulated, CG plates)
# ---------------------------------------------------------------------------
_RTO_SEED = random.Random(42)
_OWNER_NAMES = [
    "Rahul Sharma", "Priya Verma", "Amit Sahu", "Sneha Jain", "Vikas Chandrakar",
    "Neha Agrawal", "Suresh Patel", "Kavita Dewangan", "Rajesh Tiwari", "Pooja Xalxo",
    "Manish Sinha", "Anjali Sahu", "Deepak Kosaria", "Rekha Baghel", "Sanjay Netam",
    "Arti Portrait", "Gopal Bohra", "Meena Xess", "Tarun Pandey", "Swati Rao",
]
_VEHICLE_TYPES = ["car", "bike", "auto", "truck", "bus"]


def _gen_plate(rng):
    district = rng.choice(["CG-04"])  # Raipur RTO
    letters = "".join(rng.choice("ABCDEFGHJKLMNPRSTUVWXYZ") for _ in range(2))
    number = rng.randint(1, 9999)
    return f"{district}-{letters}-{number:04d}"


def build_rto_database(n=400):
    """plate -> owner record."""
    rng = random.Random(2026)
    db = {}
    for _ in range(n):
        plate = _gen_plate(rng)
        if plate in db:
            continue
        vtype = rng.choices(_VEHICLE_TYPES, weights=[38, 40, 14, 5, 3])[0]
        db[plate] = {
            "plate": plate,
            "owner": _RTO_SEED.choice(_OWNER_NAMES),
            "vehicle_type": vtype,
            "model": rng.choice(["Alto", "Swift", "Splendor", "Activa", "Bajaj RE", "Bolero", "Creta", "Apache", "E-rickshaw", "City"]),
            "rto": "CG-04 Raipur",
            "challans_pending": rng.choices([0, 0, 0, 1, 2], weights=[70, 10, 10, 6, 4])[0],
        }
    return db


RTO_DB = build_rto_database()


# ---------------------------------------------------------------------------
# Hackathon metadata
# ---------------------------------------------------------------------------
TEAM = ["Akshita", "Pratik Raj", "Ayush Kumar", "Prince"]
EVENT_META = {
    "name": "Raipur Traffic Hackathon 2026",
    "theme": "Infusion of AI/IoT in Traffic Management",
    "organizers": "Raipur Police Commissionerate | IEI CG State Centre | NIT Raipur",
}

FINE_AMOUNTS = {"red_light": 1000, "no_helmet": 500, "wrong_way": 500, "overspeed": 800}
VIOLATION_LABELS = {
    "red_light": "Red Light Jumping",
    "no_helmet": "No Helmet",
    "wrong_way": "Wrong Way Driving",
    "overspeed": "Over-Speeding",
}
IST = datetime.timezone(datetime.timedelta(hours=5, minutes=30), name="IST")
