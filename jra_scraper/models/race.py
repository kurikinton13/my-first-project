from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class TrackType(Enum):
    TURF = "芝"
    DIRT = "ダート"


class RaceClass(Enum):
    MAIDEN = "未勝利"
    ONE_WIN = "1勝クラス"
    TWO_WIN = "2勝クラス"
    THREE_WIN = "3勝クラス"
    OPEN = "オープン"
    GRADE_3 = "G3"
    GRADE_2 = "G2"
    GRADE_1 = "G1"
    LISTED = "リステッド"


@dataclass
class RaceCondition:
    course_name: str
    race_number: int
    track_type: TrackType
    distance: int
    race_class: RaceClass
    age_condition: str
    weight_condition: str
    weather: Optional[str] = None
    track_condition: Optional[str] = None
    start_time: Optional[datetime] = None

    def __str__(self) -> str:
        return f"{self.course_name}{self.race_number}R {self.track_type.value}{self.distance}m {self.race_class.value}"


@dataclass
class Race:
    race_id: str
    condition: RaceCondition
    horses: list = field(default_factory=list)
    odds_snapshots: list = field(default_factory=list)
    memo: Optional[str] = None
    scraped_at: datetime = field(default_factory=datetime.now)

    def add_horse(self, horse: "Horse") -> None:
        self.horses.append(horse)

    def add_odds_snapshot(self, snapshot: "OddsSnapshot") -> None:
        self.odds_snapshots.append(snapshot)

    def get_horse_by_gate(self, gate: int) -> Optional["Horse"]:
        for horse in self.horses:
            if horse.gate_number == gate:
                return horse
        return None

    def get_horse_by_number(self, horse_number: int) -> Optional["Horse"]:
        for horse in self.horses:
            if horse.horse_number == horse_number:
                return horse
        return None