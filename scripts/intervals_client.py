"""
Intervals.icu API kliens.

Az Intervals.icu autoszinkronizál a Garmin Connect / Strava fiókodból,
és kiszámítja a TSS / CTL / ATL / TSB értékeket. Ez az elsődleges adatforrás.

API dokumentáció: https://intervals.icu/api/v1/
Auth: HTTP Basic Auth, username = "API_KEY", password = a kulcs maga.
       (Ezt a profilodban tudod legenerálni: Settings → Developer)
"""
from __future__ import annotations

import base64
import datetime as dt
import logging
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger(__name__)

API_BASE = "https://intervals.icu/api/v1"


@dataclass
class WellnessRow:
    """Egy napi wellness/forma adatsor."""
    date: dt.date
    # Edzéselméleti mutatók (CTL/ATL/TSB)
    ctl: float | None  # Fitness
    atl: float | None  # Fatigue
    tsb: float | None  # Form
    ramp_rate: float | None
    # Pulzus/HRV alapú mutatók
    resting_hr: int | None
    hrv: float | None
    # Alvás
    sleep_secs: int | None
    sleep_score: int | None  # Garmin Sleep Score (0-100)
    # Garmin-specifikus napi metrikák
    body_battery: int | None  # 0-100, reggel mérve
    vo2max: float | None  # Garmin saját VO₂max becslés
    # Egyéb
    readiness: float | None
    weight: float | None  # kg
    stress_avg: int | None  # napi átlag stressz (Garmin)


@dataclass
class Activity:
    """Egy edzés / verseny."""
    id: str
    start_date_local: dt.datetime
    type: str  # Run, Ride, Swim, ...
    name: str
    moving_time: int  # sec
    distance: float  # m
    icu_training_load: float | None  # TSS-szerű
    average_heartrate: float | None
    max_heartrate: float | None
    average_pace: float | None  # sec/m for run/swim
    average_watts: float | None  # for ride
    description: str | None


class IntervalsClient:
    def __init__(self, athlete_id: str, api_key: str, timeout: int = 30):
        if not athlete_id or not api_key:
            raise ValueError("athlete_id és api_key kötelező")
        self.athlete_id = athlete_id
        self.api_key = api_key
        self.timeout = timeout
        self._session = requests.Session()
        # Basic auth: username "API_KEY", password = a kulcs
        token = base64.b64encode(f"API_KEY:{api_key}".encode()).decode()
        self._session.headers.update({"Authorization": f"Basic {token}"})

    # ---- alacsony szintű ----
    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        url = f"{API_BASE}{path}"
        log.debug("GET %s params=%s", url, params)
        r = self._session.get(url, params=params, timeout=self.timeout)
        r.raise_for_status()
        return r.json()

    # ---- magas szintű ----
    def get_athlete_profile(self) -> dict[str, Any]:
        """Sportolói profil: küszöbök, zónák, súly, stb."""
        return self._get(f"/athlete/{self.athlete_id}")

    def get_zones_from_recent_activity(
        self, start: dt.date, end: dt.date
    ) -> dict[str, Any]:
        """
        Az utolsó aktivitásból kinyeri a sportoló TÉNYLEGES zónáit.

        Az Intervals.icu az aktivitások mellé csatolja az aktuális
        küszöböket és zónákat – ezek a Garmin / Intervals által
        számolt VALÓDI értékek, így ne kelljen LTHR-ből találgatni.

        Visszaadott mezők (csak a nem-null értékek):
          hr_zones      – 7 elemű lista [Z1 felső, Z2 felső, ..., max] (Coggan)
                          Pl. [149, 158, 167, 176, 181, 186, 195]
          pace_zones    – futás zónahatárok (sec/km)
          power_zones   – kerékpár zónahatárok (W)
          lthr          – tényleges Lactate Threshold HR (pl. 177)
          ftp           – Functional Threshold Power
          threshold_pace – futás küszöbtempó (sec/km)
          max_hr        – mért maximális pulzus
          resting_hr    – nyugalmi pulzus
          weight        – testsúly (kg)
        """
        raw_data = self._get(
            f"/athlete/{self.athlete_id}/activities",
            params={"oldest": start.isoformat(), "newest": end.isoformat()},
        )
        if not raw_data:
            log.warning("Nincs aktivitás zónák kinyeréséhez (időszak: %s - %s)", start, end)
            return {}

        # A legfrissebb aktivitás a sortolás után az utolsó elem
        raw_data.sort(key=lambda a: a.get("start_date_local", ""))
        last = raw_data[-1]

        zones = {
            "hr_zones": last.get("icu_hr_zones"),
            "pace_zones": last.get("pace_zones"),
            "power_zones": last.get("icu_power_zones"),
            "lthr": last.get("lthr"),
            "ftp": last.get("icu_ftp"),
            "threshold_pace": last.get("threshold_pace"),
            "max_hr": last.get("athlete_max_hr"),
            "resting_hr": last.get("icu_resting_hr"),
            "weight": last.get("icu_weight"),
        }
        # Csak a nem-null értékeket
        return {k: v for k, v in zones.items() if v is not None}

    def get_wellness(
        self, start: dt.date, end: dt.date
    ) -> list[WellnessRow]:
        """Napi wellness sorok (CTL/ATL/TSB + Garmin wellness mezők)."""
        data = self._get(
            f"/athlete/{self.athlete_id}/wellness",
            params={"oldest": start.isoformat(), "newest": end.isoformat()},
        )
        rows: list[WellnessRow] = []
        for d in data:
            rows.append(
                WellnessRow(
                    date=dt.date.fromisoformat(d["id"]),
                    ctl=d.get("ctl"),
                    atl=d.get("atl"),
                    tsb=(d.get("ctl") - d.get("atl"))
                    if d.get("ctl") is not None and d.get("atl") is not None
                    else None,
                    ramp_rate=d.get("rampRate"),
                    resting_hr=d.get("restingHR"),
                    hrv=d.get("hrv"),
                    sleep_secs=d.get("sleepSecs"),
                    sleep_score=d.get("sleepScore"),
                    body_battery=d.get("bodyBatteryAtWakeUp")
                                  or d.get("bodyBatteryHigh"),
                    vo2max=d.get("vo2max"),
                    readiness=d.get("readiness"),
                    weight=d.get("weight"),
                    stress_avg=d.get("avgStress"),
                )
            )
        rows.sort(key=lambda r: r.date)
        return rows

    def get_activities(
        self, start: dt.date, end: dt.date
    ) -> list[Activity]:
        """Edzések egy időszakra."""
        data = self._get(
            f"/athlete/{self.athlete_id}/activities",
            params={"oldest": start.isoformat(), "newest": end.isoformat()},
        )
        out: list[Activity] = []
        for a in data:
            try:
                start_dt = dt.datetime.fromisoformat(
                    a["start_date_local"].replace("Z", "")
                )
            except Exception:
                continue
            out.append(
                Activity(
                    id=str(a.get("id", "")),
                    start_date_local=start_dt,
                    type=a.get("type", "Unknown"),
                    name=a.get("name", ""),
                    moving_time=a.get("moving_time") or 0,
                    distance=a.get("distance") or 0.0,
                    icu_training_load=a.get("icu_training_load"),
                    average_heartrate=a.get("average_heartrate"),
                    max_heartrate=a.get("max_heartrate"),
                    average_pace=a.get("average_pace"),
                    average_watts=a.get("average_watts"),
                    description=a.get("description"),
                )
            )
        out.sort(key=lambda a: a.start_date_local)
        return out
