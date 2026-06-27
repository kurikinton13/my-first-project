from dataclasses import dataclass
from typing import Optional


@dataclass
class Trainer:
    trainer_id: str
    name: str
    birth_date: Optional[str] = None
    debut_year: Optional[int] = None
    affiliation: Optional[str] = None
    wins_this_year: int = 0
    places_this_year: int = 0
    shows_this_year: int = 0
    total_wins: int = 0
    total_races: int = 0

    @property
    def win_rate(self) -> float:
        if self.total_races == 0:
            return 0.0
        return self.total_wins / self.total_races * 100

    def __str__(self) -> str:
        return f"{self.name} (勝率: {self.win_rate:.1f}%)"
