# 🏊‍♂️🚴‍♂️🏃‍♂️ IM 70.3 AI Coach

**Automatizált, Claude-alapú AI edző**, amely az Intervals.icu / Strava adataidból minden héten új, személyre szabott Ironman 70.3 felkészülési tervet generál.

## Mit csinál?

**Két fronton dolgozik egyszerre:**

### 🗓️ Heti újratervezés (Opus 4.7) – minden hétfő reggel
1. **Lehúzza** a friss edzésadataidat az Intervals.icu-ról (Strava fallback-kel)
2. **Elemzi** a CTL/ATL/TSB formaadataidat, heti volument, intenzitásmegoszlást
3. **Hívja a Claude Opus 4.7-et**, átadja az adatokat és a verseny dátumát
4. **Generál** egy teljes HTML edzéstervet:
   - Sportolói profil + zónák
   - Helyzetértékelés és makrociklus
   - Versenycél időbecsléssel
   - Verseny stratégia + táplálkozás
   - Az aktuális hét napra lebontott terve
   - TSS/CTL/TSB előrejelzés
   - Tudományos hivatkozások
5. **Commitolja** a repo-ba és **publikálja** GitHub Pages-en

### 🌅 Napi reggeli check (Haiku 4.5) – minden reggel 7:30 CET
1. Lehúzza az **utolsó 14 nap wellness** adatát (alvás, HRV, RHR, readiness)
2. Megnézi a **tegnapi edzést** (terv vs valóság)
3. Kinyeri a heti tervből a **mai napra** előírt edzést
4. Hívja a **Claude Haiku 4.5**-öt, ami egy strukturált JSON-t ad vissza:
   - **🟢 zöld** – tartsd a tervet
   - **🟡 sárga** – könnyítsd / módosítsd
   - **🔴 piros** – pihenj / nagyon könnyű Z1
5. A heti terv **tetején automatikusan megjelenik** egy banner a mai státusszal és a módosított edzéssel.

## Architektúra

```
Garmin / Wahoo eszköz
        ↓ (auto-sync)
   Strava
        ↓ (auto-sync)
  Intervals.icu  ←─── REST API kulcs
        ↓
  ┌─────────────────────────────────────┐
  │ GitHub Actions                       │
  │  ├─ weekly-plan.yml (hétfő 7:00)    │ ──> Opus 4.7 ──> output/index.html
  │  └─ daily-check.yml (minden reggel)  │ ──> Haiku 4.5 ─> output/daily_status.json
  └─────────────────────────────────────┘
        ↓
  GitHub Pages (index.html + JS, ami a daily_status.json-t beolvassa)
```

A **heti terv** a fő dokumentum (Opus minőség, részletes, tudományos).
A **napi banner** ennek a tetején jelenik meg dinamikusan – és csak a "mai" edzést módosítja, ha kell.

## Költségek

| Tétel | Költség |
|---|---|
| GitHub Actions | ingyenes (publikus repo) vagy 2000 perc/hó (privát) |
| Intervals.icu | ingyenes |
| Strava | ingyenes |
| Claude Opus 4.7 (heti) | ~$0.40-0.60 / futás × 4-5 hét = **~$2-3 / hó** |
| Claude Haiku 4.5 (napi) | ~$0.01-0.02 / futás × 30 = **~$0.30-0.60 / hó** |
| **Összesen** | **~$3-4 / hó** |

A **$20 minimum kredit** kényelmesen kihúz a Sept 13-i versenyig (~4-4.5 hónap), és még marad belőle.

> 💡 **Ha még olcsóbb kell:** a `coach_llm.py`-ben váltsd Sonnet 4.6-ra (`DEFAULT_MODEL = "claude-sonnet-4-6"`) – ez a heti generálást ~40%-kal csökkenti, havi $1.5-2-re.

> 💡 **Ha legjobb minőség kell:** akkor maradj Opus-on. Ez az alapbeállítás.

## Setup – lépésről lépésre

### 1. Klónozd a repo-t

```bash
git clone https://github.com/<your-username>/im703-coach.git
cd im703-coach
```

### 2. Szerezd be az API kulcsokat

#### Intervals.icu (elsődleges)
1. Regisztrálj: https://intervals.icu/
2. Csatold a Strava / Garmin Connect fiókod (Settings → Connections)
3. Várj 1-2 napot, hogy a múltbeli adatok szinkronizáljanak
4. Settings → Developer Settings → **API Key**
5. Az **athlete ID**-t a `https://intervals.icu/athlete/` URL-jén látod (pl. `i12345`)

#### Anthropic API (Claude)
1. https://console.anthropic.com → Sign up
2. Verify account, add payment method (kb. $5 minimum, kapsz $5 ingyen kreditet)
3. **API Keys → Create Key** – mentsd el biztonságos helyre, csak egyszer látod!

#### Strava (opcionális fallback) – részletes leírás: [`docs/STRAVA_SETUP.md`](docs/STRAVA_SETUP.md)

### 3. Push-old fel saját GitHub repo-ba

```bash
# Új repo a sajátod alatt
gh repo create im703-coach --private --source=. --push
```

### 4. Állítsd be a Secrets és Variables-eket

A repo-d **Settings → Secrets and variables → Actions** menüjében.

#### Repository secrets (érzékeny adatok):

| Név | Érték |
|---|---|
| `ANTHROPIC_API_KEY` | A Claude API kulcsod |
| `INTERVALS_ATHLETE_ID` | Pl. `i12345` |
| `INTERVALS_API_KEY` | Az Intervals.icu API kulcsod |
| `STRAVA_CLIENT_ID` | (opcionális, fallback) |
| `STRAVA_CLIENT_SECRET` | (opcionális) |
| `STRAVA_REFRESH_TOKEN` | (opcionális) |

#### Repository variables (nem titkos beállítások):

| Név | Érték (példa) |
|---|---|
| `ATHLETE_NAME` | `Abonyi János` |
| `RACE_DATE` | `2026-09-13` |
| `PREV_RACE_RESULTS_JSON` | `{"swim_1.9km":"43:58","bike_90km":"2:40:10","run_21.1km":"1:42:59","total":"5:18:00"}` |

### 5. Engedélyezd a GitHub Pages-t

**Settings → Pages → Source: Deploy from a branch → Branch: main, folder: `/output`**

Néhány perc múlva a terved itt lesz: `https://<your-username>.github.io/im703-coach/`

### 6. Indítsd el az első futtatást

**Actions → Generate IM 70.3 Training Plan → Run workflow**

Megírhatsz friss megjegyzéseket is (pl. "fáj a térdem", "elutaztam, csak futáshoz lesz hozzáférés"). A Claude figyelembe veszi.

A futtatás után:
- A `output/` mappában megjelenik a `plan_<név>_<dátum>_wXX.html` fájl
- Az `index.html` mindig a legfrissebb tervre mutat
- Egy `snapshot_<dátum>.json` is mentődik (audit / debug)

## Lokális futtatás (fejlesztés / tesztelés)

```bash
# 1. Virtual env
python -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt

# 2. Env változók (minimum)
export ANTHROPIC_API_KEY="sk-ant-..."
export ATHLETE_NAME="Abonyi János"
export RACE_DATE="2026-09-13"
export INTERVALS_ATHLETE_ID="iXXXXX"
export INTERVALS_API_KEY="..."

# 3. Futtatás
python scripts/generate_plan.py

# 4. Eredmény
open output/index.html
```

## Hogyan változtasd meg a viselkedést?

- **Edzői "agy"**: `prompts/system_prompt.md` – itt szabhatod testre, hogy milyen szakmai elveket kövessen, milyen szerkezetben generáljon, milyen hivatkozásokat preferáljon.
- **Adatok lehúzása**: `scripts/intervals_client.py` és `scripts/strava_client.py`
- **Mit látunk a snapshotban**: `scripts/analyzer.py` – itt szűrjük meg, mit kapjon meg a Claude
- **Modellválasztás**: `scripts/coach_llm.py` – `DEFAULT_MODEL` (pl. cseréld `claude-opus-4-7`-re ha még alaposabb tervet szeretnél)
- **Cron időpont**: `.github/workflows/weekly-plan.yml` – a `cron: "0 5 * * 1"` a hétfő reggel 5 UTC

## Hibakeresés

| Hiba | Megoldás |
|---|---|
| `Hiányzó env változó: ANTHROPIC_API_KEY` | Secret nincs beállítva |
| `Intervals.icu hibára futott: 401` | API kulcs hibás vagy lejárt |
| `Nincs lehúzott edzésadat` | Sem Intervals sem Strava nem ad vissza adatot |
| `A Claude válasza nem <!DOCTYPE html>-lel kezdődik` | Néha a modell magyarázatot ad – ellenőrizd a system promptot, vagy állítsd `DEFAULT_MODEL`-t Opus-ra |
| Workflow timeout | Növeld a `timeout-minutes`-t a yml-ben |

## Disclaimers

⚠️ **Ez egy automatizált rendszer, NEM helyettesíti a humán edzőt.** A Claude tudományos elveket követ, de:
- Nem tud **fizikailag megfigyelni**, nem lát technikai hibát úszásban / kerékpáron / futásban
- Nem érzi a **friss fájdalmat / sérülést** – ezért fontos a `notes` mező
- A célverseny előtti utolsó 4-6 hétben **érdemes humán szakember véleményét is kikérni**

A generált tervet **mindig józan ésszel és a tested visszajelzéseivel** kombináld. Ha bármilyen szúró fájdalmat, sérülést, túlfáradtságot érzel, **csökkents** vagy **pihenj**, és frissítsd a `notes`-t a következő futtatásnál.

## Licenc

MIT. A felelősség teljesen a tiéd – a kód úgy van adva, ahogy van.
