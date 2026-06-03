# Trachtenflirt SEO Dashboard

Automatisch generiertes SEO-Dashboard für [trachtenflirt.de](https://trachtenflirt.de) auf Basis von Google Search Console.

## Wie es funktioniert

- `keyword_research.py` zieht exakte Suchvolumina aus dem **Google Ads Keyword Planner**, kreuzt sie mit den GSC-Rankings und schreibt kategorisierte Chancen nach `data/keywords.json` (Near-Wins, Lücken, Gewonnen, Saison-Peaks).
- `generate.py` zieht GSC-Daten (Klicks, Impressionen, CTR, Position), baut Wochen-Trend, Quick-Wins, Gewinner/Verlierer, neue Keywords, Top-Seiten und die Keyword-Chancen-Panels und rendert `index.html`.
- Eine **GitHub Action** (`.github/workflows/update-dashboard.yml`) läuft jeden Montag, regeneriert das Dashboard, committet es und veröffentlicht es über **GitHub Pages**.
- `data/history.json` akkumuliert die Wochen-Snapshots → der Trend wird über Zeit immer aussagekräftiger.

## Secrets (in GitHub → Settings → Secrets and variables → Actions)

| Secret | Beschreibung |
|---|---|
| `GSC_CLIENT_ID` | Google OAuth Client ID |
| `GSC_CLIENT_SECRET` | Google OAuth Client Secret |
| `GSC_REFRESH_TOKEN` | OAuth Refresh Token (Scope: webmasters.readonly) |
| `GSC_SITE_URL` | z.B. `https://trachtenflirt.de/` |
| `ADS_REFRESH_TOKEN` | OAuth Refresh Token mit `adwords`-Scope |
| `ADS_DEVELOPER_TOKEN` | Google Ads API Developer Token |
| `ADS_CUSTOMER_ID` | Google Ads Customer ID (10-stellig, ohne Bindestriche) |

## Lokal ausführen

```bash
GSC_CLIENT_ID=... GSC_CLIENT_SECRET=... GSC_REFRESH_TOKEN=... GSC_SITE_URL=https://trachtenflirt.de/ python3 generate.py
```

## Manuell auslösen

GitHub → Actions → „Update SEO Dashboard" → „Run workflow".
