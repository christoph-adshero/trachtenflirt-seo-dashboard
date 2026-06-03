#!/usr/bin/env python3
"""
Trachtenflirt SEO Dashboard Generator
Zieht Google Search Console Daten, baut Wochen-Trend (12 Wochen Backfill aus GSC-Archiv),
Quick-Wins, Gewinner/Verlierer, Top-Seiten und rendert ein self-contained index.html.

Secrets via Umgebungsvariablen:
  GSC_CLIENT_ID, GSC_CLIENT_SECRET, GSC_REFRESH_TOKEN, GSC_SITE_URL
Optional (Shopify-Panel, vom Wochen-Agent geschrieben):
  data/shopify.json
"""
import os, json, urllib.request, urllib.parse
from datetime import date, timedelta
from collections import defaultdict

ROOT = os.path.dirname(os.path.abspath(__file__))
SITE = os.environ.get("GSC_SITE_URL", "https://trachtenflirt.de/")
CLIENT_ID = os.environ["GSC_CLIENT_ID"]
CLIENT_SECRET = os.environ["GSC_CLIENT_SECRET"]
REFRESH_TOKEN = os.environ["GSC_REFRESH_TOKEN"]

API = "https://searchconsole.googleapis.com/webmasters/v3/sites/" + urllib.parse.quote(SITE, safe="") + "/searchAnalytics/query"


def post(url, data, headers):
    req = urllib.request.Request(url, data=json.dumps(data).encode() if isinstance(data, dict) else data, headers=headers, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())


def get_token():
    body = urllib.parse.urlencode({
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN, "grant_type": "refresh_token",
    }).encode()
    req = urllib.request.Request("https://oauth2.googleapis.com/token", data=body,
                                 headers={"Content-Type": "application/x-www-form-urlencoded"}, method="POST")
    with urllib.request.urlopen(req, timeout=60) as r:
        return json.loads(r.read().decode())["access_token"]


def gsc_query(token, body):
    return post(API, body, {"Authorization": "Bearer " + token, "Content-Type": "application/json"}).get("rows", [])


def iso_week_key(d):
    y, w, _ = d.isocalendar()
    return f"{y}-W{w:02d}"


def main():
    token = get_token()
    today = date.today()

    # --- 1) 90-Tage Datenreihe -> Wochen-Buckets fuer Trend ---
    series = gsc_query(token, {
        "startDate": (today - timedelta(days=91)).strftime("%Y-%m-%d"),
        "endDate": (today - timedelta(days=1)).strftime("%Y-%m-%d"),
        "dimensions": ["date"], "rowLimit": 100,
    })
    weeks = defaultdict(lambda: {"clicks": 0, "impressions": 0, "pos_w": 0.0})
    for row in series:
        d = date.fromisoformat(row["keys"][0])
        wk = iso_week_key(d)
        weeks[wk]["clicks"] += row["clicks"]
        weeks[wk]["impressions"] += row["impressions"]
        weeks[wk]["pos_w"] += row["position"] * row["impressions"]
    trend = []
    for wk in sorted(weeks.keys()):
        b = weeks[wk]
        imp = b["impressions"]
        trend.append({
            "week": wk,
            "clicks": round(b["clicks"]),
            "impressions": round(imp),
            "ctr": round(b["clicks"] / imp * 100, 2) if imp else 0,
            "position": round(b["pos_w"] / imp, 1) if imp else 0,
        })
    trend = trend[-12:]  # letzte 12 vollstaendige(re) Wochen

    # --- 2) Aktuelle Woche vs Vorwoche (Keywords) ---
    cur_start = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    cur_end = (today - timedelta(days=1)).strftime("%Y-%m-%d")
    prev_start = (today - timedelta(days=14)).strftime("%Y-%m-%d")
    prev_end = (today - timedelta(days=8)).strftime("%Y-%m-%d")

    cur_rows = gsc_query(token, {"startDate": cur_start, "endDate": cur_end, "dimensions": ["query"], "rowLimit": 250})
    prev_rows = gsc_query(token, {"startDate": prev_start, "endDate": prev_end, "dimensions": ["query"], "rowLimit": 250})
    page_rows = gsc_query(token, {"startDate": cur_start, "endDate": cur_end, "dimensions": ["page"], "rowLimit": 25})

    cur = {r["keys"][0]: r for r in cur_rows}
    prev = {r["keys"][0]: r for r in prev_rows}

    # KPI-Karten: ECHTE Gesamt-Totals (ohne Dimension) – nicht nur Top-250-Keywords,
    # sonst widerspricht die Headline dem Trend-Chart.
    def totals(start, end):
        rows = gsc_query(token, {"startDate": start, "endDate": end, "dimensions": [], "rowLimit": 1})
        if not rows:
            return {"clicks": 0, "impressions": 0, "ctr": 0, "position": 0}
        r = rows[0]
        return {"clicks": round(r["clicks"]), "impressions": round(r["impressions"]),
                "ctr": round(r["ctr"] * 100, 2), "position": round(r["position"], 1)}

    cur_kpi = totals(cur_start, cur_end)
    prev_kpi = totals(prev_start, prev_end)

    # Quick Wins: Pos 4-15, Impressionen > 80, CTR < 5%
    quick_wins = []
    for kw, r in cur.items():
        if 4 <= r["position"] <= 15 and r["impressions"] > 80 and r["ctr"] < 0.05:
            quick_wins.append({"kw": kw, "position": round(r["position"], 1),
                               "impressions": round(r["impressions"]),
                               "ctr": round(r["ctr"] * 100, 1), "clicks": round(r["clicks"])})
    quick_wins.sort(key=lambda x: x["impressions"], reverse=True)
    quick_wins = quick_wins[:15]

    # Gewinner / Verlierer (Pos-Aenderung >= 1.5, Impressionen >= 40)
    gainers, losers = [], []
    for kw, r in cur.items():
        if kw in prev and r["impressions"] >= 40:
            delta = prev[kw]["position"] - r["position"]
            entry = {"kw": kw, "from": round(prev[kw]["position"], 1), "to": round(r["position"], 1),
                     "delta": round(abs(delta), 1), "clicks": round(r["clicks"])}
            if delta >= 1.5:
                gainers.append(entry)
            elif delta <= -1.5:
                losers.append(entry)
    gainers.sort(key=lambda x: x["delta"], reverse=True)
    losers.sort(key=lambda x: x["delta"], reverse=True)

    # Neue Keywords
    new_kw = [{"kw": kw, "clicks": round(r["clicks"]), "impressions": round(r["impressions"]),
               "position": round(r["position"], 1)}
              for kw, r in cur.items() if kw not in prev and r["impressions"] > 15]
    new_kw.sort(key=lambda x: x["impressions"], reverse=True)
    new_kw = new_kw[:10]

    top_kw = sorted(cur.values(), key=lambda x: x["clicks"], reverse=True)[:15]
    top_keywords = [{"kw": r["keys"][0], "clicks": round(r["clicks"]),
                     "impressions": round(r["impressions"]), "ctr": round(r["ctr"] * 100, 1),
                     "position": round(r["position"], 1)} for r in top_kw]

    top_pages = [{"url": r["keys"][0].replace("https://trachtenflirt.de", ""),
                  "clicks": round(r["clicks"]), "ctr": round(r["ctr"] * 100, 1),
                  "position": round(r["position"], 1)} for r in page_rows[:12]]

    # --- 3) History persistieren ---
    hist_path = os.path.join(ROOT, "data", "history.json")
    history = {}
    if os.path.exists(hist_path):
        history = json.load(open(hist_path))
    for t in trend:
        history[t["week"]] = {k: t[k] for k in ("clicks", "impressions", "ctr", "position")}
    os.makedirs(os.path.dirname(hist_path), exist_ok=True)
    json.dump(history, open(hist_path, "w"), indent=2, ensure_ascii=False)
    # vollstaendige History fuer Trend nutzen (ueber 12 Wochen hinaus)
    full_trend = [dict(week=w, **history[w]) for w in sorted(history.keys())][-26:]

    # --- 4) Shopify-Panel (optional, vom Agent geschrieben) ---
    shopify = None
    sp = os.path.join(ROOT, "data", "shopify.json")
    if os.path.exists(sp):
        shopify = json.load(open(sp))

    # --- 5) Keyword-Chancen (optional, von keyword_research.py geschrieben) ---
    keywords = None
    kp = os.path.join(ROOT, "data", "keywords.json")
    if os.path.exists(kp):
        keywords = json.load(open(kp))

    payload = {
        "generated": today.strftime("%d.%m.%Y"),
        "period": f"{cur_start} – {cur_end}",
        "kpi": {"current": cur_kpi, "previous": prev_kpi},
        "trend": full_trend,
        "quickWins": quick_wins,
        "gainers": gainers[:10], "losers": losers[:10],
        "newKeywords": new_kw, "topKeywords": top_keywords, "topPages": top_pages,
        "shopify": shopify, "keywords": keywords,
    }

    html = render(payload)
    open(os.path.join(ROOT, "index.html"), "w").write(html)
    print(f"OK – index.html erstellt. {len(full_trend)} Wochen Trend, {len(quick_wins)} Quick-Wins, "
          f"{len(gainers)} Gewinner, {len(losers)} Verlierer.")


def render(p):
    data_json = json.dumps(p, ensure_ascii=False)
    return TEMPLATE.replace("/*__DATA__*/", data_json)


TEMPLATE = r"""<!doctype html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trachtenflirt · SEO Dashboard</title>
<script src="https://cdn.jsdelivr.net/npm/chart.js@4.4.1/dist/chart.umd.min.js"></script>
<style>
  :root{--red:#c00000;--ink:#1a1a1a;--mut:#6b7280;--bg:#f6f7f9;--card:#fff;--ok:#1b9500;--bad:#c72e2f;--line:#e5e7eb}
  *{box-sizing:border-box}
  body{margin:0;font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,sans-serif;background:var(--bg);color:var(--ink);-webkit-font-smoothing:antialiased}
  .wrap{max-width:1180px;margin:0 auto;padding:24px 20px 60px}
  header{display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:24px}
  h1{font-size:22px;margin:0;font-weight:800;letter-spacing:-.02em}
  h1 .dot{color:var(--red)}
  .meta{color:var(--mut);font-size:13px}
  .grid{display:grid;gap:16px}
  .kpis{grid-template-columns:repeat(4,1fr)}
  @media(max-width:760px){.kpis{grid-template-columns:repeat(2,1fr)}}
  .card{background:var(--card);border:1px solid var(--line);border-radius:14px;padding:18px}
  .card h2{font-size:13px;text-transform:uppercase;letter-spacing:.04em;color:var(--mut);margin:0 0 12px}
  .kpi .label{font-size:12px;color:var(--mut);text-transform:uppercase;letter-spacing:.03em}
  .kpi .val{font-size:30px;font-weight:800;letter-spacing:-.02em;margin:6px 0 2px}
  .delta{font-size:13px;font-weight:700}
  .up{color:var(--ok)} .down{color:var(--bad)} .flat{color:var(--mut)}
  .section{margin-top:22px}
  table{width:100%;border-collapse:collapse;font-size:13.5px}
  th,td{text-align:left;padding:9px 10px;border-bottom:1px solid var(--line)}
  th{font-size:11px;text-transform:uppercase;letter-spacing:.03em;color:var(--mut);font-weight:700}
  td.num,th.num{text-align:right;font-variant-numeric:tabular-nums}
  tr:last-child td{border-bottom:none}
  .kw{font-weight:600}
  .pill{display:inline-block;padding:2px 8px;border-radius:999px;font-size:11px;font-weight:700}
  .pill.warn{background:#fff3cd;color:#8a6d00}
  .pill.hot{background:#fde0e0;color:var(--bad)}
  .two{grid-template-columns:1fr 1fr}
  @media(max-width:760px){.two{grid-template-columns:1fr}}
  .muted{color:var(--mut)}
  .arrow-up::before{content:"▲ ";color:var(--ok)}
  .arrow-down::before{content:"▼ ";color:var(--bad)}
  .foot{margin-top:30px;color:var(--mut);font-size:12px;text-align:center}
  .chip{display:inline-block;background:#eef2ff;color:#3730a3;border-radius:8px;padding:3px 9px;font-size:12px;font-weight:600;margin:2px}
  canvas{max-height:280px}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>Trachtenflirt <span class="dot">·</span> SEO Dashboard</h1>
    <div class="meta" id="meta"></div>
  </header>

  <div class="grid kpis" id="kpis"></div>

  <div class="section card">
    <h2>Klicks &amp; Impressionen – Wochen-Trend</h2>
    <canvas id="trendChart"></canvas>
  </div>

  <div class="section card">
    <h2>Ø Position – Wochen-Trend <span class="muted">(niedriger = besser)</span></h2>
    <canvas id="posChart"></canvas>
  </div>

  <div class="section card">
    <h2>🎯 Quick Wins <span class="muted">– kurz vor Top 3, CTR-Optimierung lohnt</span></h2>
    <table id="quickWins"></table>
  </div>

  <div class="section grid two">
    <div class="card"><h2>📈 Gewinner der Woche</h2><table id="gainers"></table></div>
    <div class="card"><h2>📉 Verlierer der Woche</h2><table id="losers"></table></div>
  </div>

  <div class="section grid two">
    <div class="card"><h2>💡 Neue Keywords</h2><table id="newKeywords"></table></div>
    <div class="card"><h2>🔗 Top Seiten</h2><table id="topPages"></table></div>
  </div>

  <div class="section card">
    <h2>🏆 Top Keywords</h2><table id="topKeywords"></table>
  </div>

  <div id="kwBlock" style="display:none">
    <div class="section" style="display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:6px">
      <h2 style="font-size:16px;margin:0;font-weight:800">🔑 Keyword-Chancen <span class="muted" style="font-weight:400">– Suchvolumen (Google Ads) × deine Rankings</span></h2>
      <span class="muted" id="kwStats" style="font-size:12px"></span>
    </div>

    <div class="section card" style="border-color:#1b9500;border-width:1.5px">
      <h2>🎯 Near-Wins <span class="muted">– du rankst Seite 2-3, ein Schub reicht für Seite 1</span></h2>
      <table id="kwNear"></table>
    </div>

    <div class="section grid two">
      <div class="card"><h2>🚀 Strategische Lücken <span class="muted">– hohes Volumen, (noch) nicht gerankt</span></h2><table id="kwGaps"></table></div>
      <div class="card"><h2>🏆 Hier dominierst du <span class="muted">– Top 3, halten &amp; ausbauen</span></h2><table id="kwWinning"></table></div>
    </div>

    <div class="section card">
      <h2>📅 Saison-Timing <span class="muted">– Peak-Monat: rechtzeitig Content &amp; Ads hochfahren</span></h2>
      <table id="kwSeason"></table>
    </div>
  </div>

  <div class="section card" id="shopifyCard" style="display:none">
    <h2>🛠 Shopify SEO-Status</h2><div id="shopify"></div>
  </div>

  <div class="foot">Automatisch generiert · Datenquelle: Google Search Console · Trachtenflirt / Hangowear</div>
</div>

<script>
const D = /*__DATA__*/;

function deltaHTML(cur, prev, invert=false, suffix=""){
  const d = cur - prev;
  const pct = prev ? (d/prev*100) : 0;
  let cls = "flat", arrow = "→";
  let good = invert ? d < 0 : d > 0;
  let bad = invert ? d > 0 : d < 0;
  if(Math.abs(d) < 0.0001){cls="flat";}
  else if(good){cls="up";arrow="▲";}
  else if(bad){cls="down";arrow="▼";}
  const val = (Math.abs(d) >= 10 ? Math.round(d) : d.toFixed(1));
  return `<span class="delta ${cls}">${arrow} ${val>0?'+':''}${val}${suffix} <span class="muted">(${pct>0?'+':''}${pct.toFixed(0)}%)</span></span>`;
}

function kpiCard(label, cur, prev, invert=false, suffix=""){
  return `<div class="card kpi"><div class="label">${label}</div>
    <div class="val">${cur}${suffix}</div>${deltaHTML(cur, prev, invert)}</div>`;
}

const k = D.kpi;
document.getElementById('meta').innerHTML = `Zeitraum ${D.period} · Stand ${D.generated}`;
document.getElementById('kpis').innerHTML =
  kpiCard("Klicks", k.current.clicks, k.previous.clicks) +
  kpiCard("Impressionen", k.current.impressions, k.previous.impressions) +
  kpiCard("Ø CTR", k.current.ctr, k.previous.ctr, false, "%") +
  kpiCard("Ø Position", k.current.position, k.previous.position, true);

function table(el, cols, rows, rowFn){
  const head = "<tr>" + cols.map(c=>`<th class="${c.num?'num':''}">${c.t}</th>`).join("") + "</tr>";
  const body = rows.length ? rows.map(rowFn).join("") :
    `<tr><td colspan="${cols.length}" class="muted">Keine Daten in diesem Zeitraum.</td></tr>`;
  document.getElementById(el).innerHTML = head + body;
}

table("quickWins",
  [{t:"Keyword"},{t:"Position",num:1},{t:"Impressionen",num:1},{t:"CTR",num:1},{t:"Potenzial"}],
  D.quickWins,
  r=>`<tr><td class="kw">${r.kw}</td><td class="num">${r.position}</td>
   <td class="num">${r.impressions}</td><td class="num">${r.ctr}%</td>
   <td><span class="pill ${r.ctr<2?'hot':'warn'}">${r.ctr<2?'hoch':'mittel'}</span></td></tr>`);

table("gainers",
  [{t:"Keyword"},{t:"Vorher→Jetzt"},{t:"Δ",num:1},{t:"Klicks",num:1}],
  D.gainers,
  r=>`<tr><td class="kw">${r.kw}</td><td>${r.from} → ${r.to}</td>
   <td class="num arrow-up">${r.delta}</td><td class="num">${r.clicks}</td></tr>`);

table("losers",
  [{t:"Keyword"},{t:"Vorher→Jetzt"},{t:"Δ",num:1},{t:"Klicks",num:1}],
  D.losers,
  r=>`<tr><td class="kw">${r.kw}</td><td>${r.from} → ${r.to}</td>
   <td class="num arrow-down">${r.delta}</td><td class="num">${r.clicks}</td></tr>`);

table("newKeywords",
  [{t:"Keyword"},{t:"Impr.",num:1},{t:"Pos.",num:1}],
  D.newKeywords,
  r=>`<tr><td class="kw">${r.kw}</td><td class="num">${r.impressions}</td><td class="num">${r.position}</td></tr>`);

table("topPages",
  [{t:"Seite"},{t:"Klicks",num:1},{t:"CTR",num:1},{t:"Pos.",num:1}],
  D.topPages,
  r=>`<tr><td class="kw">${r.url||'/'}</td><td class="num">${r.clicks}</td><td class="num">${r.ctr}%</td><td class="num">${r.position}</td></tr>`);

table("topKeywords",
  [{t:"Keyword"},{t:"Klicks",num:1},{t:"Impr.",num:1},{t:"CTR",num:1},{t:"Pos.",num:1}],
  D.topKeywords,
  r=>`<tr><td class="kw">${r.kw}</td><td class="num">${r.clicks}</td><td class="num">${r.impressions}</td><td class="num">${r.ctr}%</td><td class="num">${r.position}</td></tr>`);

const labels = D.trend.map(t=>t.week.replace(/^\d+-/,''));
new Chart(document.getElementById('trendChart'), {
  type:'line',
  data:{labels, datasets:[
    {label:'Klicks', data:D.trend.map(t=>t.clicks), borderColor:'#c00000', backgroundColor:'rgba(192,0,0,.08)', fill:true, tension:.3, yAxisID:'y'},
    {label:'Impressionen', data:D.trend.map(t=>t.impressions), borderColor:'#2563eb', backgroundColor:'rgba(37,99,235,.06)', fill:true, tension:.3, yAxisID:'y1'},
  ]},
  options:{responsive:true, interaction:{mode:'index',intersect:false},
    scales:{y:{position:'left',title:{display:true,text:'Klicks'}},
            y1:{position:'right',title:{display:true,text:'Impressionen'},grid:{drawOnChartArea:false}}}}
});

new Chart(document.getElementById('posChart'), {
  type:'line',
  data:{labels, datasets:[
    {label:'Ø Position', data:D.trend.map(t=>t.position), borderColor:'#1b9500', backgroundColor:'rgba(27,149,0,.08)', fill:true, tension:.3},
  ]},
  options:{responsive:true, scales:{y:{reverse:true, title:{display:true,text:'Position'}}}}
});

function vol(n){ return n>=1000 ? (n/1000).toFixed(n>=10000?0:1)+'k' : n; }
function compPill(c){ const cls = c==='hoch'?'hot':(c==='mittel'?'warn':''); return `<span class="pill ${cls}">${c}</span>`; }

if(D.keywords){
  const K = D.keywords;
  document.getElementById('kwBlock').style.display='block';
  document.getElementById('kwStats').textContent =
    `${K.stats.ideas} Keyword-Ideen analysiert · Stand ${K.generated}`;

  table("kwNear",
    [{t:"Keyword"},{t:"Suchvol./Mt",num:1},{t:"Wettbewerb"},{t:"deine Pos.",num:1}],
    K.nearWins,
    r=>`<tr><td class="kw">${r.keyword}</td><td class="num">${vol(r.volume)}</td>
     <td>${compPill(r.competition)}</td><td class="num">${r.position}</td></tr>`);

  table("kwGaps",
    [{t:"Keyword"},{t:"Vol./Mt",num:1},{t:"Wettb."}],
    K.gaps,
    r=>`<tr><td class="kw">${r.keyword}</td><td class="num">${vol(r.volume)}</td><td>${compPill(r.competition)}</td></tr>`);

  table("kwWinning",
    [{t:"Keyword"},{t:"Vol./Mt",num:1},{t:"Pos.",num:1}],
    K.winning,
    r=>`<tr><td class="kw">${r.keyword}</td><td class="num">${vol(r.volume)}</td><td class="num arrow-up">${r.position}</td></tr>`);

  table("kwSeason",
    [{t:"Keyword"},{t:"Ø Vol./Mt",num:1},{t:"Peak",num:1},{t:"Peak-Monat"}],
    K.season,
    r=>`<tr><td class="kw">${r.keyword}</td><td class="num">${vol(r.volume)}</td>
     <td class="num"><strong>${vol(r.peak)}</strong></td><td>${r.peakMonth||'—'}</td></tr>`);
}

if(D.shopify){
  document.getElementById('shopifyCard').style.display='block';
  const s = D.shopify;
  document.getElementById('shopify').innerHTML = Object.entries(s)
    .map(([k,v])=>`<span class="chip">${k}: ${v}</span>`).join(" ");
}
</script>
</body>
</html>
"""

if __name__ == "__main__":
    main()
