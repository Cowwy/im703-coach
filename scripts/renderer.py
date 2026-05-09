"""
HTML renderer - új layout: heti edzésterv fókuszban.

Hierarchia (felülről lefelé):
  1. Header (sportoló + visszaszámlálás + mai dátum)
  2. Napi banner (Haiku update)
  3. EZ A HÉT (fő szekció, mai nap kiemelve, részletes edzésstruktúrával)
  4. Versenynap stratégia (kompakt)
  5. Makrociklus áttekintés (kompakt táblázat)
  6. Háttér: profil / helyzetértékelés / hivatkozások (collapsible)
  7. Kockázatok (mindig látható, rövid)
"""
from __future__ import annotations

import datetime as dt
import html as html_mod
from typing import Any


SPORT_INFO = {
    "swim":     {"icon": "🏊", "label": "Úszás",   "color": "#3498db", "color_bg": "#ebf5fb"},
    "bike":     {"icon": "🚴", "label": "Kerékpár", "color": "#27ae60", "color_bg": "#eafaf1"},
    "run":      {"icon": "🏃", "label": "Futás",   "color": "#e74c3c", "color_bg": "#fdedec"},
    "strength": {"icon": "💪", "label": "Erő",     "color": "#9b59b6", "color_bg": "#f4ecf7"},
    "brick":    {"icon": "🚴→🏃", "label": "Brick", "color": "#e67e22", "color_bg": "#fef5e7"},
    "rest":     {"icon": "😌", "label": "Pihenő",  "color": "#95a5a6", "color_bg": "#f4f6f6"},
    "race":     {"icon": "🏁", "label": "Verseny", "color": "#c0392b", "color_bg": "#fadbd8"},
}

DAY_ORDER_HU = ["Hétfő", "Kedd", "Szerda", "Csütörtök", "Péntek", "Szombat", "Vasárnap"]


def _e(s: Any) -> str:
    """HTML escape, de az aposztrófot nem (csak <, >, & jeleket)."""
    if s is None:
        return ""
    return html_mod.escape(str(s), quote=False)


def _today_iso() -> str:
    return dt.date.today().isoformat()


# ============================================================
# A HETI EDZÉSTERV - a FŐ SZEKCIÓ
# ============================================================

def _render_target_chips(targets: dict | None) -> str:
    """A célértékeket kis pirulákban mutatja (HR, pace, watts, RPE)."""
    if not targets:
        return ""
    chips = []
    if targets.get("hr"):
        chips.append(f'<span class="chip chip-hr">❤️ HR: {_e(targets["hr"])}</span>')
    if targets.get("pace"):
        chips.append(f'<span class="chip chip-pace">⏱ Pace: {_e(targets["pace"])}</span>')
    if targets.get("watts"):
        chips.append(f'<span class="chip chip-watts">⚡ Watt: {_e(targets["watts"])}</span>')
    if targets.get("rpe"):
        chips.append(f'<span class="chip chip-rpe">📊 RPE: {_e(targets["rpe"])}</span>')
    if not chips:
        return ""
    return f'<div class="target-chips">{"".join(chips)}</div>'


def _render_main_block(item: dict) -> str:
    """A `main` lista egy elemét rendereli (block / intervals / brick / tempo)."""
    t = item.get("type", "block")

    if t == "intervals":
        label = item.get("label", "Intervallum")
        reps = item.get("reps", "?")
        work = item.get("work", {}) or {}
        rec = item.get("recovery", {}) or {}
        return f"""
<div class="main-block intervals-block">
  <div class="block-label">🔁 {_e(label)}</div>
  <div class="intervals-table">
    <div class="iv-row iv-header">
      <div>Ismétlés</div><div>Munka</div><div>Cél</div><div>Pihenő</div>
    </div>
    <div class="iv-row">
      <div class="iv-reps">{_e(reps)}×</div>
      <div class="iv-work">{_e(work.get("duration", "-"))}</div>
      <div class="iv-target">{_e(work.get("target", "-"))} <span class="iv-zone">{_e(work.get("intensity", ""))}</span></div>
      <div class="iv-rec">{_e(rec.get("duration", "-"))}<br><small>{_e(rec.get("target", ""))}</small></div>
    </div>
  </div>
</div>
"""

    if t == "brick":
        f = item.get("from") or {}
        to = item.get("to") or {}
        to_info = SPORT_INFO.get(to.get("sport", ""), {})

        # Ha from=null, csak az átmenet + új sport jelenik meg (kompaktabb)
        if not f:
            return f"""
<div class="main-block brick-block">
  <div class="block-label">🔄 Közvetlen átmenet az előző blokkból (brick)</div>
  <div class="brick-leg" style="border-color:{to_info.get("color", "#777")}">
    <span class="brick-icon">{to_info.get("icon", "")}</span>
    <strong>{_e(to.get("duration", ""))}</strong> – {_e(to.get("description", ""))}
  </div>
</div>
"""
        # Egyébként mindkét ág megjelenik
        f_info = SPORT_INFO.get(f.get("sport", ""), {})
        return f"""
<div class="main-block brick-block">
  <div class="block-label">🔄 Közvetlen átmenet (brick)</div>
  <div class="brick-leg" style="border-color:{f_info.get("color", "#777")}">
    <span class="brick-icon">{f_info.get("icon", "")}</span>
    <strong>{_e(f.get("duration", ""))}</strong> – {_e(f.get("description", ""))}
  </div>
  <div class="brick-arrow">↓</div>
  <div class="brick-leg" style="border-color:{to_info.get("color", "#777")}">
    <span class="brick-icon">{to_info.get("icon", "")}</span>
    <strong>{_e(to.get("duration", ""))}</strong> – {_e(to.get("description", ""))}
  </div>
</div>
"""

    if t == "tempo":
        return f"""
<div class="main-block tempo-block">
  <div class="block-label">⚡ Tempó / küszöb</div>
  <div class="tempo-line">
    <span class="tempo-duration">{_e(item.get("duration", "-"))}</span>
    <span class="tempo-target">{_e(item.get("target", ""))}</span>
  </div>
  {f'<div class="tempo-desc">{_e(item.get("description", ""))}</div>' if item.get("description") else ''}
</div>
"""

    # default: block
    return f"""
<div class="main-block plain-block">
  <span class="block-duration">{_e(item.get("duration", "-"))}</span>
  <span class="block-desc">{_e(item.get("description", ""))}</span>
</div>
"""


def _render_phase(label: str, phase: dict | None, css_class: str) -> str:
    """warmup / cooldown blokk renderelése."""
    if not phase:
        return ""
    return f"""
<div class="phase-block {css_class}">
  <span class="phase-label">{_e(label)}</span>
  <span class="phase-duration">{_e(phase.get("duration", ""))}</span>
  <span class="phase-desc">{_e(phase.get("description", ""))}</span>
</div>
"""


def _render_day_card(d: dict, is_today: bool, is_past: bool) -> str:
    sport = d.get("sport", "rest")
    info = SPORT_INFO.get(sport, SPORT_INFO["rest"])
    structure = d.get("structure") or {}

    # Card CSS classes
    classes = ["day-card", f"day-{sport}"]
    if is_today:
        classes.append("day-today")
    elif is_past:
        classes.append("day-past")

    today_badge = '<span class="today-badge">📍 MA</span>' if is_today else ""

    # Edzés blokkok
    main_html = ""
    main_items = structure.get("main") or []
    for item in main_items:
        main_html += _render_main_block(item)

    warmup_html = _render_phase("🔥 Bemelegítés", structure.get("warmup"), "warmup")
    cooldown_html = _render_phase("❄️ Levezetés", structure.get("cooldown"), "cooldown")

    targets_html = _render_target_chips(d.get("targets"))

    fueling_html = ""
    if d.get("fueling"):
        fueling_html = f'<div class="fueling-note">🥤 <strong>Táplálkozás:</strong> {_e(d["fueling"])}</div>'

    notes_html = ""
    if d.get("notes"):
        notes_html = f'<div class="day-note">💡 {_e(d["notes"])}</div>'

    return f"""
<div class="{' '.join(classes)}" style="--sport-color:{info["color"]}; --sport-bg:{info["color_bg"]}">
  <div class="day-card-header">
    <div class="day-meta">
      <span class="day-name">{_e(d.get("day", ""))}{today_badge}</span>
      <span class="day-date">{_e(d.get("date", ""))}</span>
    </div>
    <div class="sport-tag" style="background:{info["color"]}">
      {info["icon"]} {info["label"]}
    </div>
  </div>

  <div class="day-card-body">
    <h3 class="day-title">{_e(d.get("title", ""))}</h3>
    <div class="day-summary">{_e(d.get("summary", ""))}</div>

    <div class="day-stats">
      <span class="stat"><strong>{_e(d.get("duration_min", "-"))}'</strong> időtartam</span>
      <span class="stat stat-zone">{_e(d.get("intensity", "-"))}</span>
      <span class="stat">~<strong>{_e(d.get("tss_estimate", "-"))}</strong> TSS</span>
    </div>

    {targets_html}

    {warmup_html}
    {f'<div class="main-section">{main_html}</div>' if main_html else ''}
    {cooldown_html}

    {fueling_html}
    {notes_html}
  </div>
</div>
"""


def _render_current_week_FOCUS(plan: dict) -> str:
    """A heti edzésterv – a fő szekció, vizuális hangsúlyban."""
    w = plan.get("current_week", {})
    days = w.get("days", []) or []

    # Dátum szerinti sortolás (a Claude mai naptól induló 7 napot ad).
    # Ha valamelyiknek nincs date-je, a HU napsor alapján kerül a végére.
    def sort_key(d: dict) -> tuple:
        date = d.get("date", "")
        if date:
            return (0, date)
        try:
            return (1, DAY_ORDER_HU.index(d.get("day", "Hétfő")))
        except ValueError:
            return (2, 99)
    days_sorted = sorted(days, key=sort_key)

    today_iso = _today_iso()
    cards = []
    for d in days_sorted:
        d_date = d.get("date", "")
        is_today = d_date == today_iso
        is_past = d_date < today_iso if d_date else False
        cards.append(_render_day_card(d, is_today, is_past))

    target_tss = w.get("target_tss", "-")
    week_label = w.get("week_label", "Aktuális hét")
    week_focus = w.get("week_focus", "")

    return f"""
<section class="section section-current-week">
  <div class="week-header">
    <div>
      <h2 class="week-title">🎯 {_e(week_label)}</h2>
      <p class="week-focus">{_e(week_focus)}</p>
    </div>
    <div class="week-stats">
      <div class="week-stat-big">
        <span class="big-num">{_e(target_tss)}</span>
        <span class="big-label">heti cél TSS</span>
      </div>
    </div>
  </div>
  <div class="day-cards">
    {"".join(cards)}
  </div>
</section>
"""


# ============================================================
# Versenynap stratégia (kompakt)
# ============================================================

def _render_race_strategy(plan: dict) -> str:
    g = plan.get("race_goal", {}) or {}
    st = plan.get("race_strategy", {}) or {}
    nut = st.get("nutrition", {}) or {}

    a = g.get("scenario_a", {}) or {}
    b = g.get("scenario_b", {}) or {}
    c = g.get("scenario_c", {}) or {}

    def goal_card(s: dict, color: str, badge: str) -> str:
        return f"""
<div class="goal-card" style="border-top-color:{color}">
  <div class="goal-badge" style="background:{color}">{_e(badge)}</div>
  <div class="goal-label">{_e(s.get("label", ""))}</div>
  <div class="goal-total">{_e(s.get("total", "-"))}</div>
  <div class="goal-splits">
    <span>🏊 {_e(s.get("swim", "-"))}</span>
    <span>🚴 {_e(s.get("bike", "-"))}</span>
    <span>🏃 {_e(s.get("run", "-"))}</span>
  </div>
</div>
"""

    return f"""
<section class="section section-race">
  <h2>🏁 Versenynap stratégia</h2>
  <p class="race-meta">{_e(g.get("race_date", "-"))} • {_e(g.get("weeks_to_race", "-"))} hét múlva</p>

  <div class="goal-grid">
    {goal_card(a, "#27ae60", "A")}
    {goal_card(b, "#f39c12", "B")}
    {goal_card(c, "#e74c3c", "C")}
  </div>
  <p class="rationale">{_e(g.get("rationale", ""))}</p>

  <div class="race-strategy-grid">
    <div class="strategy-mini swim"><h4>🏊 Úszás</h4><p>{_e(st.get("swim", ""))}</p></div>
    <div class="strategy-mini bike"><h4>🚴 Kerékpár</h4><p>{_e(st.get("bike", ""))}</p></div>
    <div class="strategy-mini run"><h4>🏃 Futás</h4><p>{_e(st.get("run", ""))}</p></div>
    <div class="strategy-mini nutrition">
      <h4>🥤 Táplálkozás</h4>
      <p><strong>{_e(nut.get("carb_per_hour", "-"))} CH</strong> • <strong>{_e(nut.get("fluid_per_hour", "-"))}</strong> folyadék • <strong>{_e(nut.get("sodium_per_hour", "-"))} Na</strong> óránként</p>
      <p>{_e(nut.get("details", ""))}</p>
    </div>
  </div>
  <p class="pacing-principle"><strong>Pacing:</strong> {_e(st.get("pacing_principle", ""))}</p>
</section>
"""


# ============================================================
# Makrociklus áttekintés (kompakt)
# ============================================================

def _render_macrocycle(plan: dict) -> str:
    m = plan.get("macrocycle_outlook", {}) or {}
    weeks = m.get("weeks", []) or []
    if not weeks:
        return ""

    rows = []
    for w in weeks:
        rows.append(f"""
<tr>
  <td class="macro-offset">+{_e(w.get("week_offset", "-"))}</td>
  <td><strong>{_e(w.get("label", ""))}</strong></td>
  <td>{_e(w.get("target_tss", "-"))}</td>
  <td>{_e(w.get("expected_ctl", "-"))}</td>
  <td class="macro-key">{_e(w.get("key_session", ""))}</td>
</tr>""")

    return f"""
<section class="section section-macro">
  <h2>📅 Makrociklus a versenyig</h2>
  <table class="macro-table">
    <thead>
      <tr><th>Hét</th><th>Címke</th><th>Cél TSS</th><th>Várható CTL</th><th>Kulcs edzés</th></tr>
    </thead>
    <tbody>{"".join(rows)}</tbody>
  </table>
</section>
"""


# ============================================================
# Háttér szekciók (collapsible <details>)
# ============================================================

def _fmt_metric(label: str, value: Any) -> str:
    if value is None or value == "":
        return ""
    return (
        f'<div class="metric"><span class="metric-label">{_e(label)}</span>'
        f'<span class="metric-value">{_e(value)}</span></div>'
    )


def _render_zones(zones: Any, label: str) -> str:
    if not zones:
        return ""
    if isinstance(zones, str):
        return f'<div class="zone-row"><strong>{_e(label)}:</strong> {_e(zones)}</div>'
    if isinstance(zones, dict):
        items = "".join(
            f'<span class="zone"><b>{_e(k.upper())}</b> {_e(v)}</span>' for k, v in zones.items()
        )
        return f'<div class="zone-row"><strong>{_e(label)}:</strong> {items}</div>'
    return ""


def _render_background_profile(plan: dict) -> str:
    p = plan.get("athlete_profile", {}) or {}
    phys = p.get("physiology", {}) or {}
    perf = p.get("performance_metrics", {}) or {}
    zones = p.get("training_zones", {}) or {}
    pattern = p.get("recent_pattern", {}) or {}

    physiology_html = "".join([
        _fmt_metric("VO₂max", phys.get("vo2max_estimate")),
        _fmt_metric("LTHR", phys.get("lthr")),
        _fmt_metric("RHR", phys.get("rhr")),
        _fmt_metric("Súly", phys.get("weight")),
        _fmt_metric("FTP (bike)", phys.get("ftp_bike")),
        _fmt_metric("Threshold pace", phys.get("threshold_pace_run")),
        _fmt_metric("CSS úszás", phys.get("css_swim")),
    ])

    perf_html = "".join([
        _fmt_metric("CTL (fitness)", perf.get("ctl_current")),
        _fmt_metric("ATL (fatigue)", perf.get("atl_current")),
        _fmt_metric("TSB (form)", perf.get("tsb_current")),
        _fmt_metric("28d CTL trend", perf.get("ctl_trend_28d")),
        _fmt_metric("Ramp rate", perf.get("ramp_rate")),
    ])

    zones_html = (
        _render_zones(zones.get("hr_zones_run"), "HR zónák (futás)") +
        _render_zones(zones.get("hr_zones_bike"), "HR zónák (bike)") +
        _render_zones(zones.get("pace_zones_run"), "Tempó zónák") +
        _render_zones(zones.get("power_zones_bike"), "Watt zónák") +
        _render_zones(zones.get("swim_css_pace"), "CSS pace")
    )

    return f"""
<details class="bg-section">
  <summary><span class="bg-icon">📊</span> Sportolói profil <span class="bg-hint">(részletek)</span></summary>
  <div class="bg-content">
    <p class="lead">{_e(p.get("summary", ""))}</p>

    <h4>Fiziológia</h4>
    <div class="data-grid">{physiology_html}</div>

    <h4>Teljesítménymutatók (PMC)</h4>
    <div class="data-grid">{perf_html}</div>

    <h4>Edzészónák</h4>
    {zones_html or '<p class="muted">Nincs elegendő adat.</p>'}

    <h4>Eddigi minta</h4>
    <p>{_e(pattern.get("weeks_summary", ""))}</p>
    {f'<p><strong>Korábbi 70.3:</strong> {_e(pattern.get("previous_race"))}</p>' if pattern.get("previous_race") else ''}
    {f'<p class="key-obs"><strong>Megfigyelés:</strong> {_e(pattern.get("key_observation"))}</p>' if pattern.get("key_observation") else ''}
  </div>
</details>
"""


def _render_background_situation(plan: dict) -> str:
    s = plan.get("situation_assessment", {}) or {}
    priorities = s.get("key_priorities", []) or []
    warnings = s.get("warnings", []) or []

    pri_html = "".join(f"<li>{_e(p)}</li>" for p in priorities)
    warn_html = ""
    if warnings:
        items = "".join(f"<li>{_e(w)}</li>" for w in warnings)
        warn_html = f'<div class="alert"><strong>⚠️ Figyelem:</strong><ul>{items}</ul></div>'

    return f"""
<details class="bg-section">
  <summary><span class="bg-icon">🧭</span> Helyzetértékelés és makrociklus indoklás <span class="bg-hint">(részletek)</span></summary>
  <div class="bg-content">
    <p><strong>Aktuális fázis:</strong> <span class="phase-badge">{_e(s.get("current_phase", "?").upper())}</span></p>
    <p>{_e(s.get("phase_rationale", ""))}</p>

    <h4>Fő prioritások</h4>
    <ol class="priorities">{pri_html}</ol>

    {warn_html}
  </div>
</details>
"""


def _render_background_references(plan: dict) -> str:
    refs = plan.get("scientific_references", []) or []
    if not refs:
        return ""
    items = "".join(
        f'<li><strong>{_e(r.get("topic", ""))}:</strong> <span class="ref">{_e(r.get("source", ""))}</span></li>'
        for r in refs
    )
    return f"""
<details class="bg-section">
  <summary><span class="bg-icon">📚</span> Tudományos hivatkozások <span class="bg-hint">(részletek)</span></summary>
  <div class="bg-content">
    <ul class="references">{items}</ul>
  </div>
</details>
"""


# ============================================================
# Kockázatok (mindig látható, kompakt)
# ============================================================

def _render_risks(plan: dict) -> str:
    r = plan.get("risks_and_notes", {}) or {}
    risk_level = r.get("overtraining_risk", "low")
    risk_color = {"low": "#27ae60", "moderate": "#f39c12", "high": "#e74c3c"}.get(risk_level, "#95a5a6")

    injury = r.get("injury_risk_areas", []) or []
    injury_html = ""
    if injury:
        items = "".join(f"<li>{_e(i)}</li>" for i in injury)
        injury_html = f"<div class='risk-col'><strong>Sérülés-figyelem</strong><ul>{items}</ul></div>"

    alts = r.get("alternative_scenarios", []) or []
    alts_html = ""
    if alts:
        items = "".join(f"<li>{_e(a)}</li>" for a in alts)
        alts_html = f"<div class='risk-col'><strong>Alternatívák</strong><ul>{items}</ul></div>"

    notes_ack = r.get("athlete_notes_acknowledgment")
    notes_html = (
        f'<div class="alert info"><strong>📝 Figyelembe véve:</strong> {_e(notes_ack)}</div>'
        if notes_ack else ""
    )

    return f"""
<section class="section section-risks">
  <h2>⚠️ Kockázatok és megjegyzések</h2>
  <p><strong>Túledzés-kockázat:</strong> <span class="risk-pill" style="background:{risk_color}">{_e(risk_level.upper())}</span> – {_e(r.get("overtraining_note", ""))}</p>
  <div class="risk-grid">
    {injury_html}
    {alts_html}
  </div>
  {notes_html}
</section>
"""


# ============================================================
# CSS és JS (banner)
# ============================================================

CSS = """
:root {
  --c-primary: #1a1a2e;
  --c-secondary: #0f3460;
  --c-accent: #e94560;
  --c-bg: #f0f2f5;
  --c-card: #ffffff;
  --c-text: #2d3436;
  --c-text-light: #5d6d7e;
  --c-muted: #95a5a6;
  --c-border: #e0e0e0;
  --c-today: #e94560;
}
* { box-sizing: border-box; }
body {
  font-family: 'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', sans-serif;
  margin: 0; padding: 0; color: var(--c-text); background: var(--c-bg); line-height: 1.55;
}
.container { max-width: 1100px; margin: 0 auto; padding: 24px; }

/* HEADER */
header.main {
  background: linear-gradient(135deg, var(--c-primary) 0%, var(--c-secondary) 100%);
  color: white; padding: 32px 24px 28px; text-align: center;
}
header.main h1 { margin: 0 0 6px; font-size: 26px; }
header.main .meta { margin: 4px 0; opacity: 0.85; font-size: 13px; }
header.main .race-countdown {
  display: inline-block; background: var(--c-accent); padding: 6px 18px;
  border-radius: 20px; margin-top: 10px; font-weight: 600; font-size: 13px;
}
header.main .today-line { font-size: 12px; margin-top: 8px; opacity: 0.7; }

/* SECTION (general) */
.section {
  background: var(--c-card); border-radius: 14px; padding: 22px 24px; margin-bottom: 18px;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.section h2 {
  margin: 0 0 14px; font-size: 20px; color: var(--c-primary);
}
.section h3, .section h4 { color: var(--c-secondary); margin: 14px 0 8px; }
.section h4 { font-size: 13px; margin-top: 16px; }

/* === EZ A HÉT (FŐ SZEKCIÓ) === */
.section-current-week {
  border: 2px solid var(--c-accent);
  padding: 26px 24px;
}
.week-header {
  display: flex; justify-content: space-between; align-items: flex-start;
  gap: 20px; margin-bottom: 20px; flex-wrap: wrap;
}
.week-title { margin: 0; font-size: 24px; color: var(--c-primary); }
.week-focus { margin: 6px 0 0; color: var(--c-text-light); font-size: 14px; }
.week-stat-big {
  background: var(--c-accent); color: white; padding: 10px 18px; border-radius: 10px;
  text-align: center; min-width: 110px;
}
.week-stat-big .big-num { display: block; font-size: 24px; font-weight: 700; line-height: 1; }
.week-stat-big .big-label { display: block; font-size: 10px; text-transform: uppercase; letter-spacing: 0.5px; margin-top: 4px; opacity: 0.95; }

.day-cards { display: flex; flex-direction: column; gap: 12px; }

.day-card {
  background: var(--c-card); border: 1px solid var(--c-border); border-radius: 12px;
  border-left: 5px solid var(--sport-color, #95a5a6);
  overflow: hidden;
}
.day-card.day-past { opacity: 0.55; }
.day-card.day-today {
  border: 2px solid var(--c-today); border-left-width: 5px;
  box-shadow: 0 4px 16px rgba(233, 69, 96, 0.15);
  background: linear-gradient(to right, var(--sport-bg, #fff) 0%, var(--c-card) 30%);
}
.day-card-header {
  display: flex; justify-content: space-between; align-items: center;
  padding: 12px 18px; background: var(--sport-bg, #f8f9fa); border-bottom: 1px solid var(--c-border);
}
.day-meta { display: flex; flex-direction: column; gap: 2px; }
.day-name { font-weight: 700; font-size: 16px; display: flex; align-items: center; gap: 8px; }
.day-date { font-size: 11px; color: var(--c-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.today-badge {
  background: var(--c-today); color: white; padding: 2px 10px; border-radius: 12px;
  font-size: 11px; font-weight: 700; letter-spacing: 0.5px;
}
.sport-tag {
  color: white; padding: 5px 12px; border-radius: 20px;
  font-size: 12px; font-weight: 600; white-space: nowrap;
}
.day-card-body { padding: 16px 18px 18px; }
.day-title { margin: 0 0 4px; font-size: 17px; color: var(--c-primary); border: none; }
.day-summary { color: var(--c-text-light); font-size: 13px; margin-bottom: 12px; }
.day-stats {
  display: flex; gap: 14px; flex-wrap: wrap; margin-bottom: 14px;
  font-size: 13px; color: var(--c-text-light);
}
.day-stats .stat { background: var(--c-bg); padding: 4px 10px; border-radius: 6px; }
.day-stats .stat-zone { background: var(--sport-color); color: white; font-weight: 600; }

.target-chips { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 12px; }
.chip {
  display: inline-block; padding: 4px 10px; border-radius: 14px; font-size: 12px;
  background: var(--c-bg); border: 1px solid var(--c-border);
}
.chip-hr { background: #fdedec; border-color: #f5b7b1; }
.chip-pace { background: #ebf5fb; border-color: #aed6f1; }
.chip-watts { background: #fef9e7; border-color: #f7dc6f; }
.chip-rpe { background: #f4ecf7; border-color: #d2b4de; }

.phase-block {
  display: flex; gap: 10px; align-items: baseline; padding: 8px 12px;
  background: var(--c-bg); border-radius: 6px; margin: 6px 0; font-size: 13px;
}
.phase-block.warmup { border-left: 3px solid #f39c12; }
.phase-block.cooldown { border-left: 3px solid #3498db; }
.phase-label { font-weight: 600; color: var(--c-text); }
.phase-duration { color: var(--c-secondary); font-weight: 600; }
.phase-desc { color: var(--c-text-light); flex: 1; }

.main-section { margin: 8px 0; }
.main-block {
  background: linear-gradient(to bottom, var(--sport-bg, #f8f9fa), var(--c-card));
  border: 1px solid var(--c-border); border-left: 4px solid var(--sport-color, #95a5a6);
  border-radius: 8px; padding: 12px 14px; margin: 8px 0;
}
.block-label { font-size: 11px; text-transform: uppercase; letter-spacing: 0.6px; color: var(--c-secondary); font-weight: 700; margin-bottom: 8px; }
.plain-block { display: flex; gap: 12px; align-items: baseline; padding: 10px 14px; }
.block-duration { font-weight: 700; font-size: 15px; color: var(--c-primary); min-width: 60px; }
.block-desc { font-size: 14px; color: var(--c-text); }

.intervals-table { display: grid; gap: 4px; font-size: 13px; }
.iv-row { display: grid; grid-template-columns: 80px 1fr 2fr 1fr; gap: 10px; padding: 8px 10px; align-items: center; }
.iv-header { background: var(--c-secondary); color: white; font-weight: 600; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; border-radius: 6px; }
.iv-row:not(.iv-header) { background: white; border: 1px solid var(--c-border); border-radius: 6px; }
.iv-reps { font-size: 22px; font-weight: 800; color: var(--sport-color); }
.iv-work { font-weight: 600; color: var(--c-primary); }
.iv-target { color: var(--c-text); }
.iv-zone { display: inline-block; background: var(--sport-color); color: white; padding: 2px 8px; border-radius: 3px; font-size: 11px; margin-left: 4px; }
.iv-rec { font-size: 12px; color: var(--c-text-light); }

.brick-block .brick-leg {
  background: white; border: 1px solid var(--c-border); border-left: 4px solid;
  border-radius: 6px; padding: 10px 12px; margin: 4px 0; font-size: 13px;
}
.brick-icon { font-size: 18px; margin-right: 6px; }
.brick-arrow { text-align: center; font-size: 20px; color: var(--c-accent); margin: 2px 0; font-weight: 700; }

.tempo-block .tempo-line { display: flex; gap: 14px; align-items: baseline; }
.tempo-duration { font-size: 22px; font-weight: 800; color: var(--c-primary); }
.tempo-target { color: var(--sport-color); font-weight: 600; }
.tempo-desc { font-size: 13px; color: var(--c-text-light); margin-top: 6px; }

.fueling-note {
  background: #fef9e7; border-left: 3px solid #f7dc6f; padding: 8px 12px;
  border-radius: 6px; font-size: 13px; margin-top: 10px;
}
.day-note {
  background: #ebf5fb; border-left: 3px solid #5dade2; padding: 8px 12px;
  border-radius: 6px; font-size: 13px; margin-top: 10px; color: var(--c-secondary);
}

/* RACE STRATEGY */
.section-race { background: linear-gradient(135deg, #fff 0%, #fdf2f4 100%); }
.race-meta { color: var(--c-text-light); margin-top: 0; }
.goal-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap: 12px; margin: 14px 0; }
.goal-card {
  background: white; padding: 14px; border-radius: 10px; border-top: 4px solid;
  text-align: center; position: relative;
  box-shadow: 0 1px 3px rgba(0,0,0,0.05);
}
.goal-badge {
  position: absolute; top: -12px; left: 50%; transform: translateX(-50%);
  color: white; width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  font-weight: 700; font-size: 13px;
}
.goal-label { font-size: 12px; color: var(--c-muted); margin: 8px 0 4px; }
.goal-total { font-size: 26px; font-weight: 700; color: var(--c-primary); margin: 4px 0; }
.goal-splits { display: flex; justify-content: space-around; font-size: 12px; color: var(--c-text-light); margin-top: 8px; }
.rationale { font-style: italic; color: var(--c-text-light); margin: 8px 0; font-size: 13px; }

.race-strategy-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 10px; margin: 14px 0; }
.strategy-mini {
  background: white; padding: 12px 14px; border-radius: 8px;
  border-top: 3px solid var(--c-secondary); font-size: 13px;
}
.strategy-mini h4 { margin: 0 0 6px; font-size: 13px; }
.strategy-mini p { margin: 0; color: var(--c-text-light); }
.strategy-mini.swim { border-top-color: #3498db; }
.strategy-mini.bike { border-top-color: #27ae60; }
.strategy-mini.run { border-top-color: #e74c3c; }
.strategy-mini.nutrition { border-top-color: #f39c12; }
.pacing-principle { background: var(--c-bg); padding: 10px 14px; border-radius: 8px; font-size: 13px; }

/* MACROCYCLE */
.macro-table { width: 100%; border-collapse: collapse; font-size: 13px; }
.macro-table th { background: var(--c-secondary); color: white; padding: 8px 10px; text-align: left; font-size: 11px; text-transform: uppercase; }
.macro-table td { padding: 8px 10px; border-bottom: 1px solid var(--c-border); }
.macro-table tr:nth-child(even) td { background: var(--c-bg); }
.macro-offset { font-weight: 700; color: var(--c-accent); font-family: monospace; }
.macro-key { color: var(--c-text-light); font-style: italic; }

/* BACKGROUND COLLAPSIBLE */
.bg-section {
  background: var(--c-card); border-radius: 10px; margin-bottom: 12px;
  box-shadow: 0 1px 2px rgba(0,0,0,0.04); overflow: hidden;
}
.bg-section summary {
  cursor: pointer; padding: 14px 18px; font-weight: 600; color: var(--c-text);
  display: flex; align-items: center; gap: 10px;
  list-style: none; user-select: none;
}
.bg-section summary::-webkit-details-marker { display: none; }
.bg-section summary::before {
  content: "▶"; color: var(--c-muted); font-size: 11px;
  transition: transform 0.2s;
}
.bg-section[open] summary::before { transform: rotate(90deg); }
.bg-section summary:hover { background: var(--c-bg); }
.bg-icon { font-size: 16px; }
.bg-hint { color: var(--c-muted); font-size: 12px; font-weight: 400; margin-left: auto; }
.bg-content { padding: 4px 18px 18px; border-top: 1px solid var(--c-border); }
.bg-content .lead { font-size: 14px; color: var(--c-secondary); }

.data-grid { display: grid; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); gap: 10px; margin: 8px 0; }
.metric { background: var(--c-bg); padding: 10px; border-radius: 6px; border-left: 3px solid var(--c-accent); }
.metric-label { display: block; font-size: 10px; color: var(--c-muted); text-transform: uppercase; letter-spacing: 0.5px; }
.metric-value { display: block; font-size: 14px; font-weight: 600; margin-top: 2px; }
.zone-row { margin: 6px 0; font-size: 13px; }
.zone { display: inline-block; background: var(--c-bg); padding: 3px 9px; border-radius: 4px; margin: 2px; font-size: 12px; }
.phase-badge { background: var(--c-accent); color: white; padding: 3px 10px; border-radius: 4px; font-weight: 600; font-size: 12px; letter-spacing: 0.5px; }
.priorities { padding-left: 20px; }
.priorities li { margin-bottom: 6px; font-size: 14px; }
.alert { background: #fff3cd; border-left: 4px solid #ffc107; padding: 10px 14px; border-radius: 6px; margin: 10px 0; font-size: 13px; }
.alert.info { background: #d1ecf1; border-left-color: #0dcaf0; }
.alert ul { margin: 4px 0 0 18px; }
.references { padding-left: 18px; font-size: 12px; }
.references li { margin-bottom: 6px; }
.ref { color: var(--c-muted); font-style: italic; }
.key-obs { background: var(--c-bg); padding: 10px 14px; border-left: 3px solid var(--c-accent); border-radius: 4px; font-size: 13px; }
.muted { color: var(--c-muted); font-style: italic; }

/* RISKS */
.section-risks { background: #fffbf5; }
.risk-pill { color: white; padding: 2px 10px; border-radius: 4px; font-weight: 600; font-size: 11px; letter-spacing: 0.5px; }
.risk-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; margin-top: 10px; font-size: 13px; }
.risk-grid ul { padding-left: 18px; margin: 4px 0 0; }

/* FOOTER */
footer { text-align: center; padding: 22px 24px; color: var(--c-muted); font-size: 11px; }

/* Daily banner */
.daily-banner { max-width: 1100px; margin: 16px auto 0; padding: 0 24px; }
.daily-banner .card {
  border-radius: 12px; padding: 16px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.1);
  display: flex; align-items: flex-start; gap: 14px;
}
.daily-banner.green .card { background: #d4edda; border-left: 6px solid #27ae60; }
.daily-banner.yellow .card { background: #fff3cd; border-left: 6px solid #ffc107; }
.daily-banner.red .card { background: #f8d7da; border-left: 6px solid #dc3545; }
.daily-banner .icon { font-size: 28px; line-height: 1; }
.daily-banner .content { flex: 1; }
.daily-banner h3 { margin: 0 0 4px; font-size: 15px; font-weight: 700; }
.daily-banner p { margin: 0; font-size: 13px; line-height: 1.5; }
.daily-banner .meta { font-size: 11px; opacity: 0.7; margin-top: 6px; text-transform: uppercase; letter-spacing: 0.5px; }
.daily-banner .alt { background: rgba(0,0,0,0.06); border-radius: 6px; padding: 8px 12px; margin-top: 8px; font-size: 13px; }
.daily-banner .alt strong { display: block; margin-bottom: 3px; font-size: 11px; text-transform: uppercase; letter-spacing: 0.5px; }

/* Stale data warning banner */
.stale-banner {
  max-width: 1100px; margin: 16px auto 0; padding: 0 24px;
}
.stale-banner .card {
  background: #fff3cd; border-left: 6px solid #ffc107; border-radius: 12px;
  padding: 12px 18px; display: flex; align-items: center; gap: 12px;
  font-size: 13px; color: #856404;
}
.stale-banner .icon { font-size: 22px; }

@media (max-width: 600px) {
  .container { padding: 16px; }
  .section { padding: 16px; }
  .iv-row { grid-template-columns: 60px 1fr; gap: 6px; }
  .iv-header > div:nth-child(3), .iv-header > div:nth-child(4),
  .iv-row:not(.iv-header) > div:nth-child(3), .iv-row:not(.iv-header) > div:nth-child(4) {
    grid-column: span 2;
  }
  .week-header { flex-direction: column; }
  .risk-grid { grid-template-columns: 1fr; }
}

@media print {
  body { background: white; }
  .section { box-shadow: none; page-break-inside: avoid; }
  header.main { background: var(--c-primary); }
  .bg-section { box-shadow: none; }
  .bg-section[open] summary::before { display: none; }
  details { page-break-inside: avoid; }
}
"""


BANNER_JS = """
(async function(){
  try {
    const r = await fetch('daily_status.json?t=' + Date.now());
    if (!r.ok) return;
    const d = await r.json();
    const icon = d.status === 'green' ? '✅' : (d.status === 'yellow' ? '⚠️' : '🛑');
    const altHtml = d.modify_today && d.today_alternative
      ? `<div class="alt"><strong>Mai módosított edzés:</strong>${d.today_alternative}</div>` : '';
    const notesHtml = d.notes_acknowledgment
      ? `<div class="alt"><strong>Figyelembe véve:</strong>${d.notes_acknowledgment}</div>` : '';
    const mount = document.getElementById('daily-banner-mount');
    if (!mount) return;
    mount.outerHTML = `<div class="daily-banner ${d.status}"><div class="card">
      <div class="icon">${icon}</div>
      <div class="content">
        <h3>${d.headline}</h3>
        <p>${d.recommendation}</p>
        ${altHtml}${notesHtml}
        <div class="meta">Napi check: ${d.date} ${d.generated_at ? '• ' + d.generated_at.substring(11,16) : ''}</div>
      </div></div></div>`;
  } catch(e) { console.warn('Napi banner nem tölthető:', e); }
})();
"""


def render_plan_html(
    plan: dict,
    athlete_name: str,
    race_name: str = "Ironman 70.3",
    race_date: str | None = None,
    generated_at: dt.datetime | None = None,
) -> str:
    """A teljes JSON tervből előállít egy önálló HTML dokumentumot."""
    if generated_at is None:
        generated_at = dt.datetime.now()

    rg = plan.get("race_goal", {}) or {}
    weeks_to_race = rg.get("weeks_to_race", "?")

    today = dt.date.today()
    months_hu = ["", "január", "február", "március", "április", "május", "június",
                 "július", "augusztus", "szeptember", "október", "november", "december"]
    days_hu = ["hétfő", "kedd", "szerda", "csütörtök", "péntek", "szombat", "vasárnap"]
    today_str = f"{today.year}. {months_hu[today.month]} {today.day}. {days_hu[today.weekday()]}"

    # Adat-frissességi figyelmeztetés (ha a Claude vagy a Python jelez)
    stale_banner_html = ""
    risks = plan.get("risks_and_notes", {}) or {}
    warnings = risks.get("warnings") or []
    stale_warnings = [w for w in warnings if isinstance(w, str) and (
        "wellness" in w.lower() or "szinkron" in w.lower() or "garmin" in w.lower()
    )]
    if stale_warnings:
        stale_banner_html = f"""
<div class="stale-banner">
  <div class="card">
    <span class="icon">⚠️</span>
    <span>{_e(stale_warnings[0])}</span>
  </div>
</div>"""

    body_parts = [
        # 1. EZ A HÉT - a fő szekció, legtetejére!
        _render_current_week_FOCUS(plan),
        # 2. Versenynap stratégia
        _render_race_strategy(plan),
        # 3. Makrociklus áttekintés
        _render_macrocycle(plan),
        # 4. Háttér szekciók (collapsible)
        '<h2 style="margin: 28px 0 14px; font-size: 16px; color: var(--c-text-light); text-transform: uppercase; letter-spacing: 1px; font-weight: 600;">📖 Háttér – mi alapján hozta a terv döntéseit</h2>',
        _render_background_situation(plan),
        _render_background_profile(plan),
        _render_background_references(plan),
        # 5. Kockázatok (mindig látható, rövid)
        _render_risks(plan),
    ]

    return f"""<!DOCTYPE html>
<html lang="hu">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{_e(athlete_name)} – {_e(race_name)}</title>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap" rel="stylesheet">
<style>{CSS}</style>
</head>
<body>

<header class="main">
  <h1>{_e(athlete_name)} – {_e(race_name)}</h1>
  <p class="meta">Versenynap: {_e(race_date or rg.get("race_date", "-"))} • Frissítve: {generated_at.strftime("%Y-%m-%d %H:%M")}</p>
  <div class="race-countdown">⏱ Versenyig: {_e(weeks_to_race)} hét</div>
  <p class="today-line">📍 Ma: {today_str}</p>
</header>

{stale_banner_html}

<div id="daily-banner-mount"></div>
<script>{BANNER_JS}</script>

<div class="container">
{''.join(body_parts)}
</div>

<footer>
  Generálva: AI Coach (Claude) • Forrás: Intervals.icu / Garmin Connect • Az automatikusan generált terv NEM helyettesíti a szakképzett edző véleményét.
</footer>
</body>
</html>
"""
