"""
Strava API fallback kliens.

Akkor használjuk, ha az Intervals.icu nem elérhető. A Strava-ban nincs
natív TSS, de a HR-zónák alapján becsülhetjük (hrTSS).

OAuth: refresh_token -> access_token folyamat. A refresh_token tartós,
csak egyszer kell beszerezni.

Setup útmutató: docs/STRAVA_SETUP.md
"""
from __future__ import annotations

import datetime as dt
import logging
import time
from dataclasses import dataclass
from typing import Any

import requests

log = logging.getLogger(__name__)

TOKEN_URL = "https://www.strava.com/api/v3/oauth/token"
API_BASE = "https://www.strava.com/api/v3"


@dataclass
class StravaActivity:
    id: int
    start_date_local: dt.datetime
    type: str  # Run, Ride, Swim, VirtualRide, ...
    name: str
    moving_time: int
    distance: float  # m
    average_heartrate: float | None
    max_heartrate: float | None
    average_speed: float | None  # m/s
    average_watts: float | None
    suffer_score: float | None  # Strava saját terhelési metrikája
    description: str | None


class StravaClient:
    def __init__(self, client_id: str, client_secret: str, refresh_token: str):
        if not all([client_id, client_secret, refresh_token]):
            raise ValueError("client_id, client_secret, refresh_token kötelező")
        self.client_id = client_id
        self.client_secret = client_secret
        self.refresh_token = refresh_token
        self._access_token: str | None = None
        self._access_expires_at = 0
        self._session = requests.Session()

    def _refresh(self) -> None:
        log.info("Strava token frissítés...")
        r = requests.post(
            TOKEN_URL,
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
            },
            timeout=20,
        )
        r.raise_for_status()
        d = r.json()
        self._access_token = d["access_token"]
        self._access_expires_at = d["expires_at"]
        # A refresh_token frissülhet, mentsük el ha igen:
        new_refresh = d.get("refresh_token")
        if new_refresh and new_refresh != self.refresh_token:
            log.warning("ÚJ Strava refresh_token: %s — frissítsd a secretet!", new_refresh)
            self.refresh_token = new_refresh

    def _ensure_token(self) -> None:
        if not self._access_token or time.time() >= self._access_expires_at - 60:
            self._refresh()

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        self._ensure_token()
        r = self._session.get(
            f"{API_BASE}{path}",
            headers={"Authorization": f"Bearer {self._access_token}"},
            params=params,
            timeout=30,
        )
        r.raise_for_status()
        return r.json()

    def get_activities(
        self, start: dt.date, end: dt.date, per_page: int = 100
    ) -> list[StravaActivity]:
        after = int(dt.datetime.combine(start, dt.time.min).timestamp())
        before = int(dt.datetime.combine(end, dt.time.max).timestamp())
        all_acts: list[dict[str, Any]] = []
        page = 1
        while True:
            data = self._get(
                "/athlete/activities",
                params={"after": after, "before": before, "per_page": per_page, "page": page},
            )
            if not data:
                break
            all_acts.extend(data)
            if len(data) < per_page:
                break
            page += 1
            if page > 10:  # safety
                break

        out: list[StravaActivity] = []
        for a in all_acts:
            try:
                sd = dt.datetime.fromisoformat(
                    a["start_date_local"].replace("Z", "")
                )
            except Exception:
                continue
            out.append(
                StravaActivity(
                    id=int(a["id"]),
                    start_date_local=sd,
                    type=a.get("type", "Unknown"),
                    name=a.get("name", ""),
                    moving_time=a.get("moving_time") or 0,
                    distance=a.get("distance") or 0.0,
                    average_heartrate=a.get("average_heartrate"),
                    max_heartrate=a.get("max_heartrate"),
                    average_speed=a.get("average_speed"),
                    average_watts=a.get("average_watts"),
                    suffer_score=a.get("suffer_score"),
                    description=a.get("description"),
                )
            )
        out.sort(key=lambda x: x.start_date_local)
        return out


def estimate_hr_tss(
    duration_sec: int,
    avg_hr: float | None,
    threshold_hr: float,
) -> float | None:
    """
    Egyszerű hrTSS becslés Banister TRIMP-modell alapján:
      hrTSS = (duration_h * (avg_hr / threshold_hr)^2) * 100
    Csak akkor adjuk vissza, ha van avg_hr.
    """
    if avg_hr is None or threshold_hr <= 0 or duration_sec <= 0:
        return None
    duration_h = duration_sec / 3600.0
    return (duration_h * (avg_hr / threshold_hr) ** 2) * 100.0
