# Trachtenflirt SEO Dashboard

Automatisch generiertes SEO-Dashboard für [trachtenflirt.de](https://trachtenflirt.de) auf Basis von Google Search Console.

## Wie es funktioniert

- `generate.py` zieht GSC-Daten (Klicks, Impressionen, CTR, Position), baut einen Wochen-Trend, Quick-Wins, Gewinner/Verlierer, neue Keywords und Top-Seiten und rendert `index.html`.
- Eine **GitHub Action** (`.github/workflows/update-dashboard.yml`) läuft jeden Montag, regeneriert das Dashboard, committet es und veröffentlicht es über **GitHub Pages**.
- `data/history.json` akkumuliert die Wochen-Snapshots → der Trend wird über Zeit immer aussagekräftiger.

## Secrets (in GitHub → Settings → Secrets and variables → Actions)

| Secret | Beschreibung |
|---|---|
| `GSC_CLIENT_ID` | Google OAuth Client ID |
| `GSC_CLIENT_SECRET` | Google OAuth Client Secret |
| `GSC_REFRESH_TOKEN` | OAuth Refresh Token (Scope: webmasters.readonly) |
| `GSC_SITE_URL` | z.B. `https://trachtenflirt.de/` |

## Lokal ausführen

```bash
GSC_CLIENT_ID=... GSC_CLIENT_SECRET=... GSC_REFRESH_TOKEN=... GSC_SITE_URL=https://trachtenflirt.de/ python3 generate.py
```

## Manuell auslösen

GitHub → Actions → „Update SEO Dashboard" → „Run workflow".
