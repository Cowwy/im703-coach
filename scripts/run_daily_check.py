"""
Napi reggeli check (Haiku 4.5) – minden reggel fut.

Lehúzza az utolsó 14 nap wellness adatát + a tegnapi edzést,
átadja Claude Haiku-nak, ami visszaad egy strukturált JSON javaslatot.
A JSON kerül a output/daily_status.json-be, amit az index.html banner
JS-e beolvas és megjelenít.

Költség: kb. $0.01-0.02 / futás. Napi futtatással havi $0.30-0.60.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import sys
from dataclasses import asdict, is_dataclass
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))

from analyzer import normalize_sport
from daily_check import DailyChecker
from intervals_client import IntervalsClient
from strava_client import StravaClient

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
)
log = logging.getLogger("daily_run")


def _to_dict(obj):
    """dataclass → dict, dátumok ISO-stringgé."""
    if is_dataclass(obj):
        d = asdict(obj)
    elif isinstance(obj, dict):
        d = obj
    else:
        return obj
    out = {}
    for k, v in d.items():
        if isinstance(v, (dt.date, dt.datetime)):
            out[k] = v.isoformat()
        else:
            out[k] = v
    return out


def fetch_wellness_and_yesterday() -> tuple[list[dict], dict | None]:
    """
    Lehúzza a wellness adatokat (14 nap) és a tegnapi edzést.
    Intervals first, Strava fallback (de Strava-ban nincs wellness, csak yesterday activity).
    """
    today = dt.date.today()
    yesterday = today - dt.timedelta(days=1)
    wellness_start = today - dt.timedelta(days=14)

    # 1) Intervals.icu
    iid = os.environ.get("INTERVALS_ATHLETE_ID")
    ikey = os.environ.get("INTERVALS_API_KEY")
    if iid and ikey:
        try:
            client = IntervalsClient(iid, ikey)
            log.info("Intervals.icu wellness lehúzása (%s..%s)", wellness_start, today)
            wellness_rows = client.get_wellness(wellness_start, today)
            wellness_dicts = [_to_dict(w) for w in wellness_rows]

            log.info("Intervals.icu tegnapi edzés (%s)", yesterday)
            yesterday_acts = client.get_activities(yesterday, yesterday)
            yesterday_dict = _to_dict(yesterday_acts[-1]) if yesterday_acts else None

            return wellness_dicts, yesterday_dict
        except Exception as e:
            log.warning("Intervals.icu hibára futott: %s. Strava fallback...", e)

    # 2) Strava fallback (csak edzés, wellness nincs)
    sc_id = os.environ.get("STRAVA_CLIENT_ID")
    sc_sec = os.environ.get("STRAVA_CLIENT_SECRET")
    sc_tok = os.environ.get("STRAVA_REFRESH_TOKEN")
    if sc_id and sc_sec and sc_tok:
        try:
            sc = StravaClient(sc_id, sc_sec, sc_tok)
            log.info("Strava tegnapi edzés (%s)", yesterday)
            acts = sc.get_activities(yesterday, yesterday)
            yesterday_dict = _to_dict(acts[-1]) if acts else None
            return [], yesterday_dict
        except Exception as e:
            log.error("Strava is hibára futott: %s", e)

    return [], None


def extract_today_from_weekly_plan(plan_html_path: Path) -> str | None:
    """
    Megpróbálja kinyerni a mai napra szóló edzést.

    Elsősorban a current_plan.json-ből (strukturált adat).
    Másodlagosan a HTML-ből (regex), ha a JSON nem elérhető.
    """
    today = dt.date.today()

    # 1) Új JSON forrás (előnyben részesítve)
    json_path = plan_html_path.parent / "current_plan.json"
    if json_path.exists():
        try:
            data = json.loads(json_path.read_text(encoding="utf-8"))
            days = data.get("current_week", {}).get("days", [])
            for d in days:
                d_date = d.get("date", "")
                if d_date == today.isoformat():
                    sport = d.get("sport", "")
                    title = d.get("title", "")
                    duration = d.get("duration_min", "")
                    intensity = d.get("intensity", "")
                    details = d.get("details", "")
                    return (
                        f"Mai nap ({d.get('day', '')}, {d_date}): "
                        f"{title} [{sport}, {duration}', {intensity}] – {details}"
                    )
            # Ha nem talál mai napot a 7-elemes listában, tegyük közzé az egész heti tervet
            week_brief = "; ".join(
                f"{d.get('day', '')}: {d.get('title', '')}" for d in days
            )
            return f"Heti terv (mai nincs benne): {week_brief}"
        except Exception as e:
            log.warning("current_plan.json olvasási hiba: %s", e)

    # 2) Fallback: HTML regex (ha a JSON nincs még)
    if not plan_html_path.exists():
        return None
    try:
        text = plan_html_path.read_text(encoding="utf-8")
    except Exception:
        return None

    iso = today.isoformat()
    if iso in text:
        idx = text.index(iso)
        snippet = text[max(0, idx - 100): idx + 400]
        import re
        snippet = re.sub(r"<[^>]+>", " ", snippet)
        snippet = re.sub(r"\s+", " ", snippet).strip()
        return snippet[:400]

    return None


def main() -> int:
    out_dir = Path(__file__).parent.parent / "output"
    out_dir.mkdir(exist_ok=True)
    weekly_plan_path = out_dir / "index.html"

    today_planned = extract_today_from_weekly_plan(weekly_plan_path)
    if today_planned:
        log.info("Mai napra a heti tervből: %s...", today_planned[:120])
    else:
        log.warning("Nem sikerült kinyerni a mai napot a heti tervből.")

    wellness, yesterday = fetch_wellness_and_yesterday()
    log.info("Wellness sorok: %d, Tegnapi edzés: %s",
             len(wellness), "van" if yesterday else "nincs")

    athlete_notes = os.environ.get("ATHLETE_NOTES") or None

    checker = DailyChecker()
    result = checker.check(
        recent_wellness=wellness,
        yesterday_activity=yesterday,
        today_planned=today_planned,
        athlete_notes=athlete_notes,
    )

    # Mentés
    status_path = out_dir / "daily_status.json"
    status_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )
    log.info("daily_status.json frissítve: status=%s", result.get("status"))

    # Történeti archiválás (7 napig elég)
    archive_path = out_dir / f"daily_{dt.date.today().isoformat()}.json"
    archive_path.write_text(
        json.dumps(result, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    # Régi napi fájlok törlése (>14 nap)
    cutoff = dt.date.today() - dt.timedelta(days=14)
    for old in out_dir.glob("daily_*.json"):
        try:
            datestr = old.stem.replace("daily_", "")
            if datestr == "status":
                continue
            d = dt.date.fromisoformat(datestr)
            if d < cutoff:
                old.unlink()
        except Exception:
            pass

    print(f"\n✅ Napi check kész: {result.get('status')} – {result.get('headline')}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
