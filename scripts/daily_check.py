"""
Napi morning check Claude Haiku 4.5-tel.

Cél: minden reggel kis költséggel ($0.01-0.02/futás) megnézni:
  - milyen volt az alvás
  - HRV / RHR trendje
  - readiness
  - mi volt a tegnapi edzés (terv vs valóság)
és kiadni egy strukturált javaslatot a mai napra.

Output: JSON fájl, amit az index.html banner-je beolvas.
"""
from __future__ import annotations

import datetime as dt
import json
import logging
import os
import re
from pathlib import Path
from typing import Any

from anthropic import Anthropic

log = logging.getLogger(__name__)

DAILY_MODEL = "claude-haiku-4-5"
DAILY_MAX_TOKENS = 1500


DAILY_SYSTEM_PROMPT = """Te egy triatlon edző asszisztens vagy. A feladatod NAPI gyors check: a sportoló reggeli wellness adatait és a tegnapi edzését nézed meg, és eldöntöd, hogy a heti tervben szereplő MAI edzés:
- TARTHATÓ úgy ahogy van, vagy
- CSÖKKENTENI kell (mert fáradtság / alvás / HRV jelez), vagy
- HELYETTESÍTENI pihenővel / Z1-zel.

A döntés alapja:
- HRV trend: ha a 7 napos átlaghoz képest >7% zuhanás → óvatosság
- Resting HR: ha >5 bpm emelkedés a baseline-hoz → óvatosság
- Alvás: <6.5h vagy nagyon rossz minőség (Sleep Score <60) → könnyítés
- Body Battery (Garmin): ha reggeli érték <40 → kemény edzés helyett könnyű
- Garmin Readiness: ha <50 → óvatosság, <30 → pihenőnap
- Tegnapi edzés: ha a tényleges TSS jelentősen meghaladta a tervezettet → könnyítés
- Sportoló saját notes: fájdalom, betegség, stressz → priorizáld

Ne egyetlen mutatóra hagyatkozz. Több jelzés együttes mérlegelése a cél: pl. "HRV kicsit alacsony, de Sleep Score 85, RHR baseline-on, Body Battery 75" → green/yellow határeset, valószínűleg green.

A válaszod KIZÁRÓLAG egy érvényes JSON, semmi más, semmi markdown, semmi magyarázat előtte vagy utána.

A JSON formátuma EGYSZERREVATARTÁSI:
{
  "status": "green" | "yellow" | "red",
  "headline": "Egysoros összefoglaló (max 80 karakter, magyarul)",
  "recommendation": "Mit csinálj ma? (1-2 mondat, magyarul, konkrétan)",
  "modify_today": false | true,
  "today_alternative": null | "Ha modify_today=true: konkrét alternatív edzés leírása",
  "metrics": {
    "hrv_status": "ok" | "low" | "very_low" | "unknown",
    "rhr_status": "ok" | "elevated" | "very_elevated" | "unknown",
    "sleep_status": "ok" | "short" | "poor" | "unknown",
    "yesterday_load_status": "as_planned" | "above_planned" | "below_planned" | "unknown"
  },
  "notes_acknowledgment": null | "Ha a sportoló írt megjegyzést, mit veszel figyelembe (1 mondat)"
}

A "status" jelentései:
- "green": minden rendben, tartsd a tervet
- "yellow": vigyázat, valamilyen jelzés alapján könnyítés indokolt
- "red": kritikus jelzés (pl. nagyon alacsony HRV + magas RHR + rossz alvás kombináció), pihenőnap vagy nagyon könnyű Z1 ajánlott

A "modify_today" akkor true, ha a status yellow vagy red. Ekkor a "today_alternative" mezőben add meg KONKRÉTAN, hogy mit csináljon (pl. "30 perc Z1 könnyű kocogás 5:30-6:00/km tempóval" vagy "Teljes pihenő, 20 perc séta + nyújtás").

KONTEXTUS – a sportoló szokásos heti struktúrája (Ironman 70.3 felkészülés):
- Hétfő: Recovery + mobility
- Kedd: Threshold bike (intenzív)
- Szerda: Swim + strength
- Csütörtök: Tempo run (intenzív)
- Péntek: Easy bike + mobility
- Szombat: LONG BIKE + brick run (a hét legnagyobb terhelése)
- Vasárnap: Long aerobic run vagy open water swim

A módosítási javaslat legyen koherens ezzel a struktúrával. Pl. ha kedden (threshold bike napon) HRV-zuhanás van, a javaslat lehet "threshold helyett 60 perc Z2 lazább" – nem "csinálj futást".

Ha a sportoló friss megjegyzésében konkrét panaszt ír (pl. "fáj a térdem"), akkor a panasszal érintett szakág helyett ajánlj alternatívát (pl. térdfájdalomnál a futás helyett bicó vagy úszás).
"""


class DailyChecker:
    def __init__(self, api_key: str | None = None):
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Hiányzik az ANTHROPIC_API_KEY env változó")
        self.client = Anthropic(api_key=api_key)

    def check(
        self,
        recent_wellness: list[dict[str, Any]],
        yesterday_activity: dict[str, Any] | None,
        today_planned: str | None,
        athlete_notes: str | None = None,
    ) -> dict[str, Any]:
        """
        Lefuttat egy napi check-et, visszaad egy validált JSON dict-et.

        Args:
            recent_wellness: az utolsó 7-14 nap wellness sorai dict-ekként
            yesterday_activity: a tegnapi edzés dict-je (vagy None ha pihenőnap volt)
            today_planned: a heti tervből a mai nap leírása (string)
            athlete_notes: friss megjegyzés a sportolótól
        """
        today = dt.date.today().isoformat()

        user_parts = [
            f"# Mai dátum: {today}",
            f"\n# A heti tervből a mai napra előírt edzés:\n{today_planned or 'Nincs információ'}",
            f"\n# Az utóbbi {len(recent_wellness)} nap wellness adatai (legrégebbi → legújabb):",
            "```json",
            json.dumps(recent_wellness, indent=2, default=str, ensure_ascii=False),
            "```",
        ]

        if yesterday_activity:
            user_parts.append(
                "\n# Tegnapi edzés (tényleges):\n"
                "```json\n"
                + json.dumps(yesterday_activity, indent=2, default=str, ensure_ascii=False)
                + "\n```"
            )
        else:
            user_parts.append("\n# Tegnap: nem volt rögzített edzés (pihenőnap vagy nem szinkronizált).")

        if athlete_notes:
            user_parts.append(f"\n# A sportoló friss megjegyzése:\n{athlete_notes}")

        user_parts.append(
            "\n# Feladat\n"
            "Add vissza a kötelező JSON-t a fenti séma szerint. Csak a JSON-t, semmi mást."
        )

        user_message = "\n".join(user_parts)

        log.info("Haiku napi check hívása (prompt: %d karakter)", len(user_message))

        response = self.client.messages.create(
            model=DAILY_MODEL,
            max_tokens=DAILY_MAX_TOKENS,
            system=DAILY_SYSTEM_PROMPT,
            messages=[{"role": "user", "content": user_message}],
        )

        raw_text = "".join(
            getattr(b, "text", "") for b in response.content if getattr(b, "type", None) == "text"
        ).strip()

        log.info(
            "Haiku válasz: input=%d, output=%d tokens",
            response.usage.input_tokens, response.usage.output_tokens,
        )

        # JSON parse – védekezünk markdown-fence ellen
        cleaned = raw_text
        if cleaned.startswith("```"):
            # Vágjuk le az első és utolsó ``` sort
            m = re.search(r"```(?:json)?\s*(.+?)\s*```", cleaned, re.DOTALL)
            if m:
                cleaned = m.group(1).strip()

        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError as e:
            log.error("Haiku nem érvényes JSON-t adott: %s\nRaw: %s", e, raw_text[:500])
            # Fallback: zöld státusz, ne csináljon semmit
            data = {
                "status": "green",
                "headline": "Napi check nem értelmezhető – tartsd a tervet",
                "recommendation": "A rendszer nem tudta értelmezni a wellness adatokat. Kövesd a heti tervet, és figyelj a tested visszajelzéseire.",
                "modify_today": False,
                "today_alternative": None,
                "metrics": {
                    "hrv_status": "unknown",
                    "rhr_status": "unknown",
                    "sleep_status": "unknown",
                    "yesterday_load_status": "unknown",
                },
                "notes_acknowledgment": None,
                "_error": "json_parse_failed",
            }

        # Metaadatok hozzáadása
        data["generated_at"] = dt.datetime.now().isoformat(timespec="seconds")
        data["date"] = today
        return data
