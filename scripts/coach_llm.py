"""
Claude API kliens – strukturált JSON edzéstervet generál.

A modellnek nem HTML-t, hanem JSON-t adunk vissza:
  - Drámaian csökken a token-szükséglet (~6k vs ~15k output token)
  - Sokkal gyorsabb (15-30 sec vs 1-3 min)
  - Stabilabb (nincs HTML truncation-kockázat)
  - A modell minden tokenje a szakmai tartalomra megy, nem CSS-re

A HTML-t Python rendereli (renderer.py).

Modell ár-tudás (input/output $/MTok) — 2026 áprilisi árak:
  claude-haiku-4-5      $1 / $5    – egyszerű napi check-hez
  claude-sonnet-4-6     $3 / $15   – jó minőség, ~$0.10/heti futás
  claude-opus-4-7       $5 / $25   – legmagasabb minőség, cache-szel ~$0.23/heti futás

A prompt caching az Opus-szal kombinálva nagyon megéri:
  - A system prompt (~2500 token) gyakorlatilag ingyenessé válik az első futás után
  - 90% kedvezmény a cache-elt input tokeneken
"""
from __future__ import annotations

import json
import logging
import os
import re
from pathlib import Path

from anthropic import Anthropic

log = logging.getLogger(__name__)


# Az alapértelmezett modell most az Opus 4.7 (heti egyszer fut, megéri a minőség).
# Ha pénzt akarsz spórolni, állítsd át "claude-sonnet-4-6"-re a CLAUDE_MODEL env változóval.
DEFAULT_MODEL = "claude-opus-4-7"

# A JSON output ~6-8k token körül, max_tokens 16000 bőven elég biztonsági puffernek
DEFAULT_MAX_TOKENS = 16000


class CoachLLM:
    def __init__(
        self,
        api_key: str | None = None,
        model: str = DEFAULT_MODEL,
        max_tokens: int = DEFAULT_MAX_TOKENS,
        system_prompt_path: str | Path | None = None,
    ):
        api_key = api_key or os.environ.get("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("Hiányzik az ANTHROPIC_API_KEY env változó")

        # Az SDK natív retry-t és timeoutot használ
        self.client = Anthropic(
            api_key=api_key,
            timeout=180.0,
            max_retries=3,  # exponential backoff retry
        )
        self.model = model
        self.max_tokens = max_tokens

        if system_prompt_path is None:
            system_prompt_path = Path(__file__).parent.parent / "prompts" / "system_prompt.md"
        self.system_prompt = Path(system_prompt_path).read_text(encoding="utf-8")

    def generate_plan(
        self,
        athlete_snapshot_json: str,
        athlete_name: str,
        race_name: str = "Ironman 70.3",
        prev_race_results: dict | None = None,
        user_notes: str | None = None,
    ) -> dict:
        """
        Generál egy strukturált JSON edzéstervet a snapshot alapján.

        Visszatérési érték: a parsed dict, ami a JSON séma szerint van.
        """
        user_message_parts = [
            f"# A sportoló neve\n{athlete_name}",
            f"\n# A célverseny\n{race_name}",
        ]

        if prev_race_results:
            user_message_parts.append(
                "\n# Korábbi 70.3 verseny eredmények (referencia)\n"
                + "\n".join(f"- {k}: {v}" for k, v in prev_race_results.items())
            )

        if user_notes:
            user_message_parts.append(
                f"\n# A sportoló friss megjegyzései, érzései, prioritásai\n{user_notes}"
            )

        user_message_parts.append(
            "\n# Aktuális adat-snapshot (Intervals.icu / Garmin + származtatott metrikák)\n"
            "```json\n" + athlete_snapshot_json + "\n```\n"
        )
        user_message_parts.append(
            "\n# Feladat\n"
            "Készítsd el a teljes JSON tervet a séma szerint. CSAK a JSON-t add vissza, "
            "az első karakter `{`, az utolsó `}`. Semmi más szöveg, semmi markdown."
        )

        user_message = "\n".join(user_message_parts)

        log.info(
            "Claude hívás: model=%s, max_tokens=%d, prompt_chars=%d",
            self.model, self.max_tokens, len(user_message),
        )

        # PROMPT CACHING: a system prompt minden héten ugyanaz, ezért cache-elhető.
        # 90% kedvezmény az ismétlődő futásoknál.
        # A `system` paraméter most lista formátumban kell, hogy a cache_control hozzáadható legyen.
        system_blocks = [
            {
                "type": "text",
                "text": self.system_prompt,
                "cache_control": {"type": "ephemeral"},
            }
        ]

        chunks = []
        chunk_count = 0
        total_chars = 0

        with self.client.messages.stream(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_blocks,
            messages=[{"role": "user", "content": user_message}],
        ) as stream:
            for text in stream.text_stream:
                chunks.append(text)
                total_chars += len(text)
                chunk_count += 1
                # Progress log minden ~2000 karakterenként
                if total_chars > 0 and total_chars % 2000 < len(text):
                    log.info("  Streaming: %d chars beérkezett...", total_chars)

            response = stream.get_final_message()

        raw = "".join(chunks).strip()

        # Token-statisztika logolás (cache hit jelzéshez)
        usage = getattr(response, "usage", None)
        if usage:
            cache_read = getattr(usage, "cache_read_input_tokens", 0) or 0
            cache_create = getattr(usage, "cache_creation_input_tokens", 0) or 0
            input_tokens = getattr(usage, "input_tokens", 0) or 0
            output_tokens = getattr(usage, "output_tokens", 0) or 0
            log.info(
                "Token használat: input=%d (cache_read=%d, cache_create=%d), output=%d",
                input_tokens, cache_read, cache_create, output_tokens,
            )

        log.info("Claude válasz: %d chars, %d streaming chunk", len(raw), chunk_count)

        return _parse_json_response(raw)


def _parse_json_response(raw: str) -> dict:
    """Robosztus JSON parsing - kezeli a markdown fence-eket, csonka és hibás JSON-t."""
    s = raw.strip()

    # 1) Markdown fence eltávolítás
    if s.startswith("```"):
        m = re.search(r"```(?:json)?\s*(.+?)\s*```", s, re.DOTALL)
        if m:
            s = m.group(1).strip()

    # 2) Egyenes parse
    try:
        return json.loads(s)
    except json.JSONDecodeError:
        pass

    # 3) Első { és utolsó } közötti rész
    start = s.find("{")
    end = s.rfind("}")
    if start < 0 or end <= start:
        raise ValueError("Nem érvényes JSON érkezett a Claude-tól")
    candidate = s[start:end + 1]

    try:
        return json.loads(candidate)
    except json.JSONDecodeError as e:
        log.warning("Első JSON parse hibára futott (%s), helyreállítást próbálok...", e)

    # 4) Helyreállítás: nem-escape-elt idézőjelek javítása string értékekben
    fixed = _fix_unescaped_quotes(candidate)
    try:
        return json.loads(fixed)
    except json.JSONDecodeError as e:
        log.warning("Idézőjel-helyreállítás után is hiba: %s", e)

    # 5) Utolsó esély: a hibás sor ELŐTT levágjuk és lezárjuk a struktúrát
    try:
        e2 = None
        try:
            json.loads(candidate)
        except json.JSONDecodeError as exc:
            e2 = exc
        if e2:
            # Vágjuk a hibás pozíció ELŐTT az utolsó vesszőig vagy {/[ jelig
            cut = candidate.rfind(",", 0, e2.pos)
            if cut < 0:
                cut = max(candidate.rfind("{", 0, e2.pos), candidate.rfind("[", 0, e2.pos))
            if cut > 0:
                truncated = candidate[:cut]
                # Lezárjuk a nyitott struktúrákat
                opens_curly = truncated.count("{") - truncated.count("}")
                opens_square = truncated.count("[") - truncated.count("]")
                fix = truncated + ("]" * opens_square) + ("}" * opens_curly)
                try:
                    parsed = json.loads(fix)
                    log.warning("Sikerült részleges helyreállítás (a hibás mezőket vágtam le)")
                    return parsed
                except json.JSONDecodeError:
                    pass
    except Exception:
        pass

    log.error("JSON parse minden próbálkozás után hibára futott")
    log.error("Raw válasz első 1000 char: %s", raw[:1000])
    log.error("Raw válasz utolsó 500 char: %s", raw[-500:])
    raise ValueError("Érvénytelen JSON a Claude-tól, helyreállítás sem sikerült")


def _fix_unescaped_quotes(s: str) -> str:
    r"""
    Megpróbálja javítani a string-mezőkben levő nem-escape-elt idézőjeleket.

    Tipikus eset: "details": "5x30" gyorsítások" - itt a 30" perc-jel törs a string.
    Heurisztika: a string-belsőben lévő idézőjelek elé teszünk backslash-t, KIVÉVE
    azokat, amik logikailag string-zárók (utánuk : , ] vagy } jön opcionális whitespace után).
    """
    out = []
    i = 0
    in_string = False
    while i < len(s):
        c = s[i]
        if c == '\\' and in_string and i + 1 < len(s):
            # Escape sorozat - változatlanul átmásoljuk
            out.append(c)
            out.append(s[i + 1])
            i += 2
            continue
        if c == '"':
            if not in_string:
                in_string = True
                out.append(c)
                i += 1
                continue
            # Nézzük meg mi jön ezután: ha :, ',', ], } akkor ez valódi string-vég
            j = i + 1
            while j < len(s) and s[j] in " \t\n\r":
                j += 1
            if j >= len(s) or s[j] in ":,]}":
                in_string = False
                out.append(c)
                i += 1
                continue
            # Egyébként ez egy string-belsős idézőjel - escape-eljük
            out.append('\\"')
            i += 1
            continue
        out.append(c)
        i += 1
    return "".join(out)
