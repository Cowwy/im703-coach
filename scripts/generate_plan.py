"""
IM 70.3 AI Coach – fő entry point.

Pipeline:
  1. Adatlehúzás Intervals.icu-ról (Strava fallback)
  2. Tényleges zónák kinyerése (Garmin / Intervals által számolt)
  3. Snapshot építés (CTL/ATL/TSB + heti aggregátumok + recent acts + zónák + history)
  4. Claude API → strukturált JSON edzésterv (~3k tokens, 15-30 sec)
  5. Python renderer → szép HTML (instant)
  6. Mentés output/ mappába

Env változók (kötelező):
  ANTHROPIC_API_KEY        – Claude API kulcs
  ATHLETE_NAME             – pl. "Kovács Gergő"
  RACE_DATE                – ISO formátum, pl. "2026-09-13"

Env változók (Intervals.icu – elsődleges):
  INTERVALS_ATHLETE_ID     – pl. "i576956"
  INTERVALS_API_KEY        – Settings → Developer → API Key

Env változók (Strava – fallback, opcionális):
  STRAVA_CLIENT_ID
  STRAVA_CLIENT_SECRET
  STRAVA_REFRESH_TOKEN

Opcionális:
  ATHLETE_NOTES            – szabad szöveg friss érzésekről
  PREV_RACE_RESULTS_JSON   – pl. {"swim_1.9km": "43:58", ...}
  CLAUDE_MODEL             – pl. "claude-sonnet-4-6" (default: claude-opus-4-7)
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from analyzer import build_athlete_snapshot, snapshot_to_json
from coach_llm import CoachLLM, DEFAULT_MODEL
from intervals_client import IntervalsClient
from renderer import render_plan_html
from strava_client import StravaClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("generate_plan")


def _env(name: str, required: bool = True, default: str | None = None) -> str | None:
    v = os.environ.get(name, default)
    if required and not v:
        log.error("Hiányzó env változó: %s", name)
        raise SystemExit(2)
    return v


def fetch_data_intervals(athlete_id: str, api_key: str, lookback_days: int = 90):
    client = IntervalsClient(athlete_id, api_key)
    today = dt.date.today()
    start = today - dt.timedelta(days=lookback_days)

    log.info("Intervals.icu: profil lehúzása...")
    profile = client.get_athlete_profile() or {}

    log.info("Intervals.icu: wellness (%d napos ablak)...", lookback_days)
    wellness = client.get_wellness(start, today)

    log.info("Intervals.icu: edzések (%d napos ablak)...", lookback_days)
    activities = client.get_activities(start, today)

    # Tényleges zónák kinyerése a friss aktivitásokból
    # (a Garmin / Intervals.icu által számolt VALÓDI küszöbök)
    log.info("Intervals.icu: tényleges zónák lekérése...")
    try:
        zones = client.get_zones_from_recent_activity(start, today)
        if zones:
            log.info(
                "Tényleges zónák: HR=%s | LTHR=%s | FTP=%s | Pace=%s sec/km",
                zones.get("hr_zones"),
                zones.get("lthr"),
                zones.get("ftp"),
                zones.get("threshold_pace"),
            )
            # Beépítjük a profilba (felülírja az ottani értékeket ha vannak)
            profile.update({k: v for k, v in zones.items() if v is not None})
        else:
            log.warning("Nem sikerült tényleges zónákat lekérni.")
    except Exception as e:
        log.warning("Zónák lekérése hibára futott: %s", e)

    log.info("Intervals.icu OK: %d wellness sor, %d aktivitás",
             len(wellness), len(activities))
    return profile, wellness, activities


def fetch_data_strava(client_id: str, client_secret: str, refresh_token: str,
                     lookback_days: int = 90):
    client = StravaClient(client_id, client_secret, refresh_token)
    today = dt.date.today()
    start = today - dt.timedelta(days=lookback_days)
    log.info("Strava: edzések (%d napos ablak)...", lookback_days)
    activities = client.get_activities(start, today)
    log.info("Strava OK: %d edzés", len(activities))
    return None, [], activities


def _load_recent_plan_history(out_dir: Path, max_weeks: int = 3) -> list[dict]:
    """
    Betölti az utolsó N heti tervet rövidített formában a memory-hoz.
    Csak a `current_week` és `macrocycle_outlook` szekciókat tartja meg, hogy a Claude
    láthassa: mit ígért, mit ütemezett. Az output-mérete kezelhető marad.
    """
    history_dir = out_dir / "history"
    if not history_dir.exists():
        return []
    files = sorted(history_dir.glob("plan_*.json"), reverse=True)[:max_weeks]
    history = []
    for f in files:
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            history.append({
                "generated_at": data.get("_generated_at"),
                "current_week": data.get("current_week"),
                "macrocycle_phase": data.get("situation_assessment", {}).get("current_phase"),
            })
        except Exception:
            continue
    return list(reversed(history))  # legrégebbi -> legfrissebb


def _retain_recent_files(directory: Path, pattern: str, max_files: int) -> None:
    """A megadott pattern szerinti fájlokból csak a legfrissebb max_files darabot tartja meg."""
    files = sorted(directory.glob(pattern), key=lambda p: p.stat().st_mtime, reverse=True)
    for f in files[max_files:]:
        try:
            f.unlink()
            log.info("Régi fájl törölve: %s", f.name)
        except Exception as e:
            log.warning("Nem sikerült törölni %s: %s", f.name, e)


def main() -> int:
    athlete_name = _env("ATHLETE_NAME")
    race_date_str = _env("RACE_DATE")
    race_date = dt.date.fromisoformat(race_date_str)
    today = dt.date.today()

    user_notes = os.environ.get("ATHLETE_NOTES") or None
    prev_race_results = None
    if (raw := os.environ.get("PREV_RACE_RESULTS_JSON")):
        try:
            prev_race_results = json.loads(raw)
        except json.JSONDecodeError:
            log.warning("PREV_RACE_RESULTS_JSON nem érvényes JSON, ignorálom.")

    days_left = (race_date - today).days
    log.info("Sportoló: %s | Versenyig: %d nap (%d hét) | Versenynap: %s",
             athlete_name, days_left, days_left // 7, race_date)
    if days_left < 0:
        log.error("A versenynap már elmúlt!")
        return 3

    out_dir = Path(__file__).parent.parent / "output"
    out_dir.mkdir(exist_ok=True)
    history_dir = out_dir / "history"
    history_dir.mkdir(exist_ok=True)

    # 1. Adatok lehúzása
    profile, wellness, activities = None, [], []
    intervals_id = os.environ.get("INTERVALS_ATHLETE_ID")
    intervals_key = os.environ.get("INTERVALS_API_KEY")

    if intervals_id and intervals_key:
        try:
            profile, wellness, activities = fetch_data_intervals(intervals_id, intervals_key)
        except Exception as e:
            log.warning("Intervals.icu hibára futott: %s. Strava fallback...", e)

    if not activities:
        sc_id = os.environ.get("STRAVA_CLIENT_ID")
        sc_sec = os.environ.get("STRAVA_CLIENT_SECRET")
        sc_tok = os.environ.get("STRAVA_REFRESH_TOKEN")
        if sc_id and sc_sec and sc_tok:
            try:
                profile, wellness, activities = fetch_data_strava(sc_id, sc_sec, sc_tok)
            except Exception as e:
                log.error("Strava is hibára futott: %s", e)
                return 4
        else:
            log.error("Sem Intervals sem Strava credential nincs. Add meg legalább egyet.")
            return 5

    if not activities:
        log.error("Nincs lehúzott edzésadat – nem tudok tervet generálni.")
        return 6

    # 2. Plan history betöltése (memory az iterációkhoz)
    plan_history = _load_recent_plan_history(out_dir, max_weeks=3)
    if plan_history:
        log.info("Korábbi tervek betöltve: %d hét (memory)", len(plan_history))

    # 3. Snapshot építése
    snapshot = build_athlete_snapshot(
        profile=profile,
        wellness=wellness,
        activities=activities,
        race_date=race_date,
        today=today,
        recent_plan_history=plan_history,
    )
    snapshot_json = snapshot_to_json(snapshot)
    log.info("Snapshot kész: %d karakter JSON", len(snapshot_json))

    # 4. Claude → JSON terv
    model = os.environ.get("CLAUDE_MODEL", DEFAULT_MODEL)
    log.info("Modell használat: %s", model)
    llm = CoachLLM(model=model)
    plan_dict = llm.generate_plan(
        athlete_snapshot_json=snapshot_json,
        athlete_name=athlete_name,
        race_name="Ironman 70.3",
        prev_race_results=prev_race_results,
        user_notes=user_notes,
    )
    log.info("JSON plan parsed OK, %d top-level kulcs", len(plan_dict))

    # Időbélyeg hozzáadása a tervhez (history-hoz fontos)
    plan_dict["_generated_at"] = dt.datetime.now().isoformat()

    # 5. Python renderer → HTML
    log.info("HTML renderelés...")
    html = render_plan_html(
        plan=plan_dict,
        athlete_name=athlete_name,
        race_name="Ironman 70.3",
        race_date=race_date.isoformat(),
        generated_at=dt.datetime.now(),
    )
    log.info("HTML kész: %d karakter", len(html))

    # 6. Mentés
    timestamp = today.isoformat()
    week_num = today.isocalendar().week
    safe_name = "".join(c if c.isalnum() else "_" for c in athlete_name.lower())
    safe_name = (safe_name.replace("á", "a").replace("é", "e").replace("í", "i")
                 .replace("ó", "o").replace("ö", "o").replace("ő", "o")
                 .replace("ú", "u").replace("ü", "u").replace("ű", "u"))

    fname = f"plan_{safe_name}_{timestamp}_w{week_num:02d}.html"
    out_path = out_dir / fname
    out_path.write_text(html, encoding="utf-8")
    log.info("HTML mentve: %s", out_path)

    # index.html = legfrissebb
    (out_dir / "index.html").write_text(html, encoding="utf-8")

    # JSON mentés (audit, daily check kontextusként)
    plan_json_path = out_dir / "current_plan.json"
    plan_json_path.write_text(
        json.dumps(plan_dict, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Snapshot mentés (debug)
    snap_path = out_dir / f"snapshot_{timestamp}.json"
    snap_path.write_text(snapshot_json, encoding="utf-8")

    # History mentés (memory az iterációkhoz)
    history_path = history_dir / f"plan_{timestamp}_w{week_num:02d}.json"
    history_path.write_text(
        json.dumps(plan_dict, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Retention: csak az utolsó 8 fájlt tartjuk meg minden típusból
    _retain_recent_files(out_dir, "plan_*.html", max_files=8)
    _retain_recent_files(out_dir, "snapshot_*.json", max_files=8)
    _retain_recent_files(history_dir, "plan_*.json", max_files=8)

    print(f"\n✅ Kész! Az új edzésterv: {out_path}")
    print(f"   Index: {out_dir / 'index.html'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
