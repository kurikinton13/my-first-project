from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class OddsType(Enum):
    WIN = "単勝"
    PLACE = "複勝"
    QUINELLA = "馬連"
    EXACTA = "馬単"
    WIDE = "ワイド"
    TRIO = "3連複"
    TRIFECTA = "3連単"


@dataclass
class Odds:
    odds_type: OddsType
    horse_numbers: tuple
    odds_value: float
    popularity: Optional[int] = None

    def __str__(self) -> str:
        if len(self.horse_numbers) == 1:
            return f"{self.odds_type.value} {self.horse_numbers[0]}番 {self.odds_value:.1f}倍"
        elif len(self.horse_numbers) == 2:
            return f"{self.odds_type.value} {self.horse_numbers[0]}-{self.horse_numbers[1]} {self.odds_value:.1f}倍"
        else:
            nums = "-".join(str(n) for n in self.horse_numbers)
            return f"{self.odds_type.value} {nums} {self.odds_value:.1f}倍"


@dataclass
class OddsSnapshot:
    timestamp: datetime
    odds_list: list = field(default_factory=list)
    source_url: Optional[str] = None

    def add_odds(self, odds: Odds) -> None:
        self.odds_list.append(odds)

    def get_odds_by_type(self, odds_type: OddsType) -> list:
        return [o for o in self.odds_list if o.odds_type == odds_type]

    def get_odds_for_horse(self, horse_number: int) -> list:
        result = []
        for odds in self.odds_list:
            if horse_number in odds.horse_numbers:
                result.append(odds)
        return result

    def get_top_odds(self, odds_type: OddsType, count: int = 10) -> list:
        filtered = self.get_odds_by_type(odds_type)
        filtered.sort(key=lambda x: x.odds_value)
        return filtered[:count]

    def __str__(self) -> str:
        return f"オッズ取得時刻: {self.timestamp.strftime('%H:%M:%S')}  件数: {len(self.odds_list)}"