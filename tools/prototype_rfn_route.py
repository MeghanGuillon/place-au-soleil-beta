"""Prototype de routage ferroviaire RFN pour Place au Soleil.

But : relier Paris Montparnasse à Rennes sur la géométrie officielle des lignes
SNCF Réseau, sans modifier les données de production.
"""
import heapq
import json
import math
import os
import urllib.parse
import urllib.request
from collections import defaultdict

DATASET = "formes-des-lignes-du-rfn"
BASE = "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets"
ROOT = os.path.join(os.path.dirname(__file__), "..")
STATIONS_PATH = os.path.join(ROOT, "data", "stations.json")
OUT_DIR = os.path.join(ROOT, "data", "debug")
OUT_PATH = os.path.join(OUT_DIR, "paris-rennes-route.json")

START_NAME = "Paris Montparnasse Hall 1 - 2"
END_NAME = "Rennes"

# Une clé à 5 décimales vaut environ 1 m en latitude. Cela recolle les tronçons
# qui partagent le même nœud tout en conservant la géométrie fine.
def node_key(lon, lat):
    return (round(float(lon), 5), round(float(lat), 5))


def haversine(a, b):
    lon1, lat1 = a
    lon2, lat2 = b
    r = 6371.0088
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp = math.radians(lat2 - lat1)
    dl = math.radians(lon2 - lon1)
    h = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(h))


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "place-au-soleil/1.0"})
    with urllib.request.urlopen(req, timeout=180) as response:
        return json.load(response)


def fetch_all_records():
    rows = []
    offset = 0
    limit = 100
    while True:
        query = urllib.parse.urlencode({"limit": limit, "offset": offset})
        data = get_json(f"{BASE}/{DATASET}/records?{query}")
        batch = data.get("results", [])
        rows.extend(batch)
        print(f"RFN : {len(rows)}/{data.get('total_count', '?')} tronçons")
        if not batch or len(rows) >= int(data.get("total_count", len(rows))):
            break
        offset += len(batch)
    return rows


def coordinates_from_shape(shape):
    if not isinstance(shape, dict):
        return []
    geom = shape.get("geometry", shape)
    kind = geom.get("type")
    coords = geom.get("coordinates") or []
    if kind == "LineString":
        return [coords]
    if kind == "MultiLineString":
        return coords
    return []


def load_station(name):
    with open(STATIONS_PATH, encoding="utf-8") as f:
        stations = json.load(f)["stations"]
    exact = [s for s in stations if s["name"] == name]
    if not exact:
        raise RuntimeError(f"Gare introuvable : {name}")
    s = exact[0]
    return (float(s["lon"]), float(s["lat"]))


def build_graph(records):
    graph = defaultdict(dict)
    point_count = 0
    used_records = 0
    for rec in records:
        # Les tronçons explicitement neutralisés ne doivent pas servir à router un train commercial.
        if str(rec.get("mnemo", "")).upper() == "NEUT" or "neutral" in str(rec.get("libelle", "")).lower():
            continue
        any_line = False
        for line in coordinates_from_shape(rec.get("geo_shape")):
            clean = []
            for p in line:
                if isinstance(p, (list, tuple)) and len(p) >= 2:
                    k = node_key(p[0], p[1])
                    if not clean or k != clean[-1]:
                        clean.append(k)
            if len(clean) < 2:
                continue
            any_line = True
            point_count += len(clean)
            for a, b in zip(clean, clean[1:]):
                d = haversine(a, b)
                if d <= 0:
                    continue
                old = graph[a].get(b)
                if old is None or d < old:
                    graph[a][b] = d
                    graph[b][a] = d
        if any_line:
            used_records += 1
    print(f"Graphe : {len(graph)} nœuds, {point_count} points, {used_records} tronçons actifs")
    return graph


def nearest_node(graph, point):
    best = None
    best_d = float("inf")
    for n in graph.keys():
        d = haversine(n, point)
        if d < best_d:
            best, best_d = n, d
    return best, best_d


def dijkstra(graph, start, goal):
    q = [(0.0, start)]
    dist = {start: 0.0}
    prev = {}
    visited = set()
    while q:
        d, u = heapq.heappop(q)
        if u in visited:
            continue
        visited.add(u)
        if u == goal:
            break
        for v, w in graph[u].items():
            nd = d + w
            if nd < dist.get(v, float("inf")):
                dist[v] = nd
                prev[v] = u
                heapq.heappush(q, (nd, v))
    if goal not in dist:
        return None, None
    path = [goal]
    while path[-1] != start:
        path.append(prev[path[-1]])
    path.reverse()
    return path, dist[goal]


def simplify(points, every=8):
    if len(points) <= 2:
        return points
    out = [points[0]]
    out.extend(points[i] for i in range(every, len(points) - 1, every))
    out.append(points[-1])
    return out


def main():
    start_pos = load_station(START_NAME)
    end_pos = load_station(END_NAME)
    print("Départ :", START_NAME, start_pos)
    print("Arrivée :", END_NAME, end_pos)

    records = fetch_all_records()
    graph = build_graph(records)
    start_node, start_snap = nearest_node(graph, start_pos)
    end_node, end_snap = nearest_node(graph, end_pos)
    print(f"Snap départ : {start_snap*1000:.0f} m")
    print(f"Snap arrivée : {end_snap*1000:.0f} m")

    path, km = dijkstra(graph, start_node, end_node)
    if not path:
        raise RuntimeError("Aucun chemin RFN continu trouvé entre Paris Montparnasse et Rennes.")

    simple = simplify(path)
    print(f"Chemin trouvé : {km:.1f} km, {len(path)} points bruts, {len(simple)} points simplifiés")
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(OUT_PATH, "w", encoding="utf-8") as f:
        json.dump({
            "from": START_NAME,
            "to": END_NAME,
            "source": "SNCF Réseau — formes des lignes du RFN",
            "distance_km": round(km, 1),
            "snap_start_m": round(start_snap * 1000),
            "snap_end_m": round(end_snap * 1000),
            "raw_points": len(path),
            "geometry": [[lon, lat] for lon, lat in simple],
        }, f, ensure_ascii=False, indent=2)
    print("Écrit :", OUT_PATH)


if __name__ == "__main__":
    main()
