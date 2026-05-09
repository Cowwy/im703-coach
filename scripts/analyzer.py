"""
Edzésadat-elemző és összegző modul.

Az Intervals.icu / Strava nyers adataiból olyan tömör összefoglalót készít,
amit aztán a Claude promptba ágyazunk. Cél: a modell minden szükséges
információt megkapjon, de ne fulladjon ki nyers JSON-ben.
"""
from __future__ import annotations

import datetime as dt
import json
import statistics
from collections import defaultdict
from dataclasses import asdict, dataclass
from typing import Any, Iterable


SPORT_MAPPING = {
    # Strava és Intervals típusok normalizálása
    "Run": "run",
    "TrailRun": "run",
    "VirtualRun": "run",
    "Ride": "bike",
    "VirtualRide": "bike",
    "EBikeRide": "bike",
    "Swim": "swim",
    "WeightTraining": "strength",
    "Workout": "other",
    "Yoga": "other",
    "Walk": "other",
    "Hike": "other",
}


def normalize_sport(t: str) -> str:
    return SPORT_MAPPING.get(t, "other")


@dataclass
class WeeklyTotals:
    """Egy heti összesítő szakáganként."""
    week_start: dt.date          # hétfő
    swim_m: float = 0.0
    swim_sec: int = 0
    swim_count: int = 0
    bike_m: float = 0.0
    bike_sec: int = 0
    bike_count: int = 0
    run_m: float = 0.0
    run_sec: int = 0
    run_count: int = 0
    total_tss: float = 0.0       # ha elérhető
    total_sec: int = 0


def _monday_of(d: dt.date) -> dt.date:
    return d - dt.timedelta(days=d.weekday())


def aggregate_weekly(activities: Iterable[Any]) -> list[WeeklyTotals]:
    """
    Heti bontás. Az activity objektum bármi lehet, ami rendelkezik
    start_date_local, type, distance, moving_time és (opcionálisan)
    icu_training_load attribútumokkal.
    """
    by_week: dict[dt.date, WeeklyTotals] = {}
    for a in activities:
        wstart = _monday_of(a.start_date_local.date())
        w = by_week.setdefault(wstart, WeeklyTotals(week_start=wstart))
        sport = normalize_sport(a.type)
        if sport == "swim":
            w.swim_m += a.distance
            w.swim_sec += a.moving_time
            w.swim_count += 1
        elif sport == "bike":
            w.bike_m += a.distance
            w.bike_sec += a.moving_time
            w.bike_count += 1
        elif sport == "run":
            w.run_m += a.distance
            w.run_sec += a.moving_time
            w.run_count += 1
        w.total_sec += a.moving_time
        tl = getattr(a, "icu_training_load", None)
        if tl is not None:
            w.total_tss += float(tl)

    return sorted(by_week.values(), key=lambda x: x.week_start)


def summarize_recent_activities(
    activities: list[Any], n: int = 12
) -> list[dict[str, Any]]:
    """Az utolsó N edzés tömör reprezentációja a promptba."""
    out: list[dict[str, Any]] = []
    for a in activities[-n:]:
        sport = normalize_sport(a.type)
        d = a.start_date_local.date().isoformat()
        dur_min = round(a.moving_time / 60, 1)
        dist_km = round(a.distance / 1000, 2)
        row: dict[str, Any] = {
            "date": d,
            "sport": sport,
            "name": a.name,
            "duration_min": dur_min,
            "distance_km": dist_km,
        }
        if a.average_heartrate is not None:
            row["avg_hr"] = round(a.average_heartrate)
        if getattr(a, "average_watts", None) is not None:
            row["avg_watts"] = round(a.average_watts)
        if getattr(a, "icu_training_load", None) is not None:
            row["tss"] = round(float(a.icu_training_load))
        # tempó kiszámítása futás/úszás esetén
        if sport == "run" and dist_km > 0:
            pace_sec_per_km = a.moving_time / dist_km
            row["pace"] = f"{int(pace_sec_per_km // 60)}:{int(pace_sec_per_km % 60):02d}/km"
        elif sport == "swim" and a.distance > 0:
            pace_sec_per_100m = a.moving_time / (a.distance / 100)
            row["pace"] = f"{int(pace_sec_per_100m // 60)}:{int(pace_sec_per_100m % 60):02d}/100m"
        elif sport == "bike" and dur_min > 0:
            row["avg_kmh"] = round((dist_km / (dur_min / 60)), 1) if dur_min else None
        out.append(row)
    return out


def summarize_form_trend(
    wellness_rows: list[Any], days: int = 28
) -> dict[str, Any]:
    """CTL/ATL/TSB trend az utóbbi N napra."""
    if not wellness_rows:
        return {}
    recent = wellness_rows[-days:]
    ctl_vals = [r.ctl for r in recent if r.ctl is not None]
    atl_vals = [r.atl for r in recent if r.atl is not None]
    tsb_vals = [r.tsb for r in recent if r.tsb is not None]

    def stat(vals: list[float]) -> dict[str, float] | None:
        if not vals:
            return None
        return {
            "current": round(vals[-1], 1),
            "min": round(min(vals), 1),
            "max": round(max(vals), 1),
            "mean": round(statistics.mean(vals), 1),
        }

    out: dict[str, Any] = {
        "period_days": len(recent),
        "ctl": stat(ctl_vals),
        "atl": stat(atl_vals),
        "tsb": stat(tsb_vals),
    }

    # Trend: az első és utolsó CTL-érték közötti különbség
    if len(ctl_vals) >= 2:
        out["ctl_change_28d"] = round(ctl_vals[-1] - ctl_vals[0], 1)

    # VO2max trend (Garmin saját becslés)
    vo2_vals = [r.vo2max for r in recent if getattr(r, "vo2max", None) is not None]
    if vo2_vals:
        out["vo2max"] = stat(vo2_vals)

    # Sleep score trend
    sleep_score_vals = [r.sleep_score for r in recent if getattr(r, "sleep_score", None) is not None]
    if sleep_score_vals:
        out["sleep_score"] = stat([float(v) for v in sleep_score_vals])

    # Body Battery (reggel)
    bb_vals = [r.body_battery for r in recent if getattr(r, "body_battery", None) is not None]
    if bb_vals:
        out["body_battery_morning"] = stat([float(v) for v in bb_vals])

    # Friss readiness/HRV/RHR (utolsó nap)
    last = recent[-1]
    out["latest_resting_hr"] = last.resting_hr
    out["latest_hrv"] = last.hrv
    out["latest_readiness"] = last.readiness
    out["latest_sleep_score"] = getattr(last, "sleep_score", None)
    out["latest_body_battery"] = getattr(last, "body_battery", None)
    out["latest_vo2max"] = getattr(last, "vo2max", None)
    return out


def _format_hr_zones_human(hr_zones: list[int] | None) -> dict[str, str] | None:
    """
    Coggan 7-zónás HR lista emberi formátumra alakítása.

    Bemenet: pl. [149, 158, 167, 176, 181, 186, 195]
    Kimenet: {"z1": "<149", "z2": "149-158", "z3": "158-167",
              "z4": "167-176", "z5": "176-181", "z6": "181-186", "z7": "186+"}
    """
    if not hr_zones or len(hr_zones) < 5:
        return None
    out = {"z1": f"<{hr_zones[0]}"}
    for i in range(1, len(hr_zones)):
        out[f"z{i + 1}"] = f"{hr_zones[i - 1]}-{hr_zones[i]}"
    if len(hr_zones) >= 7:
        out[f"z{len(hr_zones)}"] = f"{hr_zones[-2]}+"
    return out


def _format_hr_zones_5zone(hr_zones: list[int] | None) -> dict[str, str] | None:
    """
    7-zónás Coggan listából 5-zónás megjelenítést készít (a Garmin órán is 5 zóna van).

    A Z5/Z6/Z7-et "Z5+ (VO2max-anaerob-sprint)" tartományba egyesíti.
    Bemenet: [149, 158, 167, 176, 181, 186, 195]
    Kimenet: {"z1":"<149", "z2":"149-158", "z3":"158-167", "z4":"167-176", "z5":"176+"}
    """
    if not hr_zones or len(hr_zones) < 5:
        return None
    return {
        "z1": f"<{hr_zones[0]}",
        "z2": f"{hr_zones[0]}-{hr_zones[1]}",
        "z3": f"{hr_zones[1]}-{hr_zones[2]}",
        "z4": f"{hr_zones[2]}-{hr_zones[3]}",
        "z5": f"{hr_zones[3]}+",
    }


def _format_pace_zones_5zone(pace_zones: list[float] | None) -> dict[str, str] | None:
    """Pace zónák (sec/km) 5-zónás emberi formátumra. Lassabb tempó = nagyobb sec/km."""
    if not pace_zones or len(pace_zones) < 5:
        return None

    def fmt(s: float) -> str:
        s = int(s)
        return f"{s // 60}:{s % 60:02d}/km"

    # A pace_zones listában a tempó-számok növekvő sec/km szerintiek (lassabb -> gyorsabb határok)
    # Z1 a leglassabb (>z1 érték), Z5+ a leggyorsabb (<z4 érték)
    return {
        "z1": f"{fmt(pace_zones[0])}+",
        "z2": f"{fmt(pace_zones[1])}-{fmt(pace_zones[0])}",
        "z3": f"{fmt(pace_zones[2])}-{fmt(pace_zones[1])}",
        "z4": f"{fmt(pace_zones[3])}-{fmt(pace_zones[2])}",
        "z5": f"<{fmt(pace_zones[3])}",
    }


def _format_power_zones_5zone(power_zones: list[int] | None) -> dict[str, str] | None:
    """Power zónák (W) 5-zónás emberi formátumra."""
    if not power_zones or len(power_zones) < 5:
        return None
    return {
        "z1": f"<{power_zones[0]}W",
        "z2": f"{power_zones[0]}-{power_zones[1]}W",
        "z3": f"{power_zones[1]}-{power_zones[2]}W",
        "z4": f"{power_zones[2]}-{power_zones[3]}W",
        "z5": f"{power_zones[3]}W+",
    }


def _data_freshness(wellness_rows: list[Any], today: dt.date) -> dict[str, Any]:
    """
    Megnézi mennyire friss a wellness adat. Garmin szinkronhibák detektálása.
    """
    if not wellness_rows:
        return {
            "days_since_last_wellness": None,
            "is_stale": True,
            "warning": "Nincs wellness adat – Garmin szinkron probléma?",
        }
    last = wellness_rows[-1]
    days = (today - last.date).days
    return {
        "days_since_last_wellness": days,
        "is_stale": days > 2,
        "warning": (
            f"Az utolsó wellness adat {days} napos – ellenőrizd a Garmin szinkront!"
            if days > 2 else None
        ),
    }


def build_athlete_snapshot(
    profile: dict[str, Any] | None,
    wellness: list[Any],
    activities: list[Any],
    race_date: dt.date,
    today: dt.date,
    recent_plan_history: list[dict] | None = None,
) -> dict[str, Any]:
    """
    A teljes pillanatkép, amit a Claude prompthoz csatolunk.
    """
    weeks_to_race = max(0, (race_date - today).days // 7)
    days_to_race = (race_date - today).days

    snapshot: dict[str, Any] = {
        "today": today.isoformat(),
        "race_date": race_date.isoformat(),
        "days_to_race": days_to_race,
        "weeks_to_race": weeks_to_race,
        "data_freshness": _data_freshness(wellness, today),
        "form_trend": summarize_form_trend(wellness, days=28),
        "weekly_summary_8w": [
            asdict(w) for w in aggregate_weekly(activities)[-8:]
        ],
        "recent_activities": summarize_recent_activities(activities, n=14),
    }

    if profile:
        # Csak a releváns mezőket emeljük ki
        relevant = {
            k: profile.get(k)
            for k in [
                "name", "weight", "ftp", "lthr", "threshold_pace",
                "swim_threshold_pace", "max_hr", "resting_hr",
                "sex", "icu_resting_hr",
            ]
            if profile.get(k) is not None
        }

        # ÚJ: tényleges zónák a friss aktivitásból
        # (a Garmin / Intervals.icu által számolt VALÓDI küszöbök)
        if profile.get("hr_zones"):
            relevant["actual_hr_zones_raw_7zone"] = profile["hr_zones"]
            human_5 = _format_hr_zones_5zone(profile["hr_zones"])
            if human_5:
                relevant["actual_hr_zones_5zone"] = human_5  # 5-zónás megjelenítés

        if profile.get("pace_zones"):
            relevant["actual_pace_zones_raw_7zone"] = profile["pace_zones"]
            human_5 = _format_pace_zones_5zone(profile["pace_zones"])
            if human_5:
                relevant["actual_pace_zones_5zone"] = human_5

        if profile.get("power_zones"):
            relevant["actual_power_zones_raw_7zone"] = profile["power_zones"]
            human_5 = _format_power_zones_5zone(profile["power_zones"])
            if human_5:
                relevant["actual_power_zones_5zone"] = human_5

        # Tényleges küszöbök (NE találgasson ezekből!)
        for key in ["lthr", "ftp", "threshold_pace", "max_hr"]:
            if profile.get(key):
                relevant[f"actual_{key}"] = profile[key]
        # Ha threshold_pace adott, kiírjuk olvashatóan is
        if profile.get("threshold_pace"):
            tp = int(profile["threshold_pace"])
            relevant["actual_threshold_pace_human"] = f"{tp // 60}:{tp % 60:02d}/km"

        snapshot["athlete_profile"] = relevant

    # ÚJ: az utolsó pár hét tervei – memory az iterációkhoz
    if recent_plan_history:
        snapshot["recent_plan_history"] = recent_plan_history

    return snapshot


def snapshot_to_json(snapshot: dict[str, Any]) -> str:
    """Promptba ágyazható JSON string (kompakt, de olvasható)."""
    # WeeklyTotals -> dict konverzió date kezeléssel
    def default(o: Any) -> Any:
        if isinstance(o, (dt.date, dt.datetime)):
            return o.isoformat()
        return str(o)

    return json.dumps(snapshot, indent=2, default=default, ensure_ascii=False)
