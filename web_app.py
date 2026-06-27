"""
スマホ対応 Web UI - netkeiba レース情報取得
起動: python web_app.py
本番: gunicorn web_app:app
"""
import logging
import os
import re
import sys
import time
from collections import OrderedDict
from io import BytesIO
import zipfile

# Ensure project root is importable (needed for Render / gunicorn)
_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd
from flask import Flask, render_template_string, request, Response

from jra_scraper.services.race_scraping_service import RaceScrapingService

logging.basicConfig(level=logging.WARNING)
logger = logging.getLogger(__name__)

app = Flask(__name__)

HTML = r"""<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1.0">
<title>競馬レース情報</title>
<style>
*{box-sizing:border-box;margin:0;padding:0}
body{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,sans-serif;background:#f5f5f5;padding:12px;color:#333}
.container{max-width:800px;margin:0 auto}
h1{font-size:20px;margin-bottom:12px;color:#1a1a2e}
.search-box{background:#fff;border-radius:10px;padding:14px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:12px}
.search-box form{display:flex;gap:8px}
.search-box input[type=text]{flex:1;padding:10px 12px;font-size:16px;border:1px solid #ddd;border-radius:8px;outline:none}
.search-box input[type=text]:focus{border-color:#4a90d9}
.search-box button{padding:10px 18px;font-size:16px;background:#4a90d9;color:#fff;border:none;border-radius:8px;cursor:pointer;white-space:nowrap}
.search-box button:active{background:#357abd}
.card{background:#fff;border-radius:10px;padding:14px;box-shadow:0 1px 4px rgba(0,0,0,.08);margin-bottom:12px;overflow-x:auto}
.card h2{font-size:16px;color:#1a1a2e;margin-bottom:8px;padding-bottom:6px;border-bottom:1px solid #eee}
.info-grid{display:grid;grid-template-columns:1fr 1fr;gap:6px 16px}
.info-grid dt{font-size:12px;color:#888;margin-top:4px}
.info-grid dd{font-size:15px;font-weight:600;margin-bottom:4px}
table{width:100%;border-collapse:collapse;font-size:13px;min-width:480px}
th,td{padding:6px 8px;text-align:center;border-bottom:1px solid #eee;white-space:nowrap}
th{background:#fafafa;color:#666;font-weight:600;position:sticky;top:0}
.note-row{padding:4px 0;font-size:13px;border-bottom:1px solid #f0f0f0}
.note-row .label{color:#888;display:inline-block;min-width:70px}
.note-row .content{color:#333}
.btn-dl{display:inline-block;padding:6px 14px;font-size:13px;background:#34a853;color:#fff;border-radius:6px;text-decoration:none;margin:4px 4px 0 0}
.error{background:#fff0f0;border:1px solid #fcc;color:#c00;border-radius:8px;padding:12px;margin-bottom:12px;font-size:14px}
@media(max-width:480px){
  body{padding:8px}
  .card{padding:10px}
  table{font-size:12px;min-width:100%}
  th,td{padding:4px 5px}
  .search-box form{flex-direction:column}
  .search-box button{width:100%}
}
</style>
</head>
<body>
<div class="container">
<h1>&#x1F3C7; レース情報</h1>
<div class="search-box">
<form method="post" onsubmit="this.querySelector('button').disabled=true;this.querySelector('button').textContent='取得中...'">
<input type="text" name="race_name" placeholder="レース名（例: 日本ダービー）" value="{{ query }}" required>
<button type="submit">検索</button>
</form>
</div>

{% if error %}
<div class="error">{{ error }}</div>
{% endif %}

{% if race_info %}
<div class="card">
<h2>&#x1F4CB; レース基本情報</h2>
<dl class="info-grid">
<dt>レース名</dt><dd>{{ race_info.レース名 }}</dd>
<dt>開催</dt><dd>{{ race_info.開催日 }} {{ race_info.競馬場 }}{{ race_info.レース番号 }}R</dd>
<dt>コース</dt><dd>{{ race_info.コース種別 }}{{ race_info.距離 }}m</dd>
<dt>馬場</dt><dd>{{ race_info.馬場状態 }}</dd>
<dt>天候</dt><dd>{{ race_info.天候 }}</dd>
<dt>発走</dt><dd>{{ race_info.発走時刻 }}</dd>
</dl>
</div>
{% endif %}

{% if entries is not none and not entries.empty %}
<div class="card">
<h2>&#x1F40E; 出走馬 ({{ entries|length }}頭)</h2>
<div style="overflow-x:auto">
<table>
<thead><tr>{% for col in entry_cols %}<th>{{ col }}</th>{% endfor %}</tr></thead>
<tbody>
{% for _, row in entries.iterrows() %}
<tr>{% for col in entry_cols %}<td>{{ row[col] if row[col] else '' }}</td>{% endfor %}</tr>
{% endfor %}
</tbody>
</table>
</div>
<a class="btn-dl" href="/download/entries/{{ cache_key }}">CSV</a>
</div>
{% endif %}

{% if odds is not none and not odds.empty %}
<div class="card">
<h2>&#x1F4B0; オッズ</h2>
<div style="overflow-x:auto">
<table>
<thead><tr>{% for col in odds_cols %}<th>{{ col }}</th>{% endfor %}</tr></thead>
<tbody>
{% for _, row in odds.iterrows() %}
<tr>{% for col in odds_cols %}<td>{{ row[col] if row[col] else '' }}</td>{% endfor %}</tr>
{% endfor %}
</tbody>
</table>
</div>
<a class="btn-dl" href="/download/odds/{{ cache_key }}">CSV</a>
</div>
{% endif %}

{% if recent_results is not none and not recent_results.empty %}
<div class="card">
<h2>&#x1F4CA; 近走成績</h2>
<div style="overflow-x:auto">
<table>
<thead><tr>{% for col in result_cols %}<th>{{ col }}</th>{% endfor %}</tr></thead>
<tbody>
{% for _, row in recent_results.iterrows() %}
<tr>{% for col in result_cols %}<td>{{ row[col] if row[col] else '' }}</td>{% endfor %}</tr>
{% endfor %}
</tbody>
</table>
</div>
<a class="btn-dl" href="/download/recent_results/{{ cache_key }}">CSV</a>
</div>
{% endif %}

{% if notes is not none and not notes.empty %}
<div class="card">
<h2>&#x1F4DD; 補足情報</h2>
{% for _, nr in notes.iterrows() %}
<div class="note-row">
<span class="label">{{ nr.馬名 }}</span>
<strong>{{ nr.note_type }}</strong>:
<span class="content">{{ nr.content[:120] }}{% if nr.content|length > 120 %}...{% endif %}</span>
</div>
{% endfor %}
<a class="btn-dl" href="/download/notes/{{ cache_key }}">CSV</a>
{% endif %}

{% if cache_key %}
<div style="text-align:center;padding:16px;font-size:12px;color:#888">
<a class="btn-dl" style="background:#666" href="/dl_all/{{ cache_key }}">すべてCSV(ZIP)</a>
</div>
{% endif %}
</div>
</body>
</html>"""

# LRU cache: {cache_key: {"race_name": str, "dfs": dict, "time": float}}
_cache: OrderedDict = OrderedDict()
MAX_CACHE = 20


def _cache_store(race_name: str, dfs: dict) -> str:
    key = f"{int(time.time())}{hash(race_name) % 10000}"
    _cache[key] = {"race_name": race_name, "dfs": dfs, "time": time.time()}
    while len(_cache) > MAX_CACHE:
        _cache.popitem(last=False)
    return key


def _cache_get(key: str) -> dict | None:
    entry = _cache.get(key)
    if entry and time.time() - entry["time"] < 600:
        return entry["dfs"]
    _cache.pop(key, None)
    return None


@app.route("/", methods=["GET", "POST"])
def index():
    ctx = {"query": "", "error": None, "race_info": None, "entries": None,
            "entry_cols": [], "odds": None, "odds_cols": [],
            "recent_results": None, "result_cols": [], "notes": None, "cache_key": ""}

    race_name = request.form.get("race_name", "").strip()
    if not race_name:
        return render_template_string(HTML, **ctx)

    ctx["query"] = race_name
    try:
        service = RaceScrapingService()
        dfs = service.run(race_name)
        service.close()
        if not dfs:
            ctx["error"] = f"「{race_name}」が見つかりません"
            return render_template_string(HTML, **ctx)

        ck = _cache_store(race_name, dfs)
        ctx["cache_key"] = ck

        ri = dfs.get("race_info")
        ctx["race_info"] = ri.iloc[0].to_dict() if ri is not None and not ri.empty else None

        entries = dfs.get("entries")
        if entries is not None and not entries.empty:
            ctx["entries"] = entries
            ctx["entry_cols"] = [c for c in ["枠番", "馬番", "馬名", "性齢", "斤量", "騎手", "馬体重"] if c in entries.columns]

        odds = dfs.get("odds")
        if odds is not None and not odds.empty:
            ctx["odds"] = odds
            ctx["odds_cols"] = [c for c in ["馬番", "馬名", "単勝オッズ", "人気"] if c in odds.columns]

        results = dfs.get("recent_results")
        if results is not None and not results.empty:
            ctx["recent_results"] = results
            ctx["result_cols"] = [c for c in ["馬名", "開催日", "レース名", "着順", "頭数", "人気", "通過順位", "上がり3F", "騎手"] if c in results.columns]

        notes = dfs.get("notes")
        ctx["notes"] = notes
    except Exception as e:
        logger.exception("Error")
        ctx["error"] = f"エラー: {e}"

    return render_template_string(HTML, **ctx)


@app.route("/download/<table>/<cache_key>")
def download(table: str, cache_key: str):
    dfs = _cache_get(cache_key)
    if not dfs:
        return "Data expired, please search again", 404
    df = dfs.get(table)
    if df is None or df.empty:
        return "No data", 404
    ri = dfs.get("race_info")
    race_name = ""
    if ri is not None and not ri.empty:
        race_name = ri.iloc[0].get("レース名", "")
    safe = re.sub(r'[\\/:*?"<>|]+', "_", race_name) or "race"
    buf = BytesIO()
    df.to_csv(buf, index=False, encoding="utf-8-sig")
    csv_bytes = buf.getvalue()
    return Response(
        csv_bytes,
        mimetype="text/csv",
        headers={"Content-Disposition": f'attachment; filename="{safe}_{table}.csv"'},
    )


@app.route("/dl_all/<cache_key>")
def download_all(cache_key: str):
    dfs = _cache_get(cache_key)
    if not dfs:
        return "Data expired, please search again", 404
    ri = dfs.get("race_info")
    race_name = ""
    if ri is not None and not ri.empty:
        race_name = ri.iloc[0].get("レース名", "")
    safe = re.sub(r'[\\/:*?"<>|]+', "_", race_name) or "race"
    buf = BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        for key, df in dfs.items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                csv_buf = BytesIO()
                df.to_csv(csv_buf, index=False, encoding="utf-8-sig")
                zf.writestr(f"{key}.csv", csv_buf.getvalue())
    zip_bytes = buf.getvalue()
    return Response(
        zip_bytes,
        mimetype="application/zip",
        headers={"Content-Disposition": f'attachment; filename="{safe}.zip"'},
    )


@app.route("/health")
def health():
    return "ok", 200


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="競馬情報 Web UI")
    parser.add_argument("--port", type=int, default=5000)
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--debug", action="store_true")
    parser.add_argument("--threaded", action="store_true", default=True)
    args = parser.parse_args()
    print(f"http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug, threaded=args.threaded)
