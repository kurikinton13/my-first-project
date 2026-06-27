import asyncio
import logging
import random
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional
from urllib.parse import urljoin

import aiohttp
from bs4 import BeautifulSoup

from jra_scraper.config.settings import ScrapingConfig


logger = logging.getLogger(__name__)


@dataclass
class ScrapingConfig:
    base_url: str = "https://race.netkeiba.com"
    user_agent: str = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    request_timeout: int = 30
    max_retries: int = 3
    retry_delay: float = 1.0
    max_delay: float = 5.0
    rate_limit: float = 1.0


class BaseScraper(ABC):
    def __init__(self, config: Optional[ScrapingConfig] = None):
        self.config = config or ScrapingConfig()
        self.session: Optional[aiohttp.ClientSession] = None
        self._last_request_time = 0.0

    async def __aenter__(self):
        connector = aiohttp.TCPConnector(limit=10)
        timeout = aiohttp.ClientTimeout(total=self.config.request_timeout)
        self.session = aiohttp.ClientSession(
            connector=connector,
            timeout=timeout,
            headers={"User-Agent": self.config.user_agent}
        )
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _rate_limit(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self.config.rate_limit:
            await asyncio.sleep(self.config.rate_limit - elapsed)
        self._last_request_time = time.time()

    async def _fetch(self, url: str) -> Optional[BeautifulSoup]:
        await self._rate_limit()

        for attempt in range(self.config.max_retries):
            try:
                async with self.session.get(url) as response:
                    if response.status == 200:
                        html = await response.text()
                        return BeautifulSoup(html, "html.parser")
                    elif response.status == 404:
                        logger.warning(f"Page not found: {url}")
                        return None
                    else:
                        logger.warning(f"HTTP {response.status}: {url}")
            except asyncio.TimeoutError:
                logger.warning(f"Timeout ({attempt + 1}/{self.config.max_retries}): {url}")
            except Exception as e:
                logger.warning(f"Error ({attempt + 1}/{self.config.max_retries}): {url} - {e}")

            if attempt < self.config.max_retries - 1:
                delay = min(self.config.retry_delay * (2 ** attempt) + random.uniform(0, 1),
                           self.config.max_delay)
                await asyncio.sleep(delay)

        logger.error(f"Failed after {self.config.max_retries} attempts: {url}")
        return None

    def _build_url(self, path: str) -> str:
        return urljoin(self.config.base_url, path)

    @abstractmethod
    async def scrape(self, *args, **kwargs):
        pass