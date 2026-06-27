from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from enum import Enum


class Sex(Enum):
    COLT = "牡"
    FILLY = "牝"
    GELDING = "せん"


@dataclass
class PastRace:
    date: datetime
    race_name: str
    course_name: str
    track_type: str
    distance: int
    race_class: str
    finishing_position: int
    total_horses: int
    time: str
    margin: str
    last_3f: Optional[str] = None
    passing_order: Optional[str] = None
    jockey: Optional[str] = None
    weight: Optional[float] = None
    odds: Optional[float] = None
    popularity: Optional[int] = None
    horse_weight: Optional[int] = None
    memo: Optional[str] = None

    def __str__(self) -> str:
        return f"{self.date.strftime('%m/%d')} {self.race_name} {self.finishing_position}着/{self.total_horses}頭 {self.time} 上がり{self.last_3f or '---'}"


@dataclass
class HorseProfile:
    horse_id: str
    name: str
    sex: Sex
    age: int
    trainer: str
    owner: str
    breeder: str
    sire: str
    dam: str
    dam_sire: str
    total_races: int = 0
    wins: int = 0
    places: int = 0
    shows: int = 0
    total_prize: int = 0
    past_races: list = field(default_factory=list)

    def add_past_race(self, race: PastRace) -> None:
        self.past_races.append(race)
        self.past_races.sort(key=lambda x: x.date, reverse=True)

    def get_recent_races(self, count: int = 5) -> list:
        return self.past_races[:count]


@dataclass
class Horse:
    gate_number: int
    horse_number: int
    name: str
    sex_age: str
    weight: float
    jockey: str
    trainer: str
    horse_weight: Optional[int] = None
    weight_change: Optional[str] = None
    profile: Optional[HorseProfile] = None
    past_races: list = field(default_factory=list)
    memo: Optional[str] = None

    @property
    def sex(self) -> Optional[Sex]:
        if self.sex_age:
            return Sex(self.sex_age[0])

    @property
    def age(self) -> Optional[int]:
        if len(self.sex_age) > 1:
            try:
                return int(self.sex_age[1:])
            except ValueError:
                return None
        return None

    def add_past_race(self, race: PastRace) -> None:
        self.past_races.append(race)
        self.past_races.sort(key=lambda x: x.date, reverse=True)

    def get_recent_form(self, count: int = 5) -> list:
        return self.past_races[:count]

    def __str__(self) -> str:
        return f"{self.gate_number}枠{self.horse_number}番 {self.name} ({self.sex_age}) {self.jockey} {self.weight}kg"