"""RaipurNetra AI - congestion-aware routing over the Raipur road graph."""

import heapq

from . import config


def _road_weight(roads_state, rid):
    rd = roads_state[rid]
    if rd["closed"]:
        return float("inf")
    # travel time proxy: distance / speed, penalised by congestion
    return 1.0 + (rd["congestion"] / 100.0) * 3.0


def shortest_path(from_j, to_j, roads_state):
    """Dijkstra over junction graph with live congestion weights.
    Returns (junction_path, road_path, total_cost) or None."""
    if from_j not in config.JUNCTIONS or to_j not in config.JUNCTIONS:
        return None
    adj = {}
    for rid, rd in roads_state.items():
        a, b = rd["a"], rd["b"]
        w = _road_weight(roads_state, rid)
        adj.setdefault(a, []).append((b, rid, w))
        adj.setdefault(b, []).append((a, rid, w))
    dist = {from_j: 0.0}
    prev = {}
    pq = [(0.0, from_j)]
    while pq:
        d, u = heapq.heappop(pq)
        if u == to_j:
            break
        if d > dist.get(u, float("inf")):
            continue
        for v, rid, w in adj.get(u, []):
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = (u, rid)
                heapq.heappush(pq, (nd, v))
    if to_j not in dist:
        return None
    path, rpath = [to_j], []
    cur = to_j
    while cur != from_j:
        p, rid = prev[cur]
        rpath.append(rid)
        path.append(p)
        cur = p
    path.reverse()
    rpath.reverse()
    return path, rpath, dist[to_j]


def route_eta_minutes(roads_state, road_path):
    total = 0.0
    for rid in road_path:
        rd = roads_state[rid]
        speed = max(8.0, rd["speed"])
        total += 1.2 / speed * 60.0  # schematic 1.2 km per road segment
    return max(2, round(total))


def hops(from_j, to_j):
    """Static hop distance (for ride matching zone similarity)."""
    roads_state = {rid: {"a": a, "b": b, "closed": False, "congestion": 20.0, "speed": 40.0}
                   for rid, (a, b, *_rest) in config.ROADS.items()}
    r = shortest_path(from_j, to_j, roads_state)
    return len(r[0]) - 1 if r else 9
