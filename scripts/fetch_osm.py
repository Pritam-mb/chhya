import urllib.request
import urllib.parse
import json
import os

BBOX = "22.5470,88.3480,22.5565,88.3585" # Park St, Camac St, Russell St, Middleton Row

query = f"""[out:json][timeout:35];
(
  way["building"]({BBOX});
  relation["building"]({BBOX});
  way["highway"]({BBOX});
);
out body;
>;
out skel qt;
"""

url = "https://overpass-api.de/api/interpreter?data=" + urllib.parse.quote(query)
headers = {"User-Agent": "ChhayaKolkataShadeApp/1.0 (hacktoberfest-chhaya)"}

print(f"Fetching OSM data for bounding box: {BBOX} ...")
os.makedirs("data", exist_ok=True)
req = urllib.request.Request(url, headers=headers)

try:
    with urllib.request.urlopen(req, timeout=40) as response:
        content = response.read().decode("utf-8")
        data = json.loads(content)
        elements = data.get("elements", [])
        print(f"Successfully received {len(elements)} elements from OSM Overpass!")
        with open("data/osm_raw.json", "w", encoding="utf-8") as f:
            f.write(content)
        print("Saved raw data to data/osm_raw.json")
except Exception as e:
    print(f"Error fetching OSM: {e}")
