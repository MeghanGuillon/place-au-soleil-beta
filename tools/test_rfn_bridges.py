"""Teste des ponts conservateurs entre extrémités RFN proches sur Paris -> Le Creusot."""
import importlib.util
import json
import math
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

graph = bg.build_graph(bg.fetch_rfn())

def add_bridges(graph, max_km=0.12):
    endpoints = [n for n, links in graph.items() if len(links) == 1]
    cell = 0.003
    grid = {}
    for n in graph:
        k=(math.floor(n[0]/cell),math.floor(n[1]/cell))
        grid.setdefault(k,[]).append(n)
    added=0
    samples=[]
    for e in endpoints:
        bx,by=math.floor(e[0]/cell),math.floor(e[1]/cell)
        best=None; best_d=max_km
        current=set(graph[e])
        for dx in (-1,0,1):
            for dy in (-1,0,1):
                for n in grid.get((bx+dx,by+dy),[]):
                    if n==e or n in current: continue
                    d=bg.haversine(e,n)
                    if 0.003 < d < best_d:
                        best,best_d=n,d
        if best is not None:
            graph[e][best]=best_d
            graph[best][e]=best_d
            added+=1
            if len(samples)<10: samples.append((e,best,best_d))
    print("Bridges added",added,"of endpoints",len(endpoints))
    print("Bridge samples",samples)

add_bridges(graph)
grid,cell=bg.build_grid(graph.keys())
sa=bg.snap(stations[A],grid,cell); sb=bg.snap(stations[B],grid,cell)
print("Snaps",sa,sb)
path,km=bg.astar(graph,sa[0],sb[0])
straight=bg.haversine(stations[A],stations[B])
print("Straight",straight,"Route",km,"Ratio",km/straight if km else None,"Nodes",len(path) if path else 0)
