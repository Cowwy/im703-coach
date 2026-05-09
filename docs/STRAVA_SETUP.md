# Strava OAuth setup (fallback adatforrás)

A Strava API egy **OAuth 2.0** flow-t használ. Egyszer kell beszerezni egy `refresh_token`-t, ami aztán tartósan érvényes.

## 1. Hozz létre Strava API alkalmazást

1. Menj ide: https://www.strava.com/settings/api
2. Kattints **"Create & Manage Your App"**
3. Töltsd ki:
   - **Application Name**: `im703-coach` (vagy bármi)
   - **Category**: Training
   - **Website**: bármi, pl. `http://localhost`
   - **Authorization Callback Domain**: `localhost`
4. Mentsd el. Kapsz egy:
   - **Client ID** (egész szám, pl. `12345`)
   - **Client Secret** (hosszú string)

## 2. Authorize URL hívása

Cseréld ki a `<CLIENT_ID>`-t és nyisd meg a böngészőben:

```
https://www.strava.com/oauth/authorize?client_id=<CLIENT_ID>&response_type=code&redirect_uri=http://localhost&approval_prompt=force&scope=read,activity:read_all,profile:read_all
```

Hagyd jóvá a hozzáférést. A böngésző átirányít:

```
http://localhost/?state=&code=<AUTH_CODE>&scope=read,activity:read_all,profile:read_all
```

A `<AUTH_CODE>` az URL-ben van. Másold ki.

> Az URL bizonyára "Site can't be reached" hibával jön be – ez normális, mert a `localhost`-on nem fut semmi. A `code` paraméter ettől még a címsorban van.

## 3. Cseréld le auth code-ot refresh_token-re

Egyszeri curl hívás (vagy Postman):

```bash
curl -X POST https://www.strava.com/api/v3/oauth/token \
  -d client_id=<CLIENT_ID> \
  -d client_secret=<CLIENT_SECRET> \
  -d code=<AUTH_CODE> \
  -d grant_type=authorization_code
```

A válaszban:

```json
{
  "token_type": "Bearer",
  "access_token": "...",
  "refresh_token": "...",   ← EZ KELL!
  "expires_at": 1759320000,
  "expires_in": 21600,
  "athlete": { ... }
}
```

## 4. Mentsd el a 3 értéket GitHub Secrets-ként

| Secret név | Érték |
|---|---|
| `STRAVA_CLIENT_ID` | A Client ID |
| `STRAVA_CLIENT_SECRET` | A Client Secret |
| `STRAVA_REFRESH_TOKEN` | A refresh_token |

A `refresh_token` **tartósan érvényes** (hacsak nem revoke-olod). A kód minden futtatáskor frissít access_tokent belőle.

## Gyakori probléma

- **"You do not have permission to view this activity"** → a scope `activity:read_all`-t kéne, nézd meg az Authorize URL-t
- **Rate limit** → 100 req / 15 min, 1000 / nap. Heti egyszeri futtatáshoz bőven elég.
