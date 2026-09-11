"""Fetch hero data + community builds from Fribbels' public services.

Two endpoints:
  - Hero metadata (skills, base stats, attribute, role) is at the S3 cache:
      https://e7-optimizer-game-data.s3-accelerate.amazonaws.com/herodata.json
  - Community-submitted builds are at the AWS API used by hero-library.html:
      POST https://krivpfvxi0.execute-api.us-west-2.amazonaws.com/dev/getBuilds
      Body: hero name as plain text. Response: {data: [3000 build rows]}

We cache responses on disk to avoid hammering the public service.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Optional

log = logging.getLogger(__name__)

HERODATA_URL = "https://e7-optimizer-game-data.s3-accelerate.amazonaws.com/herodata.json"
GET_BUILDS_URL = "https://krivpfvxi0.execute-api.us-west-2.amazonaws.com/dev/getBuilds"

DEFAULT_CACHE_DIR = Path(__file__).resolve().parents[2] / "cache" / "fribbels"
CACHE_TTL_DAYS = 14   # rebuild cache after this many days


@dataclass
class CachedBuilds:
    hero_name: str
    fetched_at: float
    builds: list[dict]

    @property
    def stale(self) -> bool:
        age_days = (time.time() - self.fetched_at) / 86400.0
        return age_days > CACHE_TTL_DAYS


class FribbelsClient:
    """Light wrapper around urllib + disk cache."""

    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE_DIR) -> None:
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # -------------------------------------------------------------- herodata

    def fetch_herodata(self, force: bool = False) -> dict:
        cache = self.cache_dir / "herodata.json"
        if cache.exists() and not force:
            age = (time.time() - cache.stat().st_mtime) / 86400.0
            if age < CACHE_TTL_DAYS:
                with cache.open("r", encoding="utf-8") as f:
                    return json.load(f)
        log.info("Fetching herodata from %s", HERODATA_URL)
        data = self._http_json(HERODATA_URL)
        with cache.open("w", encoding="utf-8") as f:
            json.dump(data, f)
        return data

    # -------------------------------------------------------------- builds

    def fetch_builds(self, hero_name: str, force: bool = False) -> CachedBuilds:
        cache_path = self._build_cache_path(hero_name)
        if cache_path.exists() and not force:
            cached = self._load_cache(cache_path)
            if cached and not cached.stale:
                return cached
        log.info("Fetching builds for '%s'", hero_name)
        raw = self._http_post(GET_BUILDS_URL, hero_name.encode("utf-8"))
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as e:
            raise RuntimeError(f"Invalid JSON from getBuilds for '{hero_name}': {e}")
        rows = payload.get("data", []) or []
        cached = CachedBuilds(
            hero_name=hero_name,
            fetched_at=time.time(),
            builds=rows,
        )
        self._save_cache(cache_path, cached)
        return cached

    def fetch_builds_bulk(
        self,
        hero_names: list[str],
        force: bool = False,
        polite_delay: float = 0.5,
    ) -> dict[str, CachedBuilds]:
        out: dict[str, CachedBuilds] = {}
        for i, name in enumerate(hero_names, 1):
            try:
                out[name] = self.fetch_builds(name, force=force)
                log.info("[%d/%d] %s: %d builds", i, len(hero_names),
                         name, len(out[name].builds))
            except Exception as e:
                log.warning("Failed to fetch %s: %s", name, e)
            time.sleep(polite_delay)
        return out

    # -------------------------------------------------------------- internal

    def _build_cache_path(self, hero_name: str) -> Path:
        safe = hero_name.replace(" ", "_").replace("/", "_").replace("&", "and")
        return self.cache_dir / "builds" / f"{safe}.json"

    def _load_cache(self, path: Path) -> Optional[CachedBuilds]:
        try:
            with path.open("r", encoding="utf-8") as f:
                d = json.load(f)
            return CachedBuilds(
                hero_name=d["hero_name"],
                fetched_at=float(d["fetched_at"]),
                builds=d.get("builds", []),
            )
        except Exception as e:
            log.warning("Could not load cache %s: %s", path, e)
            return None

    def _save_cache(self, path: Path, cached: CachedBuilds) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump({
                "hero_name": cached.hero_name,
                "fetched_at": cached.fetched_at,
                "builds": cached.builds,
            }, f)

    @staticmethod
    def _http_json(url: str) -> dict:
        from urllib.request import Request, urlopen
        req = Request(url, headers={"User-Agent": "e7-daily-bot/0.1"})
        with urlopen(req, timeout=30) as resp:
            raw = resp.read().decode("utf-8")
        return json.loads(raw)

    @staticmethod
    def _http_post(url: str, body: bytes) -> str:
        from urllib.request import Request, urlopen
        req = Request(
            url, data=body, method="POST",
            headers={
                "User-Agent": "e7-daily-bot/0.1",
                "Content-Type": "text/plain",
            },
        )
        with urlopen(req, timeout=60) as resp:
            return resp.read().decode("utf-8")
