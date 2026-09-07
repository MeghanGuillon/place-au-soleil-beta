"""Diagnostic temporaire : inspecte la géométrie officielle du Réseau Ferré National."""
import json
import urllib.request

DATASETS = [
    "fichier-de-formes-des-voies-du-reseau-ferre-national",
    "formes-des-lignes-du-rfn",
]
BASE = "https://ressources.data.sncf.com/api/explore/v2.1/catalog/datasets"


def get_json(url):
    req = urllib.request.Request(url, headers={"User-Agent": "place-au-soleil/1.0"})
    with urllib.request.urlopen(req, timeout=120) as response:
        return json.load(response)


def describe_geometry(value, indent=""):
    if not isinstance(value, dict):
        return
    if value.get("type") == "Feature" and isinstance(value.get("geometry"), dict):
        geom = value["geometry"]
        print(indent + "GeoJSON Feature ->", geom.get("type"))
        print(indent + "Coordinate sample:", str(geom.get("coordinates"))[:800])
        return
    if "coordinates" in value:
        print(indent + "Geometry ->", value.get("type"))
        print(indent + "Coordinate sample:", str(value.get("coordinates"))[:800])


def main():
    for dataset in DATASETS:
        print("\n===", dataset, "===")
        meta = get_json(f"{BASE}/{dataset}")
        print("Dataset:", meta.get("dataset_id"))
        print("Fields:")
        for field in meta.get("fields", []):
            print(" -", field.get("name"), "|", field.get("type"), "|", field.get("label"))

        records = get_json(f"{BASE}/{dataset}/records?limit=2")
        print("Total records:", records.get("total_count"))
        for i, record in enumerate(records.get("results", []), 1):
            print(f"Record {i} keys:", sorted(record.keys()))
            for key, value in record.items():
                if key in {"geo_shape", "geometry"}:
                    print(" Geometry field:", key)
                    describe_geometry(value, "  ")
                elif key.lower() in {
                    "type_voie", "code_ligne", "libelle", "mnemo", "rg_troncon",
                    "ligne", "nom_voie", "idgaia"
                }:
                    print(f" {key}:", value)


if __name__ == "__main__":
    main()
