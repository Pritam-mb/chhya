"""
Best-window forecaster for Chhaya.

Uses the TabPFN regressor (TabPFN-2 weights, Prior Labs License = Apache-2.0
with attribution) trained on real Open-Meteo historical October weather for
Park Street, Kolkata, and compared against a climatology baseline.

Target = Open-Meteo `apparent_temperature` (feels-like). Features are the
day's forecast temperature, humidity, radiation and cloud; wind speed is
deliberately withheld (Open-Meteo's apparent temperature also depends on wind),
so the held-out error is a genuine, non-trivial nowcast number rather than a
restatement of the target formula.

At request time the model consumes the live Open-Meteo forecast for the target
date; if the network is unavailable it falls back to the 20-year hourly
climatology stored from the archive CSV.

Run `python scripts/train_window_model.py` to (re)compute the held-out MAE and
write `results/window_eval.json`.
"""
import os
import json
import math
import warnings
import datetime
from typing import Dict, List, Any, Optional

import numpy as np
import pandas as pd

try:
    from tabpfn import TabPFNRegressor
    from tabpfn.constants import ModelVersion
    HAS_TABPFN = True
except Exception:
    HAS_TABPFN = False

from backend.geo_shadows import calculate_solar_position

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ARCHIVE_CSV = os.path.join(ROOT, "data", "openmeteo_kolkata_october.csv")
EVAL_JSON = os.path.join(ROOT, "results", "window_eval.json")

LAT, LON = 22.5510, 88.3530
TZ = "Asia/Kolkata"
FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
ARCHIVE_URL = "https://archive-api.open-meteo.com/v1/archive"
HOURLY_VARS = ["temperature_2m", "relative_humidity_2m", "shortwave_radiation", "cloud_cover"]

FEATURE_COLS = [
    "hour_sin",
    "hour_cos",
    "solar_elevation",
    "temperature_2m",
    "relative_humidity_2m",
    "shortwave_radiation",
    "cloud_cover",
]
TARGET_COL = "apparent_temperature"

TRAIN_YEAR_MAX = 2024
TEST_YEAR = 2025
DAYLIGHT_HOURS = list(range(6, 19))  # 6 AM .. 6 PM
TRAIN_SUBSET = 600
N_ESTIMATORS = 2

# 2-hour walking windows: (representative hours, label, display)
WINDOWS = [
    ([7, 8], "Early Morning", "06:30 - 08:30"),
    ([9, 10], "Morning", "08:30 - 10:30"),
    ([12, 13], "High Noon (Peak Sun)", "11:30 - 13:30"),
    ([15, 16], "Late Afternoon (Long Shadows)", "14:30 - 16:30"),
    ([17], "Dusk / Sunset", "16:30 - 18:00"),
]


def _add_features(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    df["time"] = pd.to_datetime(df["time"])
    df["hour"] = df["time"].dt.hour
    df["year"] = df["time"].dt.year
    df["hour_sin"] = np.sin(2.0 * math.pi * df["hour"] / 24.0)
    df["hour_cos"] = np.cos(2.0 * math.pi * df["hour"] / 24.0)
    df["solar_elevation"] = df["time"].apply(
        lambda dt: calculate_solar_position(dt.to_pydatetime())["elevation"]
    )
    return df


def load_archive() -> Optional[pd.DataFrame]:
    if not os.path.exists(ARCHIVE_CSV):
        return None
    df = pd.read_csv(ARCHIVE_CSV)
    df = _add_features(df)
    df = df[df["hour"].isin(DAYLIGHT_HOURS)].dropna(
        subset=FEATURE_COLS + [TARGET_COL]
    )
    return df.reset_index(drop=True)


class BestWindowModel:
    def __init__(self):
        self.df = load_archive()
        self.ready = self.df is not None and len(self.df) > 0
        self.model = None
        self.tabpfn_error: Optional[str] = None
        self.climatology: Dict[int, float] = {}
        self.hourly_climo: Optional[pd.DataFrame] = None
        self.mae_tabpfn: Optional[float] = None
        self.mae_baseline: Optional[float] = None
        self.train_year_max = TRAIN_YEAR_MAX
        self.test_year = TEST_YEAR
        self._forecast_cache: Dict[str, Any] = {}
        if self.ready:
            self._prepare()

    # ------------------------------------------------------------------ setup
    def _prepare(self):
        df = self.df
        train = df[df["year"] <= TRAIN_YEAR_MAX]
        test = df[df["year"] == TEST_YEAR]

        self.climatology = {
            int(h): float(v) for h, v in train.groupby("hour")[TARGET_COL].mean().items()
        }
        self.hourly_climo = train.groupby("hour")[HOURLY_VARS].mean()

        if len(test) > 0:
            base_pred = test["hour"].map(self.climatology)
            self.mae_baseline = float(np.mean(np.abs(test[TARGET_COL] - base_pred)))

        self._fit_tabpfn(train)
        self._load_metrics()

    def _fit_tabpfn(self, train: pd.DataFrame):
        if not HAS_TABPFN or len(train) < 20:
            return
        sub = train.sample(n=min(TRAIN_SUBSET, len(train)), random_state=42)
        try:
            warnings.filterwarnings("ignore", message="Running on CPU with more than 200 samples")
            reg = TabPFNRegressor.create_default_for_version(ModelVersion.V2)
            reg.set_params(device="cpu", n_estimators=N_ESTIMATORS)
            reg.fit(sub[FEATURE_COLS].values, sub[TARGET_COL].values)
            self.model = reg
        except Exception as e:  # keeps the app alive if weights are unavailable
            self.tabpfn_error = str(e)
            self.model = None

    def _load_metrics(self):
        if os.path.exists(EVAL_JSON):
            try:
                with open(EVAL_JSON) as f:
                    data = json.load(f)
                self.mae_tabpfn = data.get("tabpfn_mae")
            except Exception:
                pass

    def evaluate_heldout(self) -> Dict[str, Any]:
        """Full held-out evaluation (used by scripts/train_window_model.py)."""
        if not self.ready:
            raise RuntimeError("No archive data available for evaluation.")
        df = self.df
        test = df[df["year"] == TEST_YEAR]
        base_pred = test["hour"].map(self.climatology)
        self.mae_baseline = float(np.mean(np.abs(test[TARGET_COL] - base_pred)))

        result: Dict[str, Any] = {
            "test_year": TEST_YEAR,
            "train_year_max": TRAIN_YEAR_MAX,
            "n_train_rows": int((df["year"] <= TRAIN_YEAR_MAX).sum()),
            "n_test_rows": int(len(test)),
            "baseline_mae": round(self.mae_baseline, 4),
            "tabpfn_mae": None,
            "model": "TabPFN-2 regressor" if self.model is not None else "climatology only",
        }
        if self.model is not None:
            preds = self.model.predict(test[FEATURE_COLS].values)
            self.mae_tabpfn = float(np.mean(np.abs(test[TARGET_COL].values - preds)))
            result["tabpfn_mae"] = round(self.mae_tabpfn, 4)
            result["error_reduction_pct"] = round(
                (self.mae_baseline - self.mae_tabpfn) / self.mae_baseline * 100.0, 2
            )
        return result

    # ------------------------------------------------------------- prediction
    def _fetch_hourly(self, date_str: str) -> tuple:
        """Return (list of hourly dicts, source label) for one date."""
        import requests

        params_base = {
            "latitude": LAT,
            "longitude": LON,
            "start_date": date_str,
            "end_date": date_str,
            "hourly": ",".join(HOURLY_VARS),
            "timezone": TZ,
        }
        for url, label in (
            (FORECAST_URL, "Open-Meteo forecast"),
            (ARCHIVE_URL, "Open-Meteo archive"),
        ):
            try:
                r = requests.get(url, params=params_base, timeout=20)
                r.raise_for_status()
                payload = r.json()
                hourly = payload.get("hourly") or {}
                times = hourly.get("time") or []
                if not times:
                    continue
                rows = []
                for i, t in enumerate(times):
                    rows.append({"time": t, **{v: hourly[v][i] for v in HOURLY_VARS}})
                return rows, label
            except Exception:
                continue
        return None, "climatology fallback (offline)"

    def _climatology_rows(self, date_str: str) -> list:
        dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
        rows = []
        for h in DAYLIGHT_HOURS:
            base = self.hourly_climo.loc[h] if self.hourly_climo is not None else None
            rows.append(
                {
                    "time": dt.replace(hour=h).strftime("%Y-%m-%dT%H:%M"),
                    "temperature_2m": float(base["temperature_2m"]) if base is not None else 30.0,
                    "relative_humidity_2m": float(base["relative_humidity_2m"]) if base is not None else 70.0,
                    "shortwave_radiation": float(base["shortwave_radiation"]) if base is not None else 0.0,
                    "cloud_cover": float(base["cloud_cover"]) if base is not None else 40.0,
                }
            )
        return rows

    def predict_for_date(self, date_str: str) -> Dict[str, Any]:
        if date_str in self._forecast_cache:
            return self._forecast_cache[date_str]

        rows, source = self._fetch_hourly(date_str)
        if rows is None:
            rows = self._climatology_rows(date_str)

        feat = _add_features(pd.DataFrame(rows))
        feat = feat[feat["hour"].isin(DAYLIGHT_HOURS)].reset_index(drop=True)

        if self.model is not None:
            preds = self.model.predict(feat[FEATURE_COLS].values)
            pred_by_hour = {int(h): float(p) for h, p in zip(feat["hour"], preds)}
        else:
            pred_by_hour = {
                int(h): float(self.climatology.get(int(h), 32.0)) for h in DAYLIGHT_HOURS
            }

        elev_by_hour = {int(h): float(e) for h, e in zip(feat["hour"], feat["solar_elevation"])}
        base_by_hour = {
            int(h): float(self.climatology.get(int(h), 32.0)) for h in DAYLIGHT_HOURS
        }

        windows = []
        for hours, label, display in WINDOWS:
            preds_w = [pred_by_hour[h] for h in hours if h in pred_by_hour]
            bases_w = [base_by_hour[h] for h in hours]
            elevs_w = [elev_by_hour.get(h, 60.0) for h in hours]
            pred_heat = float(np.mean(preds_w)) if preds_w else base_by_hour[hours[0]]
            base_heat = float(np.mean(bases_w))
            mean_elev = float(np.mean(elevs_w))

            if mean_elev > 1.0:
                shadow_factor = 1.0 / math.tan(math.radians(mean_elev))
            else:
                shadow_factor = 3.0
            shadow_factor = max(0.0, min(shadow_factor, 3.0))

            heat_penalty = max(0.0, pred_heat - 27.0)
            score = 100.0 - heat_penalty * 4.0 + min(shadow_factor, 2.0) * 4.0
            score = int(max(5, min(99, round(score))))

            if mean_elev <= 0.0:
                shade_quality = "Full shade (sun below skyline)"
            elif shadow_factor >= 1.5:
                shade_quality = f"Excellent (deep shadows {shadow_factor:.1f}x building height)"
            elif shadow_factor >= 1.0:
                shade_quality = f"Good (shadows {shadow_factor:.1f}x building height)"
            elif shadow_factor >= 0.7:
                shade_quality = f"Moderate (short shadows {shadow_factor:.1f}x height)"
            else:
                shade_quality = f"Poor (shadows only {shadow_factor:.1f}x height)"

            if score >= 85:
                recommendation = "Best time to walk: coolest air with the longest shade"
            elif score >= 70:
                recommendation = "Comfortable if you keep to the shaded lanes"
            elif score >= 55:
                recommendation = "Usable but warm; prefer shade routing"
            else:
                recommendation = "Avoid if sensitive to sun; pick another hour"

            windows.append(
                {
                    "time_window": display,
                    "label": label,
                    "discomfort_score": score,
                    "predicted_feels_like_c": round(pred_heat, 1),
                    "baseline_climatology_c": round(base_heat, 1),
                    "predicted_heat_index": round(pred_heat, 1),
                    "baseline_climatology": round(base_heat, 1),
                    "shade_quality": shade_quality,
                    "recommendation": recommendation,
                    "is_recommended": score >= 80,
                    "is_peak_noon": 12 in hours or 13 in hours,
                }
            )

        windows.sort(key=lambda w: w["discomfort_score"], reverse=True)
        best = windows[0]

        try:
            dt = datetime.datetime.strptime(date_str, "%Y-%m-%d")
            noon_elev = calculate_solar_position(dt.replace(hour=12))["elevation"]
        except Exception:
            noon_elev = 60.0

        reduction = None
        if self.mae_tabpfn is not None and self.mae_baseline:
            reduction = round(
                (self.mae_baseline - self.mae_tabpfn) / self.mae_baseline * 100.0, 1
            )

        result = {
            "date": date_str,
            "data_source": source,
            "best_window": best["time_window"],
            "best_window_label": best["label"],
            "explanation": (
                f"Best walking window is {best['time_window']} ({best['label']}): "
                f"TabPFN feels-like {best['predicted_feels_like_c']}°C vs "
                f"{best['baseline_climatology_c']}°C climatology. "
                f"At noon the sun reaches {noon_elev:.1f}°, shrinking shadows, so the "
                f"low-sun hours give both cooler air and longer shade."
            ),
            "model_metrics": {
                "model": "TabPFN-2 regressor vs 20-year hourly climatology baseline",
                "target": "Open-Meteo apparent temperature (feels-like, deg C)",
                "tabpfn_mae": self.mae_tabpfn,
                "baseline_mae": round(self.mae_baseline, 3) if self.mae_baseline else None,
                "error_reduction_pct": reduction,
                "dataset": "Open-Meteo ERA5 archive, October 2006-2025, Park Street Kolkata",
                "features": "hour, solar elevation, temperature, humidity, radiation, cloud (wind withheld)",
                "held_out": f"October {self.test_year}, all daylight hours",
                "tabpfn_license": "Prior Labs License (Apache-2.0 with attribution) - 'Built with PriorLabs-TabPFN'",
            },
            "windows": windows,
        }
        self._forecast_cache[date_str] = result
        return result


_window_model: Any = None


def get_window_model() -> BestWindowModel:
    global _window_model
    if _window_model is None:
        _window_model = BestWindowModel()
    return _window_model
