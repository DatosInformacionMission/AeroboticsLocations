import requests
import json
import base64
import os
from datetime import datetime

# ── CONFIGURACIÓN ──────────────────────────────────────────────────────────────
AEROBOTICS_TOKEN = os.environ["AEROBOTICS_TOKEN"]
GITHUB_TOKEN     = os.environ["GITHUB_TOKEN"]

# Repo donde se GUARDA el resultado (AeroboticsLocations)
GITHUB_REPO_OUTPUT   = "DatosInformacionMission/AeroboticsLocations"
GITHUB_FILE_PATH     = "MaestroLotesT_combinado.json"

# Repo donde están los POLÍGONOS (MapasAzureJson) — lectura pública, no necesita token
POLIGONOS_URL = "https://raw.githubusercontent.com/DatosInformacionMission/MapasAzureJson/main/MaestroLotesT.json"

HEADERS_AERO = {
    "Authorization": f"Bearer {AEROBOTICS_TOKEN}",
    "Content-Type": "application/json"
}

HEADERS_GITHUB = {
    "Authorization": f"Bearer {GITHUB_TOKEN}",
    "Accept": "application/vnd.github+json"
}

LIST_URL   = "https://api.aerobotics.com/farming/truefruit/size/measurements/"
DETAIL_URL = "https://api.aerobotics.com/farming/truefruit/size/measurements/{orchard_id}/{measurement_date}/"

# ── PASO 1: Obtener lista de orchards y fechas ─────────────────────────────────
print("Obteniendo lista de measurements...")
response = requests.get(LIST_URL, headers=HEADERS_AERO)
response.raise_for_status()
lista = response.json()

# Por cada orchard_id quedarse con la fecha más reciente
orchards_recientes = {}
for item in lista["results"]:
    oid  = item["orchard_id"]
    date = item["measurement_date"]
    if oid not in orchards_recientes or date > orchards_recientes[oid]:
        orchards_recientes[oid] = date

print(f"  → {len(orchards_recientes)} orchards encontrados")

# ── PASO 2: Obtener sample_positions de cada orchard ──────────────────────────
print("Obteniendo sample positions por orchard...")
features_puntos = []

for orchard_id, measurement_date in orchards_recientes.items():
    url = DETAIL_URL.format(orchard_id=orchard_id, measurement_date=measurement_date)
    try:
        r = requests.get(url, headers=HEADERS_AERO)
        r.raise_for_status()
        detalle = r.json()

        for sp in detalle.get("sample_positions", []):
            feature = {
                "type": "Feature",
                "geometry": {
                    "type": "Point",
                    "coordinates": [sp["longitude"], sp["latitude"]]
                },
                "properties": {
                    "sample_position_id":    sp["sample_position_id"],
                    "orchard_id":            orchard_id,
                    "measurement_date":      measurement_date,
                    "average_fruit_size_mm": sp.get("average_fruit_size_mm"),
                    "count_fruit_measured":  sp.get("count_fruit_measured"),
                    "average_length_mm":     sp.get("average_length_mm"),
                    "average_mass_g":        sp.get("average_mass_g"),
                    "marker-color":          "#FF4500",
                    "marker-size":           "medium"
                }
            }
            features_puntos.append(feature)

        print(f"  → orchard {orchard_id} ({measurement_date}): {len(detalle.get('sample_positions', []))} puntos")

    except Exception as e:
        print(f"  ✗ Error en orchard {orchard_id}: {e}")

print(f"Total puntos: {len(features_puntos)}")

# ── PASO 3: Leer polígonos desde MapasAzureJson (repo público) ─────────────────
print("Leyendo polígonos desde MapasAzureJson...")
r_pol = requests.get(POLIGONOS_URL)
r_pol.raise_for_status()
poligonos_content = r_pol.json()
print(f"  → {len(poligonos_content['features'])} polígonos cargados")

# ── PASO 4: Combinar polígonos + puntos ────────────────────────────────────────
geojson_final = {
    "type": "FeatureCollection",
    "features": poligonos_content["features"] + features_puntos
}

# ── PASO 5: Subir GeoJSON combinado a AeroboticsLocations ─────────────────────
print("Subiendo GeoJSON combinado a GitHub...")
output_url = f"https://api.github.com/repos/{GITHUB_REPO_OUTPUT}/contents/{GITHUB_FILE_PATH}"

sha = None
r_existing = requests.get(output_url, headers=HEADERS_GITHUB)
if r_existing.status_code == 200:
    sha = r_existing.json()["sha"]

contenido_b64 = base64.b64encode(
    json.dumps(geojson_final, ensure_ascii=False).encode("utf-8")
).decode("utf-8")

payload = {
    "message": f"Update GeoJSON combinado - {datetime.utcnow().strftime('%Y-%m-%d %H:%M UTC')}",
    "content": contenido_b64
}
if sha:
    payload["sha"] = sha

r_upload = requests.put(output_url, headers=HEADERS_GITHUB, json=payload)
r_upload.raise_for_status()
print(f"✓ Listo: {len(poligonos_content['features'])} polígonos + {len(features_puntos)} puntos")
print(f"  URL: https://raw.githubusercontent.com/{GITHUB_REPO_OUTPUT}/main/{GITHUB_FILE_PATH}")
