"""Diagnostic ciblé du train 6605 Paris Gare de Lyon -> Lyon Part Dieu."""
import hashlib
import json
import os

ROOT = os.path.join(os.path.dirname(__file__), "..", "data")
DATE = "2026-09-06"
TRAIN_NUMBER = "6605"
FROM_NAME = "Paris Gare de Lyon Hall 1 - 2"
TO_NAME = "Lyon Part Dieu"


def pair_key(a, b):
    return "|".join(sorted((str(a), str(b))))


def shard_for(key):
    return hashlib.sha1(key.encode("utf-8")).hexdigest()[0]


with open(os.path.join(ROOT, "stations.json"), encoding="utf-8") as f:
    stations = json.load(f)["stations"]
by_name = {s["name"]: s for s in stations}
by_id = {str(s["id"]): s for s in stations}
start_id = str(by_name[FROM_NAME]["id"])
end_id = str(by_name[TO_NAME]["id"])

with open(os.path.join(ROOT, "dates", DATE + ".json"), encoding="utf-8") as f:
    trains = json.load(f)["trains"]

matches = []
for t in trains:
    if str(t.get("n", "")) != TRAIN_NUMBER:
        continue
    ids = [str(s[0]) for s in t.get("s", [])]
    if start_id in ids and end_id in ids and ids.index(start_id) < ids.index(end_id):
        matches.append((t, ids.index(start_id), ids.index(end_id)))

print(f"Matches train {TRAIN_NUMBER}: {len(matches)}")
for t, i, j in matches:
    print(f"Trip: {t.get('id')}")
    section = t["s"][i:j+1]
    for n, stop in enumerate(section):
        sid = str(stop[0])
        print(f"  STOP {n}: {sid} | {by_id.get(sid, {}).get('name')} | arr={stop[1]} dep={stop[2]}")
    for a, b in zip(section, section[1:]):
        a_id, b_id = str(a[0]), str(b[0])
        key = pair_key(a_id, b_id)
        shard = shard_for(key)
        path = os.path.join(ROOT, "segments", shard + ".json")
        payload = {}
        if os.path.exists(path):
            with open(path, encoding="utf-8") as f:
                payload = json.load(f)
        print(f"  PAIR: {by_id.get(a_id, {}).get('name')} -> {by_id.get(b_id, {}).get('name')}")
        print(f"    ids={a_id} -> {b_id}")
        print(f"    key={key} shard={shard} present={key in payload}")
        if key in payload:
            print(f"    geometry_points={len(payload[key])}")
