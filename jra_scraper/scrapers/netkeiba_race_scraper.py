import logging
import re
import time
from datetime import datetime
from typing import Optional
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from jra_scraper.config.settings import ScrapingConfig
from jra_scraper.scrapers.race_name_map import RACE_SPECIAL_IDS, RACE_ALIASES

logger = logging.getLogger(__name__)


class NetkeibaRaceScraper:
    SCHEDULE_URL = "https://race.netkeiba.com/top/schedule.html"
    SPECIAL_URL = "https://race.netkeiba.com/special/index.html"
    SHUTUBA_URL = "https://race.netkeiba.com/race/shutuba.html"
    RESULT_URL = "https://race.netkeiba.com/race/result.html"
    DB_URL = "https://db.netkeiba.com"

    def __init__(self, config: Optional[ScrapingConfig] = None):
        self.config = config or ScrapingConfig()
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": self.config.user_agent})
        self._last_request_time = 0.0
        self._race_name_map = None

    def _rate_limit(self):
        elapsed = time.time() - self._last_request_time
        if elapsed < self.config.rate_limit:
            time.sleep(self.config.rate_limit - elapsed)
        self._last_request_time = time.time()

    def _fetch(self, url: str, encoding: str = "utf-8", rate_limit: bool = True) -> Optional[BeautifulSoup]:
        if rate_limit:
            self._rate_limit()
        for attempt in range(self.config.max_retries):
            try:
                resp = self.session.get(url, timeout=self.config.request_timeout)
                resp.encoding = encoding
                if resp.status_code == 200:
                    return BeautifulSoup(resp.text, "html.parser")
                elif resp.status_code == 404:
                    logger.warning("Page not found: %s", url)
                    return None
                else:
                    logger.warning("HTTP %d: %s", resp.status_code, url)
            except requests.RequestException as e:
                logger.warning("Error (%d/%d): %s - %s", attempt + 1, self.config.max_retries, url, e)
            if attempt < self.config.max_retries - 1:
                delay = min(self.config.retry_delay * (2 ** attempt), self.config.max_delay)
                time.sleep(delay)
        logger.error("Failed after %d attempts: %s", self.config.max_retries, url)
        return None

    # ----------------------------------------------------------------
    #  Search: race name -> special page -> race_id
    # ----------------------------------------------------------------
    def _build_race_name_map(self) -> dict[str, str]:
        if self._race_name_map is not None:
            return self._race_name_map

        mapping = dict(RACE_SPECIAL_IDS)

        soup = self._fetch(self.SCHEDULE_URL)
        if soup:
            for a in soup.select("a[href*='special/index.html']"):
                text = a.get_text(strip=True)
                m = re.search(r"id=(\d+)", a.get("href", ""))
                if text and m and text not in mapping:
                    mapping[text] = m.group(1)

        self._race_name_map = mapping
        logger.info("Race name map: %d races", len(mapping))
        return mapping

    def _lookup_special_id(self, race_name: str) -> Optional[str]:
        name_map = self._build_race_name_map()
        canonical = RACE_ALIASES.get(race_name, race_name)
        sid = name_map.get(canonical) or name_map.get(race_name)
        if not sid:
            for key, val in name_map.items():
                if race_name in key or key in race_name:
                    sid = val
                    break
        return sid

    def find_race_id(self, race_name: str) -> Optional[str]:
        sid = self._lookup_special_id(race_name)
        if sid:
            return self._get_latest_race_id(sid)
        return None

    def _get_latest_race_id(self, special_id: str) -> Optional[str]:
        url = f"{self.SPECIAL_URL}?id={special_id}"
        soup = self._fetch(url)
        if not soup:
            return None

        # Best: find race_id from a link with "出馬表" text (main race)
        for a in soup.select("a[href*='race_id']"):
            text = a.get_text(strip=True)
            if text == "出馬表":
                m = re.search(r"race_id=(\d{12})", a["href"])
                if m:
                    return m.group(1)

        # Fallback: find race_id linked to shutuba.html
        for a in soup.select("a[href*='shutuba.html']"):
            m = re.search(r"race_id=(\d{12})", a["href"])
            if m:
                return m.group(1)

        # Last resort: pick the latest race_id for current year
        all_ids = set(re.findall(r"race_id=(\d{12})", str(soup)))
        if not all_ids:
            return None
        current_year = datetime.now().year
        this_year = sorted(rid for rid in all_ids if rid.startswith(str(current_year)))
        return this_year[-1] if this_year else max(all_ids)

    # ----------------------------------------------------------------
    #  Race info from shutuba page
    # ----------------------------------------------------------------
    def fetch_race_info(self, race_id: str) -> dict:
        url = f"{self.SHUTUBA_URL}?race_id={race_id}"
        soup = self._fetch(url)
        if not soup:
            return {"race_id": race_id, "error": "Page not found"}
        info = {"race_id": race_id}

        title_tag = soup.select_one("title")
        if title_tag:
            t = title_tag.get_text(strip=True)
            info["title"] = t
            m = re.search(r"(.+?)\s*(?:\(|出馬表)", t)
            if m:
                info["race_name"] = m.group(1).strip()
            m = re.search(r"(\d{4})年(\d{1,2})月(\d{1,2})日", t)
            if m:
                info["date"] = f"{m.group(1)}-{m.group(2).zfill(2)}-{m.group(3).zfill(2)}"
            m = re.search(r"(\d+)月(\d+)日\s*(\D+?)(\d+)R", t)
            if m:
                info["course"] = m.group(3)
                info["race_number"] = int(m.group(4))
            else:
                m = re.search(r"(\D+?)(\d+)R", t)
                if m:
                    info["course"] = m.group(1)
                    info["race_number"] = int(m.group(2))

        data01 = soup.select_one(".RaceData01")
        if data01:
            text = data01.get_text(" ", strip=True)
            m = re.search(r"(\d{2}:\d{2})発走", text)
            if m:
                info["start_time"] = m.group(1)
            m = re.search(r"(芝|ダート|障害)\s*(\d+)m", text)
            if m:
                info["track_type"] = m.group(1)
                info["distance"] = int(m.group(2))
            m = re.search(r"天候[:：]\s*(\S+)", text)
            if m:
                info["weather"] = m.group(1)
            m = re.search(r"馬場[:：]\s*(\S+)", text)
            if m:
                info["track_condition"] = m.group(1)

        data02 = soup.select_one(".RaceData02")
        if data02:
            text = data02.get_text(" ", strip=True)
            m = re.search(r"(\d+)頭", text)
            if m:
                info["horse_count"] = int(m.group(1))
        return info

    # ----------------------------------------------------------------
    #  Entries from shutuba page
    # ----------------------------------------------------------------
    def fetch_entries(self, race_id: str) -> list[dict]:
        url = f"{self.SHUTUBA_URL}?race_id={race_id}"
        soup = self._fetch(url)
        if not soup:
            return []
        table = soup.select_one("table.Shutuba_Table")
        if not table:
            return []
        entries = []
        for row in table.select("tr")[1:]:
            cells = row.select("td")
            if len(cells) < 8:
                continue
            entry = self._parse_entry_cells(cells)
            if entry:
                entries.append(entry)
        return entries

    def _parse_entry_cells(self, cells) -> Optional[dict]:
        try:
            entry = {}
            entry["gate_number"] = self._clean_int(cells[0].get_text(strip=True))
            entry["horse_number"] = self._clean_int(cells[1].get_text(strip=True))
            horse_td = cells[3]
            a = horse_td.find("a")
            if a:
                entry["horse_name"] = a.get_text(strip=True)
                m = re.search(r"/horse/(\d+)", a.get("href", ""))
                if m:
                    entry["horse_id"] = m.group(1)
            else:
                entry["horse_name"] = horse_td.get_text(strip=True)
            entry["sex_age"] = cells[4].get_text(strip=True)
            entry["weight"] = self._clean_float(cells[5].get_text(strip=True))
            entry["jockey"] = cells[6].get_text(strip=True)
            trainer_td = cells[7]
            a = trainer_td.find("a")
            entry["trainer"] = a.get_text(strip=True) if a else trainer_td.get_text(strip=True)
            if len(cells) > 8:
                wt_text = cells[8].get_text(strip=True)
                m = re.search(r"(\d+)", wt_text)
                if m:
                    entry["horse_weight"] = int(m.group(1))
                m2 = re.search(r"\(([+-]?\d+)\)", wt_text)
                if m2:
                    entry["weight_change"] = m2.group(1)
            if len(cells) > 10:
                pop_text = cells[10].get_text(strip=True)
                pop = self._clean_int(pop_text)
                if pop:
                    entry["popularity"] = pop
            return entry
        except Exception as e:
            logger.debug("Failed to parse entry row: %s", e)
            return None

    # ----------------------------------------------------------------
    #  Horse recent results from db.netkeiba
    # ----------------------------------------------------------------
    def fetch_horse_recent_results(self, horse_id: str, limit: int = 5) -> list[dict]:
        url = f"{self.DB_URL}/horse/result/{horse_id}/"
        soup = self._fetch(url, encoding="euc-jp")
        if not soup:
            return []
        table = soup.select_one("table.db_h_race_results")
        if not table:
            return []
        header_row = table.select_one("tr")
        col_map = {}
        for i, th in enumerate(header_row.select("th, td")):
            text = th.get_text(strip=True).replace("\u3000", "")
            if text:
                col_map[text] = i
        results = []
        for row in table.select("tr")[1:]:
            if len(results) >= limit:
                break
            r = self._parse_horse_result_row(row, col_map)
            if r:
                results.append(r)
        return results

    def _parse_horse_result_row(self, row, col_map) -> Optional[dict]:
        try:
            cells = row.select("td")
            if len(cells) < 15:
                return None

            def get(header_key: str, default: str = "") -> str:
                idx = col_map.get(header_key)
                if idx is not None and idx < len(cells):
                    return cells[idx].get_text(strip=True)
                return default

            result = {}
            raw_date = get("日付")
            result["date"] = raw_date.replace("/", "-") if "/" in raw_date else raw_date
            result["venue"] = get("開催")
            result["weather"] = get("天気")
            result["race_name"] = get("レース名")
            result["finishing_position"] = self._clean_int(get("着順"))
            result["total_horses"] = self._clean_int(get("頭数"))
            result["odds"] = self._clean_float(get("オッズ"))
            result["popularity"] = self._clean_int(get("人気"))
            result["jockey"] = get("騎手")
            result["weight_carried"] = self._clean_float(get("斤量"))
            course_raw = get("距離")
            m = re.search(r"(芝|ダート|障害)\s*(\d+)m?", course_raw)
            if m:
                result["track_type"] = m.group(1)
                result["distance"] = int(m.group(2))
            else:
                m2 = re.search(r"(\d+)", course_raw)
                if m2:
                    result["distance"] = int(m2.group(1))
            result["track_condition"] = get("馬場")
            result["time"] = get("タイム")
            result["margin"] = get("着差")
            result["passing_order"] = get("通過")
            result["last_3f"] = get("上り")
            hw_text = get("馬体重")
            m = re.search(r"(\d+)", hw_text)
            if m:
                result["horse_weight"] = int(m.group(1))
            m2 = re.search(r"\(([+-]?\d+)\)", hw_text)
            if m2:
                result["weight_change"] = m2.group(1)
            return result
        except Exception as e:
            logger.debug("Failed to parse horse result row: %s", e)
            return None

    # ----------------------------------------------------------------
    #  Odds from result page
    # ----------------------------------------------------------------
    def fetch_odds_from_result(self, race_id: str) -> dict:
        url = f"{self.RESULT_URL}?race_id={race_id}"
        soup = self._fetch(url)
        if not soup:
            return {}
        odds = {
            "race_id": race_id,
            "fetched_at": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "win_odds": [],
        }
        result_table = soup.select_one("table.RaceTable01")
        if result_table:
            for row in result_table.select("tr")[1:]:
                cells = row.select("td")
                if len(cells) >= 11:
                    horse_num = self._clean_int(cells[2].get_text(strip=True))
                    horse_name = cells[3].get_text(strip=True)
                    ninki = self._clean_int(cells[9].get_text(strip=True))
                    odds_val = self._clean_float(cells[10].get_text(strip=True))
                    if horse_num:
                        odds["win_odds"].append({
                            "horse_number": horse_num,
                            "horse_name": horse_name,
                            "odds": odds_val,
                            "popularity": ninki,
                        })
        payout_tables = soup.select("table.Payout_Detail_Table")
        if payout_tables:
            odds["payout"] = []
            for t in payout_tables:
                odds["payout"].append(t.get_text(" ", strip=True))
        return odds

    # ----------------------------------------------------------------
    #  Horse weight from result page
    # ----------------------------------------------------------------
    def fetch_horse_weight(self, race_id: str) -> list[dict]:
        url = f"{self.RESULT_URL}?race_id={race_id}"
        soup = self._fetch(url)
        if not soup:
            return []
        weights = []
        table = soup.select_one("table.RaceTable01")
        if not table:
            return weights
        for row in table.select("tr")[1:]:
            cells = row.select("td")
            if len(cells) < 15:
                continue
            horse_num = self._clean_int(cells[2].get_text(strip=True))
            weight_text = cells[14].get_text(strip=True)
            m = re.search(r"(\d+)", weight_text)
            m2 = re.search(r"\(([+-]?\d+)\)", weight_text)
            if m and horse_num:
                weights.append({
                    "horse_number": horse_num,
                    "horse_weight": int(m.group(1)),
                    "weight_change": m2.group(1) if m2 else "",
                })
        return weights

    # ----------------------------------------------------------------
    #  Training info
    # ----------------------------------------------------------------
    def fetch_training_info(self, horse_id: str) -> dict:
        info = {"horse_id": horse_id, "last_work": ""}
        url = f"{self.DB_URL}/horse/{horse_id}/"
        soup = self._fetch(url, encoding="euc-jp")
        if not soup:
            return info
        for sel in [".training", ".Training", ".work", ".train"]:
            el = soup.select_one(sel)
            if el:
                text = el.get_text(" ", strip=True)
                if len(text) > 3:
                    info["last_work"] = text[:200]
                    break
        return info

    # ----------------------------------------------------------------
    #  Pedigree
    # ----------------------------------------------------------------
    def fetch_pedigree(self, horse_id: str) -> list[str]:
        url = f"{self.DB_URL}/horse/ped/{horse_id}/"
        soup = self._fetch(url, encoding="euc-jp")
        if not soup:
            return []
        table = soup.select_one("table.blood_table")
        if not table:
            return []
        skip = {"血統", "産駒", "TOP", "戦績"}
        found: list[str] = []
        for a in table.select("a[href*='/horse/']"):
            name = a.get_text(strip=True)
            if name and name not in skip and len(name) <= 20 and name not in found:
                found.append(name)
        return found[:7]

    # ----------------------------------------------------------------
    #  Helpers
    # ----------------------------------------------------------------
    @staticmethod
    def _clean_int(text) -> Optional[int]:
        if not text:
            return None
        text = re.sub(r"[^\d\-]", "", str(text).strip())
        if text and text != "-":
            try:
                return int(text)
            except ValueError:
                return None
        return None

    @staticmethod
    def _clean_float(text) -> Optional[float]:
        if not text:
            return None
        text = re.sub(r"[^\d\.\-]", "", str(text).strip())
        if text and text != "-":
            try:
                return float(text)
            except ValueError:
                return None
        return None

    def close(self):
        self.session.close()
