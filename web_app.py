"""
スマホ対応 Web UI - netkeiba レース情報取得 (async loading for Render)
起動: python web_app.py
本番: gunicorn web_app:app
"""
import logging
import os
import re
import sys
import time
import traceback
import threading
import urllib.parse
from collections import OrderedDict
import json

_cache_lock = threading.Lock()

_root = os.path.dirname(os.path.abspath(__file__))
if _root not in sys.path:
    sys.path.insert(0, _root)

import pandas as pd
from flask import Flask, render_template_string, request, Response, jsonify

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
.loading{text-align:center;padding:24px;color:#888;font-size:14px}
.spinner{display:inline-block;width:20px;height:20px;border:3px solid #ddd;border-top-color:#4a90d9;border-radius:50%;animation:spin .8s linear infinite;vertical-align:middle;margin-right:8px}
@keyframes spin{to{transform:rotate(360deg)}}
.hidden{display:none}
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
<form method="post" onsubmit="this.querySelector('button').disabled=true;this.querySelector('button').textContent='検索中...'">
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
<div class="card" id="card-entries">
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
<div class="card" id="card-odds">
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

<div id="loading-details" class="loading {% if not task_key %}hidden{% endif %}">
  <span class="spinner"></span><span id="loading-text">詳細データを取得中...</span>
</div>
<div id="card-results" class="hidden">
  <div class="card">
    <h2>&#x1F4CA; 近走成績</h2>
    <div id="results-table" style="overflow-x:auto"></div>
    <a class="btn-dl hidden" id="dl-results" href="">CSV</a>
  </div>
</div>
<div id="card-notes" class="hidden">
  <div class="card">
    <h2>&#x1F4DD; 補足情報</h2>
    <div id="notes-content"></div>
    <a class="btn-dl hidden" id="dl-notes" href="">CSV</a>
  </div>
</div>

{% if cache_key %}
<div style="text-align:center;padding:16px;font-size:12px;color:#888">
<a class="btn-dl" style="background:#666" href="/dl_all/{{ cache_key }}">すべてCSV(ZIP)</a>
</div>
{% endif %}
</div>

<script>
{% if task_key %}
(function(){
  var poll = setInterval(function(){
    var x = new XMLHttpRequest();
    x.open('GET', '/progress/' + '{{ task_key }}');
    x.onload = function(){
      if(x.status == 200){
        var d = JSON.parse(x.responseText);
        if(d.status == 'complete'){
          clearInterval(poll);
          document.getElementById('loading-details').classList.add('hidden');
          if(d.data.results){
            var r = document.getElementById('card-results');
            r.classList.remove('hidden');
            document.getElementById('results-table').innerHTML = d.data.results;
            document.getElementById('dl-results').href = '/download/recent_results/{{ cache_key }}';
            document.getElementById('dl-results').classList.remove('hidden');
          }
          if(d.data.notes){
            document.getElementById('card-notes').classList.remove('hidden');
            document.getElementById('notes-content').innerHTML = d.data.notes;
            document.getElementById('dl-notes').href = '/download/notes/{{ cache_key }}';
            document.getElementById('dl-notes').classList.remove('hidden');
          }
          document.getElementById('loading-text').textContent = '完了';
        } else if(d.status == 'error'){
          clearInterval(poll);
          document.getElementById('loading-text').textContent = '詳細データの取得に失敗: ' + (d.error || '不明');
        } else {
          document.getElementById('loading-text').textContent = d.message || '詳細データを取得中...';
        }
      }
    };
    x.send();
  }, 2000);
})();
{% endif %}
</script>
</body>
</html>"""

# Task tracking: {task_key: {"status": str, "message": str, "data": dict, "time": float}}
_tasks: OrderedDict = OrderedDict()
MAX_TASKS = 50

def _task_create(race_name: str) -> str:
    with _cache_lock:
        key = f"t{int(time.time())}{hash(race_name) % 100000}"
        _tasks[key] = {"status": "pending", "message": "Starting...", "data": {}, "time": time.time()}
        while len(_tasks) > MAX_TASKS:
            _tasks.popitem(last=False)
    return key

def _task_update(key: str, status: str, message: str = "", data: dict = None):
    with _cache_lock:
        entry = _tasks.get(key)
        if entry:
            entry["status"] = status
            entry["message"] = message
            if data:
                entry["data"] = data
            entry["time"] = time.time()

def _task_get(key: str):
    with _cache_lock:
        entry = _tasks.get(key)
        if entry and time.time() - entry["time"] < 600:
            return dict(entry)
        _tasks.pop(key, None)
    return None

# LRU cache for full data
_cache: OrderedDict = OrderedDict()
MAX_CACHE = 20

def _cache_store(race_name: str, dfs: dict) -> str:
    with _cache_lock:
        key = f"{int(time.time())}{hash(race_name) % 10000}"
        _cache[key] = {"race_name": race_name, "dfs": dfs, "time": time.time()}
        while len(_cache) > MAX_CACHE:
            _cache.popitem(last=False)
    return key

def _cache_get(key: str) -> dict | None:
    with _cache_lock:
        entry = _cache.get(key)
        if entry and time.time() - entry["time"] < 600:
            return entry.get("dfs", {})
        _cache.pop(key, None)
    return None

def _cache_update(store_key: str, new_dfs: dict):
    with _cache_lock:
        entry = _cache.get(store_key)
        if entry:
            entry["dfs"].update(new_dfs)
            entry["time"] = time.time()

@app.route("/", methods=["GET", "POST"])
def index():
    ctx = {"query": "", "error": None, "race_info": None, "entries": None,
            "entry_cols": [], "odds": None, "odds_cols": [],
            "recent_results": None, "result_cols": [], "notes": None,
            "cache_key": "", "task_key": ""}

    race_name = request.form.get("race_name", "").strip()
    if not race_name:
        return render_template_string(HTML, **ctx)

    ctx["query"] = race_name
    try:
        # Phase 1: quick fetch (must finish within Render proxy timeout ~30s)
        service = RaceScrapingService()
        race_id = service.scraper.find_race_id(race_name)
        if not race_id:
            service.close()
            ctx["error"] = f"「{race_name}」が見つかりません"
            return render_template_string(HTML, **ctx)

        race_info = service.scraper.fetch_race_info(race_id)
        entries = service.scraper.fetch_entries(race_id)
        odds_data = service.scraper.fetch_odds(race_id)
        horse_weights = service.scraper.fetch_horse_weight(race_id)

        # Build partial DataFrames (no horse details yet)
        ri_df = service._build_race_info_df(race_info)
        en_df = service._build_entries_df(entries)
        od_df = service._build_odds_df(odds_data)
        dfs_partial = {
            "race_info": ri_df,
            "entries": en_df,
            "odds": od_df,
            "recent_results": pd.DataFrame(),
            "notes": pd.DataFrame(),
        }
        ck = _cache_store(race_name, dict(dfs_partial))
        ctx["cache_key"] = ck

        if ri_df is not None and not ri_df.empty:
            ctx["race_info"] = ri_df.iloc[0].to_dict()
        if en_df is not None and not en_df.empty:
            ctx["entries"] = en_df
            ctx["entry_cols"] = [c for c in ["枠番", "馬番", "馬名", "性齢", "斤量", "騎手", "馬体重"] if c in en_df.columns]
        if od_df is not None and not od_df.empty:
            ctx["odds"] = od_df
            ctx["odds_cols"] = [c for c in ["馬番", "馬名", "単勝オッズ", "人気"] if c in od_df.columns]

        # Phase 2: start background thread for heavy data
        task_key = _task_create(race_name)

        def _bg_work(task_k, cache_k, svc, rn):
            try:
                _task_update(task_k, "loading", "馬データ取得中...")
                svc.run(rn)
                dfs_full = svc.get_dataframes()
                _cache_update(cache_k, dfs_full)
                notes_html = _render_notes_html(dfs_full.get("notes"))
                results_html = _render_results_html(dfs_full.get("recent_results"))
                _task_update(task_k, "complete", "", {"notes": notes_html, "results": results_html})
            except Exception as e:
                logger.exception("BG error")
                _task_update(task_k, "error", "", {"error": str(e)})
            finally:
                try:
                    svc.close()
                except Exception:
                    pass

        t = threading.Thread(target=_bg_work, args=(task_key, ck, service, race_name), daemon=True)
        t.start()
        ctx["task_key"] = task_key

    except Exception as e:
        logger.exception("Error")
        ctx["error"] = f"エラー: {e}"

    return render_template_string(HTML, **ctx)


@app.route("/progress/<task_key>")
def progress(task_key: str):
    entry = _task_get(task_key)
    if not entry:
        return jsonify({"status": "expired"})
    return jsonify({
        "status": entry["status"],
        "message": entry.get("message", ""),
        "data": entry.get("data", {}),
    })


def _render_notes_html(notes_df):
    if notes_df is None or notes_df.empty:
        return None
    parts = []
    for _, nr in notes_df.iterrows():
        name = nr.get("馬名", "")
        nt = nr.get("note_type", "")
        ct = str(nr.get("content", ""))
        if len(ct) > 120:
            ct = ct[:120] + "..."
        parts.append(f'<div class="note-row"><span class="label">{name}</span><strong>{nt}</strong>: <span class="content">{ct}</span></div>')
    return "".join(parts) if parts else None


def _render_results_html(results_df):
    if results_df is None or results_df.empty:
        return None
    cols = [c for c in ["馬名", "開催日", "レース名", "着順", "頭数", "人気", "通過順位", "上がり3F", "騎手"] if c in results_df.columns]
    rows = []
    for _, r in results_df.iterrows():
        cells = "".join(f"<td>{r[c] if r[c] is not None else ''}</td>" for c in cols)
        rows.append(f"<tr>{cells}</tr>")
    thead = "".join(f"<th>{c}</th>" for c in cols)
    return f'<table><thead><tr>{thead}</tr></thead><tbody>{"".join(rows)}</tbody></table>'


@app.route("/download/<table>/<cache_key>")
def download(table: str, cache_key: str):
    try:
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
        safe = re.sub(r'[^a-zA-Z0-9_]+', "_", race_name)[:30] or "race"
        fname = urllib.parse.quote(f"{safe}_{table}.csv")
        csv_text = df.to_csv(index=False)
        r = Response(
            csv_text,
            mimetype="text/csv; charset=utf-8",
            headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"},
        )
        return r
    except Exception:
        return f"ERROR: {traceback.format_exc()}", 500


@app.route("/dl_all/<cache_key>")
def download_all(cache_key: str):
    dfs = _cache_get(cache_key)
    if not dfs:
        return "Data expired, please search again", 404
    ri = dfs.get("race_info")
    race_name = ""
    if ri is not None and not ri.empty:
        race_name = ri.iloc[0].get("レース名", "")
    safe = re.sub(r'[^a-zA-Z0-9_]+', "_", race_name)[:30] or "race"
    fname = urllib.parse.quote(f"{safe}_all.txt")
    parts = []
    for key, df in dfs.items():
        if isinstance(df, pd.DataFrame) and not df.empty:
            parts.append(f"--- {key}.csv ---")
            parts.append(df.to_csv(index=False))
    text = "\n".join(parts)
    return Response(
        text,
        mimetype="text/plain; charset=utf-8",
        headers={"Content-Disposition": f"attachment; filename*=UTF-8''{fname}"},
    )


@app.route("/health")
def health():
    return "ok", 200




if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="競馬情報 Web UI")
    parser.add_argument("--port", type=int, default=int(os.environ.get("PORT", 5000)))
    parser.add_argument("--host", default="0.0.0.0")
    parser.add_argument("--debug", action="store_true")
    args = parser.parse_args()
    print(f"http://{args.host}:{args.port}")
    app.run(host=args.host, port=args.port, debug=args.debug)
