"""Guild War / Arena meta data fetcher.

Wraps the three endpoints behind https://fribbels.github.io/e7/gw-meta.html:

  POST /getMeta      - top-N defenses with W/L/D counts and offenseData index
  POST /getDef       - given a 3-unit defense, return common offense comps
  POST /buildDef     - search for popular defenses containing/excluding heroes

⚠️ As of 2026, the upstream backend has stopped accepting fresh submissions.
   The `maxTimestamp` field returned by `/getMeta` reveals when data was
   last updated. Surface this prominently in the UI.
"""
from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Iterable, Optional

from .fribbels_api import DEFAULT_CACHE_DIR

log = logging.getLogger(__name__)

GW_API_BASE = "https://z4tfy2r5kc.execute-api.us-west-2.amazonaws.com/dev"
META_CACHE_TTL_DAYS = 14   # data is stale anyway; cache aggressively


# --- Data classes ------------------------------------------------------------

@dataclass(frozen=True)
class Defense:
    """A defense team: 3 hero codes + win/loss/draw counts."""
    units: tuple[str, str, str]    # hero codes (c1022, c1153, ...)
    wins: int
    losses: int
    draws: int

    @property
    def total_matches(self) -> int:
        return self.wins + self.losses + self.draws

    @property
    def winrate(self) -> float:
        if self.total_matches == 0:
            return 0.0
        return self.wins / self.total_matches

    @property
    def loss_rate(self) -> float:
        if self.total_matches == 0:
            return 0.0
        return self.losses / self.total_matches


@dataclass
class GwMetaSnapshot:
    fetched_at: float
    max_timestamp: int                       # upstream's last update (unix epoch)
    defenses: list[Defense] = field(default_factory=list)
    offense_data: dict[str, list] = field(default_factory=dict)  # heroCode -> comp list

    @property
    def data_age_days(self) -> float:
        return max(0.0, (time.time() - self.max_timestamp) / 86400.0)

    @property
    def data_date(self) -> str:
        try:
            return datetime.fromtimestamp(self.max_timestamp).strftime("%Y-%m-%d")
        except Exception:
            return "unknown"


# --- Client -----------------------------------------------------------------

class GwMetaClient:
    def __init__(self, cache_dir: Path | str = DEFAULT_CACHE_DIR) -> None:
        self.cache_dir = Path(cache_dir) / "gw_meta"
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    # ------------------------------------------------ /getMeta

    def fetch_meta(self, force: bool = False) -> GwMetaSnapshot:
        cache = self.cache_dir / "meta.json"
        if cache.exists() and not force:
            age_days = (time.time() - cache.stat().st_mtime) / 86400.0
            if age_days < META_CACHE_TTL_DAYS:
                with cache.open("r", encoding="utf-8") as f:
                    raw = json.load(f)
                return self._parse_meta(raw, fetched_at=cache.stat().st_mtime)
        log.info("Fetching GW meta snapshot")
        raw_text = self._http_post("/getMeta", "")
        raw = json.loads(raw_text)
        with cache.open("w", encoding="utf-8") as f:
            json.dump(raw, f)
        return self._parse_meta(raw, fetched_at=time.time())

    def _parse_meta(self, raw: dict, fetched_at: float) -> GwMetaSnapshot:
        defenses: list[Defense] = []
        for d in raw.get("data", []) or []:
            units_str = d.get("defense", "") or ""
            parts = units_str.split(",")
            if len(parts) != 3:
                continue
            defenses.append(Defense(
                units=tuple(parts),  # type: ignore
                wins=int(d.get("w", 0) or 0),
                losses=int(d.get("l", 0) or 0),
                draws=int(d.get("d", 0) or 0),
            ))
        return GwMetaSnapshot(
            fetched_at=fetched_at,
            max_timestamp=int(raw.get("maxTimestamp", 0) or 0),
            defenses=defenses,
            offense_data=raw.get("offenseData", {}) or {},
        )

    # ------------------------------------------------ /getDef

    def fetch_def(self, units: Iterable[str]) -> dict:
        """Given a defense (list of 3 hero codes), return common offense comps."""
        units_list = list(units)
        key = ",".join(units_list)
        cache = self.cache_dir / f"def__{key.replace(',', '_')}.json"
        if cache.exists():
            age_days = (time.time() - cache.stat().st_mtime) / 86400.0
            if age_days < META_CACHE_TTL_DAYS:
                with cache.open("r", encoding="utf-8") as f:
                    return json.load(f)
        log.info("Fetching offenses against defense: %s", key)
        raw_text = self._http_post("/getDef", key)
        raw = json.loads(raw_text)
        with cache.open("w", encoding="utf-8") as f:
            json.dump(raw, f)
        return raw

    # ------------------------------------------------ /buildDef

    def build_def(
        self,
        include_units: list[str] = (),  # type: ignore
        exclude_units: list[str] = (),  # type: ignore
    ) -> dict:
        """Search popular defenses by include/exclude. Up to 3 includes + 1 exclude.

        The endpoint takes a 5-element CSV string: include[0..2], include[3]
        becomes another include, last slot is exclude. We pass 5 slots
        (empty for unfilled) joined with commas.
        """
        slots = list(include_units) + ["", "", "", ""]
        slots = slots[:4]
        slots.extend([""] * (4 - len(slots)))
        slots.append(exclude_units[0] if exclude_units else "")
        body = ",".join(slots)
        log.info("buildDef body=%r", body)
        raw_text = self._http_post("/buildDef", body)
        return json.loads(raw_text)

    # ------------------------------------------------ HTTP

    @staticmethod
    def _http_post(path: str, body: str) -> str:
        from urllib.request import Request, urlopen
        url = GW_API_BASE + path
        req = Request(
            url, data=body.encode("utf-8"), method="POST",
            headers={
                "User-Agent": "e7-daily-bot/0.1",
                "Content-Type": "text/plain",
            },
        )
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")


# --- Code <-> name helpers ---------------------------------------------------

class HeroCodeBook:
    """Translate Fribbels hero codes (c1022) <-> names (Ruele of Light).

    Loads from herodata.json (cached on disk via FribbelsClient).
    """

    def __init__(self, herodata: dict) -> None:
        self.by_code: dict[str, str] = {}
        self.by_name: dict[str, str] = {}
        for name, info in herodata.items():
            code = (info or {}).get("code")
            if not code:
                continue
            self.by_code[code] = name
            self.by_name[name.lower()] = code

    def name_of(self, code: str) -> str:
        return self.by_code.get(code, code)

    def code_of(self, name: str) -> Optional[str]:
        return self.by_name.get(name.strip().lower())

    def names_of(self, codes: Iterable[str]) -> list[str]:
        return [self.name_of(c) for c in codes]
