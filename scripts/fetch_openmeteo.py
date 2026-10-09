"""
Fetch real historical October weather for Park Street, Kolkata from the
Open-Meteo Historical Weather Archive (ERA5 reanalysis).

Data source: https://open-meteo.com/ (free, non-commercial, CC-BY-4.0 attribution).
Output: data/openmeteo_kolkata_october.csv  +  data/openmeteo_source.json

Run:  python scripts/fetch_openmeteo.py
"""
import json
import os
import sys
import time
import datetime

import requests

sys.path.insert(0, os.path.abspath("."))

LAT = 22.5510
LON = 88.3530
TZ = "Asia/Kolkata"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_VARS = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "shortwave_radiation",
    "cloud_cover",
    "wind_speed_10m",
]
YEARS = list(range(2006, 2026))  # 20 Octobers (2006 ... 2025)

OUT_CSV = os.path.join("data", "openmeteo_kolkata_october.csv")
OUT_META = os.path.join("data", "openmeteo_source.json")


def fetch_year(year: int, retries: int = 3) -> dict:
    params = {
        "latitude": LAT,
        "longitude": LON,
        "start_date": f"{year}-10-01",
        "end_date": f"{year}-10-31",
        "hourly": ",".join(HOURLY_VARS),
        "timezone": TZ,
    }
    last_err = None
    for attempt in range(retries):
        try:
            r = requests.get(ARCHIVE_URL, params=params, timeout=60)
            r.raise_for_status()
            return r.json()
        except Exception as e:  # network hiccups are common on archives
            last_err = e
            time.sleep(1.5 * (attempt + 1))
    raise RuntimeError(f"Failed to fetch {year}: {last_err}")


def main():
    if os.path.exists(OUT_CSV) and "--force" not in sys.argv:
        print(f"{OUT_CSV} already exists. Use --force to refetch.")
        return

    rows = []
    for year in YEARS:
        print(f"Fetching October {year} ...", flush=True)
        payload = fetch_year(year)
        hourly = payload["hourly"]
        times = hourly["time"]
        for i, t in enumerate(times):
            rec = {"time": t}
            for var in HOURLY_VARS:
                rec[var] = hourly[var][i]
            rec["source_year"] = year
            rows.append(rec)
        time.sleep(0.3)

    import pandas as pd

    df = pd.DataFrame(rows)
    df["time"] = pd.to_datetime(df["time"])
    df = df.sort_values("time").reset_index(drop=True)
    os.makedirs("data", exist_ok=True)
    df.to_csv(OUT_CSV, index=False)

    meta = {
        "source": "Open-Meteo Historical Weather Archive (ERA5 reanalysis)",
        "source_url": ARCHIVE_URL,
        "location": {"name": "Park Street, Kolkata", "lat": LAT, "lon": LON, "timezone": TZ},
        "variables": HOURLY_VARS,
        "years": YEARS,
        "rows": int(len(df)),
        "fetched_at": datetime.datetime.now().isoformat(),
        "license": "Open-Meteo data is CC-BY-4.0. Attribution required.",
    }
    with open(OUT_META, "w") as f:
        json.dump(meta, f, indent=2)

    print(f"Wrote {len(df)} rows -> {OUT_CSV}")
    print(f"Wrote metadata -> {OUT_META}")


if __name__ == "__main__":
    main()
