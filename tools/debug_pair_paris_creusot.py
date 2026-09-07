"""Diagnostic RFN ciblé Paris Gare de Lyon -> Le Creusot TGV."""
import importlib.util
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..")
DATA = os.path.join(ROOT, "data")
SPEC = importlib.util.spec_from_file_location("bg", os.path.join(ROOT, "scripts", "build_geometry.py"))
bg = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(bg)

A = "StopArea:OCE87686006"
B = "StopArea:OCE87694109"

with open(os.path.join(DATA, "stations.json"), encoding="utf-8") as f:
    stations = {str(s["id"]): (float(s["lon"]), float(s["lat"])) for s in json.load(f)["stations"]}

print("Station A", A, stations[A])
print("Station B", B, stations[B])
records = bg.fetch_rfn()
graph = bg.build_graph(records)
grid, cell = bg.build_grid(graph.keys())
sa = bg.snap(stations[A], grid, cell)
sb = bg.snap(stations[B], grid, cell)
print("Snap A", sa)
print("Snap B", sb)
straight = bg.haversine(stations[A], stations[B])
print("Straight km", straight)
if sa[0] is not None and sb[0] is not None:
    path, km = bg.astar(graph, sa[0], sb[0])
    print("Path found", bool(path))
    print("Path km", km)
    print("Path nodes", len(path) if path else 0)
    if km is not None:
        print("Ratio", km / straight if straight else None)
        print("Lower limit", straight * 0.88)
        print("Upper limit", max(straight * 3.5, straight + 80))
        print("Would reject", straight > 1 and (km < straight * 0.88 or km > max(straight * 3.5, straight + 80)))
