#!/usr/bin/env python3
"""
Keyword-Research: Google Ads Keyword Planner (exakte Suchvolumina) x GSC-Rankings.
Schreibt data/keywords.json mit kategorisierten, deduplizierten Chancen für das Dashboard.

Env-Variablen:
  GSC_CLIENT_ID, GSC_CLIENT_SECRET
  ADS_REFRESH_TOKEN, ADS_DEVELOPER_TOKEN, ADS_CUSTOMER_ID
  GSC_REFRESH_TOKEN, GSC_SITE_URL
"""
import os, json, urllib.request, urllib.parse, re
from datetime import date, timedelta

ROOT = os.path.dirname(os.path.abspath(__file__))
CID = os.environ["GSC_CLIENT_ID"]
CSEC = os.environ["GSC_CLIENT_SECRET"]
ADS_REFRESH = os.environ["ADS_REFRESH_TOKEN"]
DEV_TOKEN = os.environ["ADS_DEVELOPER_TOKEN"]
CUSTOMER = os.environ["ADS_CUSTOMER_ID"]
GSC_REFRESH = os.environ.get("GSC_REFRESH_TOKEN", ADS_REFRESH)
SITE = os.environ.get("GSC_SITE_URL", "https://trachtenflirt.de/")

SEEDS = [
    "trachtenmode damen", "trachtenmode herren", "trachten t shirt herren",
    "trachten t shirt damen", "trachtenshirts", "vegane lederhose damen",
    "vegane lederhose herren", "trachtenkleider modern", "trachtenrock damen",
    "trachtenjeans damen", "oktoberfest outfit damen", "oktoberfest outfit herren",
    "apres ski outfit", "trachtenweste damen", "dirndl alternative",
    "oktoberfest ohne dirndl", "trachtenhemd herren kariert", "landhausmode damen",
    "trachten große größen", "trachtenbluse",
]
COMP_DE = {"LOW": "niedrig", "MEDIUM": "mittel", "HIGH": "hoch", "UNSPECIFIED": "?"}
STOP = {"für", "fur", "die", "der", "das", "und"}


def access_token(refresh):
    body = urllib.parse.urlencode({"client_id": CID, "client_secret": CSEC,
        "refresh_token": refresh, "grant_type": "refresh_token"}).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body,
        headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    return json.loads(urllib.request.urlopen(req, timeout=60).read())["access_token"]


def keyword_ideas(token, seeds):
    url = f"https://googleads.googleapis.com/v21/customers/{CUSTOMER}:generateKeywordIdeas"
    body = json.dumps({"language": "languageConstants/1001",
        "geoTargetConstants": ["geoTargetConstants/2276"],
        "keywordPlanNetwork": "GOOGLE_SEARCH", "includeAdultKeywords": False,
        "keywordSeed": {"keywords": seeds}}).encode()
    req = urllib.request.Request(url, data=body, method="POST", headers={
        "Authorization": "Bearer " + token, "developer-token": DEV_TOKEN,
        "Content-Type": "application/json"})
    data = json.loads(urllib.request.urlopen(req, timeout=120).read())
    out = []
    for item in data.get("results", []):
        m = item.get("keywordIdeaMetrics") or {}
        vols = m.get("monthlySearchVolumes", [])
        avg = int(m["avgMonthlySearches"]) if m.get("avgMonthlySearches") else (
            round(sum(int(v["monthlySearches"]) for v in vols) / len(vols)) if vols else 0)
        peak = max(((int(v["monthlySearches"]), f"{v['month'][:3].title()} {v['year']}")
                    for v in vols), default=(0, "")) if vols else (0, "")
        out.append({
            "keyword": item.get("text", ""), "volume": avg,
            "competition": m.get("competition", "UNSPECIFIED"),
            "peak_searches": peak[0], "peak_month": peak[1],
            "cpc_high": round(int(m.get("highTopOfPageBidMicros", 0)) / 1_000_000, 2),
        })
    return out


def gsc_positions(token):
    api = "https://searchconsole.googleapis.com/webmasters/v3/sites/" + urllib.parse.quote(SITE, safe="") + "/searchAnalytics/query"
    today = date.today()
    body = json.dumps({"startDate": (today - timedelta(days=30)).strftime("%Y-%m-%d"),
        "endDate": (today - timedelta(days=1)).strftime("%Y-%m-%d"),
        "dimensions": ["query"], "rowLimit": 1000}).encode()
    req = urllib.request.Request(api, data=body, method="POST", headers={
        "Authorization": "Bearer " + token, "Content-Type": "application/json"})
    rows = json.loads(urllib.request.urlopen(req, timeout=60).read()).get("rows", [])
    return {r["keys"][0].lower(): {"position": round(r["position"], 1), "clicks": round(r["clicks"])}
            for r in rows}


def norm_key(kw):
    """Wort-Reihenfolge & Stopwörter ignorieren -> Duplikate wie
    'lederhosen herren' / 'herren lederhosen' / 'lederhosen für herren' kollabieren."""
    words = [w for w in re.sub(r"[^a-zäöüß ]", "", kw.lower()).split() if w not in STOP]
    return tuple(sorted(words))


def dedupe(ideas):
    groups = {}
    for k in ideas:
        key = norm_key(k["keyword"])
        if not key:
            continue
        cur = groups.get(key)
        # behalte Variante mit bekannter Position, sonst die kürzeste/natürlichste
        better = (cur is None
                  or (k.get("our_position") is not None and cur.get("our_position") is None)
                  or (len(k["keyword"]) < len(cur["keyword"]) and
                      (k.get("our_position") is not None) == (cur.get("our_position") is not None)))
        if better:
            groups[key] = k
    return list(groups.values())


def main():
    print("→ Keyword-Ideen aus Google Ads…")
    ideas = keyword_ideas(access_token(ADS_REFRESH), SEEDS)
    print(f"  {len(ideas)} Ideen.")
    print("→ GSC-Rankings…")
    ranks = gsc_positions(access_token(GSC_REFRESH))
    print(f"  {len(ranks)} gerankte Keywords.")

    for k in ideas:
        r = ranks.get(k["keyword"].lower())
        k["our_position"] = r["position"] if r else None
        k["our_clicks"] = r["clicks"] if r else 0

    ideas = dedupe(ideas)

    def fields(k):
        return {"keyword": k["keyword"], "volume": k["volume"],
                "competition": COMP_DE.get(k["competition"], "?"),
                "peak": k["peak_searches"], "peakMonth": k["peak_month"],
                "cpc": k["cpc_high"], "position": k["our_position"]}

    near = sorted([k for k in ideas if k["our_position"] and 11 <= k["our_position"] <= 30 and k["volume"] >= 150],
                  key=lambda x: x["volume"], reverse=True)
    improve = sorted([k for k in ideas if k["our_position"] and 4 <= k["our_position"] <= 10 and k["volume"] >= 200],
                     key=lambda x: x["volume"], reverse=True)
    gaps = sorted([k for k in ideas if (k["our_position"] is None or k["our_position"] > 30) and k["volume"] >= 500],
                  key=lambda x: x["volume"], reverse=True)
    winning = sorted([k for k in ideas if k["our_position"] and k["our_position"] <= 3 and k["volume"] >= 200],
                     key=lambda x: x["volume"], reverse=True)
    # Saison-Peaks: Top-Volumen-Keywords mit Peak-Monat (Timing für Content/Ads)
    season = sorted([k for k in ideas if k["volume"] >= 1000 and k["peak_searches"] >= 3 * max(k["volume"], 1)],
                    key=lambda x: x["peak_searches"], reverse=True)

    payload = {
        "generated": date.today().strftime("%d.%m.%Y"),
        "stats": {"ideas": len(ideas), "ranked": len(ranks)},
        "nearWins": [fields(k) for k in near[:12]],
        "improve": [fields(k) for k in improve[:10]],
        "gaps": [fields(k) for k in gaps[:12]],
        "winning": [fields(k) for k in winning[:10]],
        "season": [fields(k) for k in season[:8]],
    }
    json.dump(payload, open(os.path.join(ROOT, "data", "keywords.json"), "w"), indent=2, ensure_ascii=False)
    print(f"\nOK – keywords.json: {len(near)} Near-Wins, {len(improve)} Verbessern, "
          f"{len(gaps)} Lücken, {len(winning)} Gewonnen, {len(season)} Saison-Peaks.")


if __name__ == "__main__":
    main()
