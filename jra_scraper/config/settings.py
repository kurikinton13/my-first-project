import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class ScrapingConfig:
    base_url: str = "https://race.netkeiba.com"
    db_url: str = "https://db.netkeiba.com"
    user_agent: str = (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/120.0.0.0 Safari/537.36"
    )
    request_timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    max_delay: float = 5.0
    rate_limit: float = 1.0
    output_dir: str = "output"


settings = ScrapingConfig()
