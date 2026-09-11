"""Orchestrator — runs a chain of routines and reports the result.

Reads which routines to run from `config.yaml` and dispatches to the registered
routine classes.
"""
from __future__ import annotations

import csv
import logging
from datetime import datetime
from pathlib import Path
from typing import Iterable

import yaml

from .core.driver import AdbDriver, Driver, default_adb_path
from .core.matcher import TemplateMatcher
from .core.routine import Routine, RoutineResult

log = logging.getLogger(__name__)

# Registry filled in by routines.__init__
ROUTINE_REGISTRY: dict[str, type[Routine]] = {}


def register(name: str):
    """Decorator: @register('login') -> registers a Routine class."""
    def deco(cls: type[Routine]) -> type[Routine]:
        ROUTINE_REGISTRY[name] = cls
        cls.name = name
        return cls
    return deco


class Orchestrator:
    def __init__(self, config_path: str | Path = "config.yaml") -> None:
        self.config_path = Path(config_path)
        self.config = self._load_config()
        self.driver = self._build_driver()
        self.matcher = TemplateMatcher(
            self.driver,
            assets_dir=self.config.get("assets_dir", "assets"),
            default_threshold=self.config.get("match_threshold", 0.85),
        )

    def _load_config(self) -> dict:
        if not self.config_path.exists():
            raise FileNotFoundError(f"Missing config: {self.config_path}")
        with self.config_path.open("r", encoding="utf-8") as f:
            return yaml.safe_load(f) or {}

    def _build_driver(self) -> Driver:
        d = self.config.get("driver", {})
        kind = d.get("kind", "mouse")
        if kind == "adb":
            return AdbDriver(
                adb_path=d.get("adb_path") or default_adb_path(),
                serial=d.get("serial"),
                width=d.get("width", 1920),
                height=d.get("height", 1080),
                tap_jitter_px=d.get("tap_jitter_px", 6),
                tap_delay=d.get("tap_delay", 0.25),
            )
        if kind == "mouse":
            from .core.mouse_driver import MouseDriver
            return MouseDriver(
                window_title=d.get("window_title", "Epic Seven"),
                width=d.get("width", 1280),
                height=d.get("height", 720),
                auto_resize=d.get("auto_resize", True),
                auto_focus=d.get("auto_focus", True),
                move_to_origin=d.get("move_to_origin", True),
                tap_jitter_px=d.get("tap_jitter_px", 6),
                tap_delay=d.get("tap_delay", 0.25),
            )
        raise ValueError(f"Unsupported driver kind: {kind}")

    def run_daily(self) -> list[RoutineResult]:
        """Run the routines listed in config.daily in order."""
        names: Iterable[str] = self.config.get("daily", [])
        return self._run_chain(names)

    def run_one(self, name: str) -> RoutineResult:
        return self._run_chain([name])[0]

    def _run_chain(self, names: Iterable[str]) -> list[RoutineResult]:
        results: list[RoutineResult] = []
        for name in names:
            cls = ROUTINE_REGISTRY.get(name)
            if cls is None:
                log.warning("Unknown routine '%s' — skipping (registered: %s)",
                            name, list(ROUTINE_REGISTRY))
                continue
            routine = cls(self.driver, self.matcher)
            self._inject_routine_config(routine, name)
            results.append(routine.execute())
        self._write_history(results)
        return results

    def _inject_routine_config(self, routine: Routine, name: str) -> None:
        """Make per-routine config available as `routine.config`."""
        per_routine = self.config.get("routines", {}).get(name, {}) or {}
        routine.config = per_routine  # type: ignore[attr-defined]

    def _write_history(self, results: list[RoutineResult]) -> None:
        history_dir = Path(self.config.get("history_dir", "logs"))
        history_dir.mkdir(parents=True, exist_ok=True)
        path = history_dir / "routine_history.csv"
        write_header = not path.exists()
        with path.open("a", newline="", encoding="utf-8") as f:
            w = csv.writer(f)
            if write_header:
                w.writerow(["timestamp", "routine", "success", "duration_s",
                            "step_count", "error", "screenshot"])
            for r in results:
                w.writerow([
                    datetime.now().isoformat(timespec="seconds"),
                    r.name, r.succeeded, f"{r.duration_seconds:.1f}",
                    len(r.steps), r.error or "", r.screenshot_path or "",
                ])
