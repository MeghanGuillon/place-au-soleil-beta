"""Construit un index national SNCF léger pour Place au Soleil.

Sorties :
- data/stations.json : gares canoniques + coordonnées
- data/manifest.json : dates disponibles
- data/dates/YYYY-MM-DD.json : trains de la journée, avec arrêts et horaires
"""
import io
import json
import os
import re
import shutil
import zipfile
from collections import Counter, defaultdict
from datetime import datetime, timedelta, timezone

import pandas as pd
import requests

GTFS_URL = "https://eu.ftp.opendatasoft.com/sncf/plandata/Export_OpenData_SNCF_GTFS_NewTripId.zip"
ROOT = os.path.join(os.path.dirname(__file__), "..", "data")
DATES_DIR = os.path.join(ROOT, "dates")
DATE_RE = re.compile(r"(20\d{6})(?!.*20\d{6})")
DAYS = ["monday", "tuesday", "wednesday", "thursday", "friday", "saturday", "sunday"]


def download_gtfs():
    print("Téléchargement du GTFS national SNCF…")
    r = requests.get(GTFS_URL, timeout=180)
    r.raise_for_status()
    print(f"  {len(r.content)/1e6:.1f} Mo")
    return zipfile.ZipFile(io.BytesIO(r.content))


def gtfs_date(value):
    try:
        return datetime.strptime(str(value), "%Y%m%d").date()
    except (TypeError, ValueError):
        return None


def extract_date(*values):
    """Secours pour les flux SNCF qui encodent directement la date dans un identifiant."""
    for value in values:
        if value is None or pd.isna(value):
            continue
        m = DATE_RE.search(str(value))
        if m:
            d = gtfs_date(m.group(1))
            if d:
                return d.isoformat()
    return None


def build_service_dates(zf):
    """Construit service_id -> dates selon calendar.txt + calendar_dates.txt."""
    service_dates = defaultdict(set)
    names = set(zf.namelist())
    used = []

    if "calendar.txt" in names:
        with zf.open("calendar.txt") as f:
            calendar = pd.read_csv(f, dtype=str)
        for row in calendar.itertuples(index=False):
            d = row._asdict()
            service_id = str(d.get("service_id", ""))
            start = gtfs_date(d.get("start_date"))
            end = gtfs_date(d.get("end_date"))
            if not service_id or not start or not end:
                continue
            current = start
            while current <= end:
                day_key = DAYS[current.weekday()]
                if str(d.get(day_key, "0")) == "1":
                    service_dates[service_id].add(current.isoformat())
                current += timedelta(days=1)
        used.append("calendar.txt")

    if "calendar_dates.txt" in names:
        with zf.open("calendar_dates.txt") as f:
            exceptions = pd.read_csv(f, dtype=str)
        for row in exceptions.itertuples(index=False):
            d = row._asdict()
            service_id = str(d.get("service_id", ""))
            date = gtfs_date(d.get("date"))
            exception = str(d.get("exception_type", ""))
            if not service_id or not date:
                continue
            iso = date.isoformat()
            if exception == "1":
                service_dates[service_id].add(iso)
            elif exception == "2":
                service_dates[service_id].discard(iso)
        used.append("calendar_dates.txt")

    print("Calendrier GTFS : " + (" + ".join(used) if used else "absent, secours par identifiants"))
    print(f"Services calendaires : {len(service_dates)}")
    return service_dates, used


def canonical_stations(stops):
    stops = stops.copy()
    if "parent_station" not in stops.columns:
        stops["parent_station"] = ""
    stops["canonical_id"] = stops["parent_station"].fillna("").where(
        stops["parent_station"].fillna("") != "", stops["stop_id"]
    ).astype(str)

    by_id = stops.set_index("stop_id", drop=False)
    station_rows = []
    stop_to_station = {}

    for cid, group in stops.groupby("canonical_id", sort=False):
        stop_to_station.update({str(x): str(cid) for x in group["stop_id"]})
        parent = by_id.loc[cid] if cid in by_id.index else None
        if isinstance(parent, pd.DataFrame):
            parent = parent.iloc[0]

        if parent is not None:
            name = str(parent.get("stop_name") or "").strip()
            lat = parent.get("stop_lat")
            lon = parent.get("stop_lon")
        else:
            names = [str(x).strip() for x in group["stop_name"].dropna() if str(x).strip()]
            name = Counter(names).most_common(1)[0][0] if names else str(cid)
            lat = pd.to_numeric(group.get("stop_lat"), errors="coerce").mean()
            lon = pd.to_numeric(group.get("stop_lon"), errors="coerce").mean()

        if pd.isna(lat) or pd.isna(lon):
            continue
        station_rows.append({"id": str(cid), "name": name, "lat": float(lat), "lon": float(lon)})

    station_rows.sort(key=lambda x: x["name"].lower())
    return station_rows, stop_to_station


def train_kind(trip_id):
    text = str(trip_id).upper()
    for key in ("TGV", "TER", "IC", "INTERCITES"):
        if f":{key}:" in text or f"_{key}:" in text:
            return "Intercités" if key in ("IC", "INTERCITES") else key
    return "Train"


def train_number(raw, trip_id):
    value = str(raw or "").strip()
    if value and value.lower() != "nan":
        return value
    m = re.match(r"OCESN(\d+)", str(trip_id), re.IGNORECASE)
    return m.group(1) if m else ""


def main():
    zf = download_gtfs()
    with zf.open("stops.txt") as f:
        stops = pd.read_csv(f, dtype=str)
    with zf.open("trips.txt") as f:
        trips = pd.read_csv(f, dtype=str)

    service_dates, calendar_sources = build_service_dates(zf)

    stations, stop_to_station = canonical_stations(stops)
    station_ids = {s["id"] for s in stations}
    print(f"Gares canoniques : {len(stations)}")

    meta = {}
    has_short = "trip_short_name" in trips.columns
    fallback_count = 0
    for row in trips.itertuples(index=False):
        d = row._asdict()
        trip_id = str(d.get("trip_id", ""))
        service_id = str(d.get("service_id", ""))
        dates = sorted(service_dates.get(service_id, set()))
        if not dates:
            fallback = extract_date(trip_id, service_id)
            if fallback:
                dates = [fallback]
                fallback_count += 1
        if not dates:
            continue
        meta[trip_id] = {
            "dates": dates,
            "number": train_number(d.get("trip_short_name", "") if has_short else "", trip_id),
            "kind": train_kind(trip_id),
        }
    print(f"Trips avec dates de circulation : {len(meta)}")
    print(f"Trips utilisant le secours par identifiant : {fallback_count}")

    wanted = set(meta)
    cols = ["trip_id", "stop_id", "stop_sequence", "arrival_time", "departure_time"]
    pieces = []
    print("Lecture de stop_times.txt…")
    with zf.open("stop_times.txt") as f:
        for chunk in pd.read_csv(f, dtype=str, usecols=cols, chunksize=500_000):
            hit = chunk[chunk["trip_id"].isin(wanted)]
            if not hit.empty:
                pieces.append(hit)
    if not pieces:
        raise RuntimeError("Aucun stop_time exploitable n'a été trouvé.")

    times = pd.concat(pieces, ignore_index=True)
    times["stop_sequence"] = pd.to_numeric(times["stop_sequence"], errors="coerce")
    times = times.dropna(subset=["stop_sequence"]).sort_values(["trip_id", "stop_sequence"])

    by_date = {}
    kept_trips = 0
    circulations = 0
    for trip_id, group in times.groupby("trip_id", sort=False):
        info = meta.get(str(trip_id))
        if not info:
            continue
        stops_out = []
        previous = None
        for row in group.itertuples(index=False):
            cid = stop_to_station.get(str(row.stop_id))
            if not cid or cid not in station_ids:
                continue
            if cid == previous:
                if stops_out:
                    stops_out[-1][1] = str(row.arrival_time or stops_out[-1][1])
                    stops_out[-1][2] = str(row.departure_time or stops_out[-1][2])
                continue
            stops_out.append([cid, str(row.arrival_time or ""), str(row.departure_time or "")])
            previous = cid
        if len(stops_out) < 2:
            continue

        obj = {
            "id": str(trip_id),
            "n": info["number"],
            "k": info["kind"],
            "s": stops_out,
        }
        for date in info["dates"]:
            by_date.setdefault(date, []).append(obj)
            circulations += 1
        kept_trips += 1

    print(f"Trips conservés : {kept_trips}")
    print(f"Circulations datées générées : {circulations}")
    os.makedirs(ROOT, exist_ok=True)
    if os.path.isdir(DATES_DIR):
        shutil.rmtree(DATES_DIR)
    os.makedirs(DATES_DIR, exist_ok=True)

    with open(os.path.join(ROOT, "stations.json"), "w", encoding="utf-8") as f:
        json.dump({"stations": stations}, f, ensure_ascii=False, separators=(",", ":"))

    manifest_dates = []
    for date, trains in sorted(by_date.items()):
        path = os.path.join(DATES_DIR, f"{date}.json")
        with open(path, "w", encoding="utf-8") as f:
            json.dump({"date": date, "trains": trains}, f, ensure_ascii=False, separators=(",", ":"))
        manifest_dates.append({"date": date, "count": len(trains)})

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": "SNCF Open Data — Licence Ouverte Etalab 2.0",
        "calendar_sources": calendar_sources,
        "dates": manifest_dates,
    }
    with open(os.path.join(ROOT, "manifest.json"), "w", encoding="utf-8") as f:
        json.dump(manifest, f, ensure_ascii=False, indent=2)

    print(f"Dates générées : {len(manifest_dates)}")
    if manifest_dates:
        print(f"Période : {manifest_dates[0]['date']} → {manifest_dates[-1]['date']}")


if __name__ == "__main__":
    main()
