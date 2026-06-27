import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from typing import Optional

import pandas as pd

from jra_scraper.config.settings import ScrapingConfig
from jra_scraper.scrapers.netkeiba_race_scraper import NetkeibaRaceScraper

logger = logging.getLogger(__name__)


class RaceScrapingService:
    def __init__(self, config: Optional[ScrapingConfig] = None):
        self.config = config or ScrapingConfig()
        self.scraper = NetkeibaRaceScraper(self.config)
        self._data = {}

    def run(self, race_name: str) -> dict[str, pd.DataFrame]:
        logger.info("Searching for race: %s", race_name)
        race_id = self.scraper.find_race_id(race_name)
        if not race_id:
            logger.error("Race not found: %s", race_name)
            return {}
        logger.info("Found race ID: %s", race_id)
        return self._fetch_all(race_id)

    def run_by_id(self, race_id: str) -> dict[str, pd.DataFrame]:
        logger.info("Fetching race ID: %s", race_id)
        return self._fetch_all(race_id)

    def _fetch_all(self, race_id: str) -> dict[str, pd.DataFrame]:
        race_info = self.scraper.fetch_race_info(race_id)
        entries = self.scraper.fetch_entries(race_id)
        odds_data = self.scraper.fetch_odds(race_id)
        horse_weights = self.scraper.fetch_horse_weight(race_id)

        recent_results, notes_rows = self._fetch_horse_data_parallel(entries)
        self._add_horse_weight_notes(horse_weights, entries, notes_rows)

        dfs = {
            "race_info": self._build_race_info_df(race_info),
            "entries": self._build_entries_df(entries),
            "recent_results": self._build_recent_results_df(recent_results),
            "odds": self._build_odds_df(odds_data),
            "notes": self._build_notes_df(notes_rows),
        }
        self._data = dfs
        return dfs

    def _fetch_horse_data_parallel(self, entries: list) -> tuple[list, list]:
        horse_entries = [e for e in entries if e.get("horse_id")]
        all_results: list = []
        all_notes: list = []
        lock = __import__("threading").Lock()

        def work(entry: dict):
            hid = entry["horse_id"]
            name = entry.get("horse_name", "")
            num = entry.get("horse_number")
            sc = NetkeibaRaceScraper(self.config)
            sc._rate_limit = lambda: None
            results = sc.fetch_horse_recent_results(hid, limit=5)
            for r in results:
                r["horse_name"] = name
                r["horse_number"] = num
                r["horse_id"] = hid
            notes: list = []
            training = sc.fetch_training_info(hid)
            if training.get("last_work"):
                notes.append({
                    "horse_name": name, "horse_number": num,
                    "note_type": "調教", "content": training["last_work"],
                })
            ped = sc.fetch_pedigree(hid)
            if ped:
                notes.append({
                    "horse_name": name, "horse_number": num,
                    "note_type": "血統", "content": " → ".join(ped),
                })
            self._add_course_change_notes(entry, results, notes)
            self._add_distance_notes(entry, results, notes)
            self._add_jockey_change_notes(entry, results, notes)
            self._add_spacing_notes(entry, results, notes)
            return results, notes

        with ThreadPoolExecutor(max_workers=min(10, len(horse_entries))) as ex:
            futures = {ex.submit(work, e): e for e in horse_entries}
            for f in as_completed(futures):
                try:
                    rr, nn = f.result()
                    with lock:
                        all_results.extend(rr)
                        all_notes.extend(nn)
                except Exception as e:
                    logger.warning("Horse fetch failed: %s", e)

        return all_results, all_notes

    def _add_course_change_notes(self, entry: dict, recent_results: list, notes_rows: list):
        horse_races = [r for r in recent_results if r.get("horse_name") == entry.get("horse_name") and r.get("venue")]
        if len(horse_races) >= 2:
            last = horse_races[0].get("venue", "")
            prev = horse_races[1].get("venue", "")
            if last and prev and last != prev:
                notes_rows.append({
                    "horse_name": entry.get("horse_name", ""),
                    "horse_number": entry.get("horse_number"),
                    "note_type": "コース替わり",
                    "content": f"前走({prev}) → ({last})",
                })

    def _add_distance_notes(self, entry: dict, recent_results: list, notes_rows: list):
        horse_races = [r for r in recent_results if r.get("horse_name") == entry.get("horse_name") and r.get("distance")]
        if len(horse_races) >= 2:
            last = horse_races[0].get("distance")
            prev = horse_races[1].get("distance")
            if last and prev and last != prev:
                direction = "延長" if last > prev else "短縮"
                notes_rows.append({
                    "horse_name": entry.get("horse_name", ""),
                    "horse_number": entry.get("horse_number"),
                    "note_type": f"距離{direction}",
                    "content": f"前走{prev}m → {last}m ({direction})",
                })

    def _add_jockey_change_notes(self, entry: dict, recent_results: list, notes_rows: list):
        horse_races = [r for r in recent_results if r.get("horse_name") == entry.get("horse_name") and r.get("jockey")]
        if horse_races:
            prev = horse_races[0].get("jockey")
            curr = entry.get("jockey")
            if curr and prev and curr != prev:
                notes_rows.append({
                    "horse_name": entry.get("horse_name", ""),
                    "horse_number": entry.get("horse_number"),
                    "note_type": "騎手乗り替わり",
                    "content": f"前走: {prev} → 今回: {curr}",
                })

    def _add_spacing_notes(self, entry: dict, recent_results: list, notes_rows: list):
        horse_races = [r for r in recent_results if r.get("horse_name") == entry.get("horse_name") and r.get("date")]
        if horse_races:
            last_date_str = horse_races[0].get("date", "")
            if last_date_str:
                try:
                    last_date = datetime.strptime(last_date_str, "%Y-%m-%d")
                    today = datetime.now()
                    days = (today - last_date).days
                    if days > 0:
                        weeks = days // 7
                        notes_rows.append({
                            "horse_name": entry.get("horse_name", ""),
                            "horse_number": entry.get("horse_number"),
                            "note_type": "前走からの間隔",
                            "content": f"前走({last_date_str})から{days}日 ({weeks}週)",
                        })
                except ValueError:
                    pass

    def _add_pedigree_notes(self, entry: dict, horse_id: str, notes_rows: list):
        ped = self.scraper.fetch_pedigree(horse_id)
        if ped:
            notes_rows.append({
                "horse_name": entry.get("horse_name", ""),
                "horse_number": entry.get("horse_number"),
                "note_type": "血統",
                "content": " → ".join(ped),
            })

    def _add_horse_weight_notes(self, horse_weights: list, entries: list, notes_rows: list):
        wm = {}
        for w in horse_weights:
            hn = w.get("horse_number")
            if hn:
                wm[hn] = w
        for entry in entries:
            hn = entry.get("horse_number")
            if hn and hn in wm:
                w = wm[hn]
                change = w.get("weight_change", "")
                ct = f" (前回比{change}kg)" if change else ""
                notes_rows.append({
                    "horse_name": entry.get("horse_name", ""),
                    "horse_number": hn,
                    "note_type": "馬体重",
                    "content": f"{w['horse_weight']}kg{ct}",
                })

    # ------------------------------------------------------------------
    #  DataFrame builders
    # ------------------------------------------------------------------
    def _build_race_info_df(self, race_info: dict) -> pd.DataFrame:
        if not race_info or "error" in race_info:
            return pd.DataFrame()
        return pd.DataFrame([{
            "レースID": race_info.get("race_id", ""),
            "レース名": race_info.get("race_name", ""),
            "開催日": race_info.get("date", ""),
            "競馬場": race_info.get("course", ""),
            "レース番号": race_info.get("race_number", ""),
            "コース種別": race_info.get("track_type", ""),
            "距離": race_info.get("distance", ""),
            "馬場状態": race_info.get("track_condition", ""),
            "天候": race_info.get("weather", ""),
            "発走時刻": race_info.get("start_time", ""),
        }])

    def _build_entries_df(self, entries: list) -> pd.DataFrame:
        if not entries:
            return pd.DataFrame()
        rows = []
        for e in entries:
            rows.append({
                "枠番": e.get("gate_number"),
                "馬番": e.get("horse_number"),
                "馬名": e.get("horse_name", ""),
                "性齢": e.get("sex_age", ""),
                "斤量": e.get("weight"),
                "騎手": e.get("jockey", ""),
                "調教師": e.get("trainer", ""),
                "馬体重": e.get("horse_weight"),
                "体重増減": e.get("weight_change", ""),
                "horse_id": e.get("horse_id", ""),
            })
        return pd.DataFrame(rows)

    def _build_recent_results_df(self, results: list) -> pd.DataFrame:
        if not results:
            return pd.DataFrame()
        rows = []
        for r in results:
            rows.append({
                "馬名": r.get("horse_name", ""),
                "馬番": r.get("horse_number"),
                "horse_id": r.get("horse_id", ""),
                "開催日": r.get("date", ""),
                "レース名": r.get("race_name", ""),
                "競馬場": r.get("venue", ""),
                "コース種別": r.get("track_type", ""),
                "距離": r.get("distance"),
                "馬場状態": r.get("track_condition", ""),
                "天候": r.get("weather", ""),
                "着順": r.get("finishing_position"),
                "頭数": r.get("total_horses"),
                "人気": r.get("popularity"),
                "オッズ": r.get("odds"),
                "タイム": r.get("time", ""),
                "着差": r.get("margin", ""),
                "上がり3F": r.get("last_3f", ""),
                "通過順位": r.get("passing_order", ""),
                "騎手": r.get("jockey", ""),
                "斤量": r.get("weight_carried"),
                "馬体重": r.get("horse_weight"),
            })
        return pd.DataFrame(rows)

    def _build_odds_df(self, odds_data: dict) -> pd.DataFrame:
        rows = []
        fetched_at = odds_data.get("fetched_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S"))
        for od in odds_data.get("win_odds", []):
            rows.append({
                "馬番": od.get("horse_number"),
                "馬名": od.get("horse_name", ""),
                "単勝オッズ": od.get("odds"),
                "人気": od.get("popularity"),
                "オッズ取得時刻": fetched_at,
            })
        payout = odds_data.get("payout", [])
        for p in payout:
            rows.append({
                "馬番": "",
                "馬名": "",
                "単勝オッズ": "",
                "人気": "",
                "オッズ取得時刻": p[:100],
            })
        if not rows:
            return pd.DataFrame()
        return pd.DataFrame(rows)

    def _build_notes_df(self, notes_rows: list) -> pd.DataFrame:
        if not notes_rows:
            return pd.DataFrame()
        return pd.DataFrame(notes_rows)

    # ------------------------------------------------------------------
    #  File save
    # ------------------------------------------------------------------
    def save_csv(self, output_dir: Optional[str] = None, prefix: str = "") -> dict[str, str]:
        base_dir = output_dir or self.config.output_dir
        os.makedirs(base_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = prefix or ts
        paths = {}

        ri = self._data.get("race_info")
        if ri is not None and not ri.empty:
            name = ri.iloc[0].get("レース名", "") or "race"
            safe_name = re.sub(r'[\\/:*?"<>|]+', "_", str(name))
            prefix = f"{safe_name}_{ts}"

        for key, df in self._data.items():
            if isinstance(df, pd.DataFrame) and not df.empty:
                path = os.path.join(base_dir, f"{prefix}_{key}.csv")
                df.to_csv(path, index=False, encoding="utf-8-sig")
                paths[key] = path
                logger.info("Saved: %s", path)
        return paths

    def save_excel(self, output_dir: Optional[str] = None, prefix: str = "") -> Optional[str]:
        base_dir = output_dir or self.config.output_dir
        os.makedirs(base_dir, exist_ok=True)
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        prefix = prefix or ts
        ri = self._data.get("race_info")
        if ri is not None and not ri.empty:
            name = ri.iloc[0].get("レース名", "") or "race"
            safe_name = re.sub(r'[\\/:*?"<>|]+', "_", str(name))
            prefix = f"{safe_name}_{ts}"
        path = os.path.join(base_dir, f"{prefix}_race_data.xlsx")
        try:
            with pd.ExcelWriter(path, engine="openpyxl") as writer:
                for key, df in self._data.items():
                    if isinstance(df, pd.DataFrame) and not df.empty:
                        df.to_excel(writer, sheet_name=key, index=False)
            logger.info("Saved: %s", path)
            return path
        except Exception as e:
            logger.error("Failed to save Excel: %s", e)
            return None

    def get_dataframes(self) -> dict[str, pd.DataFrame]:
        return self._data

    def display_summary(self):
        print("=" * 60)
        ri = self._data.get("race_info")
        if ri is not None and not ri.empty:
            r = ri.iloc[0]
            print(f"レース: {r.get('レース名', '')}")
            print(f"開催日: {r.get('開催日', '')}  {r.get('競馬場', '')}{r.get('レース番号', '')}R")
            print(f"コース: {r.get('コース種別', '')}{r.get('距離', '')}m  馬場: {r.get('馬場状態', '')}")
            print(f"発走: {r.get('発走時刻', '')}  天候: {r.get('天候', '')}")
        print("-" * 60)

        entries_df = self._data.get("entries")
        if entries_df is not None and not entries_df.empty:
            print(f"\n出走馬: {len(entries_df)}頭")
            cols = [c for c in ["枠番", "馬番", "馬名", "性齢", "斤量", "騎手", "調教師", "馬体重"] if c in entries_df.columns]
            if cols:
                print(entries_df[cols].to_string(index=False))

        odds_df = self._data.get("odds")
        if odds_df is not None and not odds_df.empty:
            print("\nオッズ:")
            cols = [c for c in ["馬番", "馬名", "単勝オッズ", "人気"] if c in odds_df.columns]
            if cols:
                print(odds_df[cols].to_string(index=False))
        else:
            print("\nオッズ: 未発表（netkeibaにオッズ未掲載のため）")

        notes_df = self._data.get("notes")
        if notes_df is not None and not notes_df.empty:
            print("\n補足情報:")
            for _, nr in notes_df.iterrows():
                hn = nr.get("馬名", "")
                nt = nr.get("note_type", "")
                ct = nr.get("content", "")
                if isinstance(ct, str) and len(ct) > 100:
                    ct = ct[:100] + "..."
                print(f"  {hn} [{nt}]: {ct}")

        print("=" * 60)

    def close(self):
        self.scraper.close()
